"""
Song stats shared between everyone who uses this SuperMusic server.

Two things go into the shared database (app/core/store.py):

  * Lookups. Whenever an import looks a song up online (Deezer BPM, the key and
    energy measured from its preview, the genre from listener tags), the answer
    is saved, so the next person's map starts from it.
  * Listener corrections. Anyone can say "this song is really 90 BPM, not 180"
    or "this is A minor", rate its energy, or tag its vibe ("late night", "gym").

Guarding against bad edits. One person's correction changes only their own
map. It becomes the shared value, used on everyone's map, only when at least
two different listeners (from different networks) agree, and they make up at
least 60% of the votes for that stat. "Agree" means close enough: within 4% for
BPM (so 90 and 92 agree, and 90 and 180 count as the same tempo felt half or
double time), within 0.15 for 0-1 scores like energy, the same year, the same
key or genre. The shared value is the average of the agreeing votes, so one
wild answer can't drag it. Each listener also has a daily vote limit.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import statistics
import time
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from app.core import store
from app.core.genres import GENRES
from app.core.library_import import song_key
from app.core.music_map import _find, parse_key

MIN_AGREE = 2         # listeners who must agree before a correction reaches other people's maps
MIN_SHARE = 0.6       # ...and the share of all votes for that stat they must make up
DAILY_VOTES = 500     # per listener, and per network address
MAX_VIBES = 3         # vibe tags one listener can give one song
SHOWN_VIBES = 5

SCORES = ("energy", "danceability", "valence", "acousticness")
FIELDS = ("bpm", "key", "year", "genre", *SCORES, "vibes")
LABELS = {
    "bpm": "Tempo (BPM)", "key": "Key", "year": "Year", "genre": "Genre", "energy": "Energy",
    "danceability": "Danceability", "valence": "Happiness", "acousticness": "Acoustic", "vibes": "Vibes",
}
_GENRE_BY_LOWER = {g.lower(): g for g in GENRES}


class VoteError(ValueError):
    """A vote that can't be accepted; the message is shown to the listener."""


# ---------------------------------------------------------------------------
# Checking values
# ---------------------------------------------------------------------------

def _number(value: Any, lo: float, hi: float, what: str) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise VoteError(f"{what} should be a number.")
    if not math.isfinite(v) or not lo <= v <= hi:
        raise VoteError(f"{what} should be between {lo:g} and {hi:g}.")
    return v


def normalise(field: str, value: Any) -> Any:
    """A listener's answer in one standard form, or VoteError if it isn't a sensible one."""
    if field == "bpm":
        return round(_number(value, 40, 250, "Tempo"), 1)
    if field in SCORES:
        v = _number(value, 0, 100, LABELS[field])
        return round(v / 100 if v > 1 else v, 3)  # the page sends 0-100; 0-1 is also fine
    if field == "year":
        return int(_number(value, 1900, time.gmtime().tm_year + 1, "Year"))
    if field == "key":
        k = parse_key(value)
        if not k:
            raise VoteError("Key should look like 'A minor', 'F#', 'Bbm' or '8A'.")
        return k.name
    if field == "genre":
        parts = value if isinstance(value, list) else re.split(r"[;,]", str(value or ""))
        out = []
        for p in parts:
            g = _GENRE_BY_LOWER.get(str(p).strip().lower())
            if not g and str(p).strip():
                raise VoteError(f"Pick genres from the list ({', '.join(GENRES)}).")
            if g and g not in out:
                out.append(g)
        if not out:
            raise VoteError("Pick at least one genre.")
        return out[:2]
    if field == "vibes":
        parts = value if isinstance(value, list) else re.split(r"[;,]", str(value or ""))
        out = []
        for p in parts:
            t = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 &'-]", "", str(p).lower())).strip()[:24]
            if t and t not in out:
                out.append(t)
        if not out:
            raise VoteError("Add at least one vibe, like 'late night' or 'gym'.")
        return out[:MAX_VIBES]
    raise VoteError(f"Unknown stat '{field}'.")


# ---------------------------------------------------------------------------
# Who is voting
# ---------------------------------------------------------------------------

def voter_id(username: Optional[str], listener_id: Optional[str]) -> Optional[str]:
    """Signed-in listeners vote as their account, others as their browser's random id."""
    if username:
        return f"user:{username}"
    lid = str(listener_id or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{8,64}", lid):
        return f"anon:{lid}"
    return None


def ip_hash(ip: Optional[str]) -> Optional[str]:
    """Network addresses are only kept scrambled, to tell "two people" from "one person twice"."""
    if not ip:
        return None
    salt = os.getenv("JWT_SECRET_KEY", "supermusic")
    return hashlib.sha256(f"{salt}|{ip}".encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def _song(c, artist: str, title: str) -> str:
    key = song_key(artist, title)
    c.execute("INSERT OR IGNORE INTO songs (song_key, artist, title) VALUES (?, ?, ?)", (key, artist, title))
    return key


def record_lookup(artist: str, title: str, info: Dict[str, Any], only_if_new: bool = False) -> None:
    """Save what an online lookup found, so other people's imports can reuse it.

    `only_if_new`: skip songs already saved (an answer from the lookup cache, already recorded)."""
    facts = {}
    for f in ("bpm", "year", "energy"):
        v = info.get(f)
        if isinstance(v, (int, float)) and math.isfinite(v) and v > 0:
            facts[f] = (v, "preview analysis" if f == "energy" else "Deezer")
    if info.get("key"):
        k = parse_key(info["key"])
        if k:
            facts["key"] = (k.name, "preview analysis")
    if info.get("genre"):
        facts["genre"] = (str(info["genre"]).split(";"), info.get("genre_source") or "")
    if not facts or not str(title or "").strip():
        return
    now = time.time()
    try:
        if only_if_new and store.connect().execute(
                "SELECT 1 FROM song_facts WHERE song_key = ? LIMIT 1", (song_key(artist, title),)).fetchone():
            return
        with store.tx() as c:
            key = _song(c, artist, title)
            c.executemany(
                "INSERT OR REPLACE INTO song_facts (song_key, field, value, source, updated_at) VALUES (?, ?, ?, ?, ?)",
                [(key, f, json.dumps(v), src, now) for f, (v, src) in facts.items()])
    except Exception:
        pass  # the shared database is a bonus; an import never fails because of it


def vote(artist: str, title: str, field: str, value: Any, voter: str, ip: Optional[str] = None) -> Any:
    """Save (or with value None, take back) one listener's answer for one stat of one song."""
    if field not in FIELDS:
        raise VoteError(f"Unknown stat '{field}'.")
    if not str(title or "").strip():
        raise VoteError("The song needs a title.")
    c = store.connect()
    key = song_key(artist, title)
    if value is None or value == "" or value == []:
        c.execute("DELETE FROM song_votes WHERE song_key = ? AND field = ? AND voter = ?", (key, field, voter))
        return None
    v = normalise(field, value)
    day_ago = time.time() - 86400
    mine = c.execute("SELECT COUNT(*) FROM song_votes WHERE voter = ? AND created_at > ?", (voter, day_ago)).fetchone()[0]
    from_ip = c.execute("SELECT COUNT(*) FROM song_votes WHERE ip_hash = ? AND created_at > ?",
                        (ip, day_ago)).fetchone()[0] if ip else 0
    if mine >= DAILY_VOTES or from_ip >= DAILY_VOTES:
        raise VoteError(f"That's {DAILY_VOTES} edits today, the daily limit. Thank you! Try again tomorrow.")
    with store.tx() as c:
        _song(c, artist, title)
        c.execute("INSERT OR REPLACE INTO song_votes (song_key, field, voter, ip_hash, value, created_at) "
                  "VALUES (?, ?, ?, ?, ?, ?)", (key, field, voter, ip, json.dumps(v), time.time()))
    return v


# ---------------------------------------------------------------------------
# Agreement
# ---------------------------------------------------------------------------

def _fold(v: float, ref: float) -> float:
    """Move a tempo by octaves next to `ref`: 180 BPM felt half time is 90."""
    while v > ref * 1.41:
        v /= 2
    while v < ref / 1.41:
        v *= 2
    return v


def _close(field: str, a: float, b: float) -> bool:
    if field == "bpm":
        return abs(a - b) <= 0.04 * max(a, b)
    if field == "year":
        return a == b
    return abs(a - b) <= 0.15


def agree(field: str, values: List[Any]) -> Optional[Dict[str, Any]]:
    """The value most listeners agree on: {"value", "agree", "votes"}, or None if they don't (yet).

    `values` holds one answer per listener."""
    n = len(values)
    if n < MIN_AGREE:
        return None
    if field == "vibes":
        counts = Counter(t for tags in values for t in set(tags))
        tags = [t for t, k in counts.most_common() if k >= MIN_AGREE][:SHOWN_VIBES]
        return {"value": tags, "agree": max(counts.values()), "votes": n} if tags else None
    if field in ("key", "genre"):
        counts = Counter(json.dumps(v) for v in values)
        top, k = counts.most_common(1)[0]
        if k >= MIN_AGREE and k >= MIN_SHARE * n:
            return {"value": json.loads(top), "agree": k, "votes": n}
        return None
    nums = [float(v) for v in values]
    mid = statistics.median(nums)
    if field == "bpm":
        nums = [_fold(v, mid) for v in nums]
        mid = statistics.median(nums)
    close = [v for v in nums if _close(field, v, mid)]
    if len(close) < MIN_AGREE or len(close) < MIN_SHARE * n:
        return None
    avg = sum(close) / len(close)
    value = int(round(avg)) if field == "year" else round(avg, 1 if field == "bpm" else 3)
    return {"value": value, "agree": len(close), "votes": n}


def _one_per_listener(rows: Iterable) -> Dict[Tuple[str, str], List[Any]]:
    """Votes per (song, stat), keeping only the latest vote from each network address."""
    latest: Dict[Tuple[str, str, str], Tuple[float, Any]] = {}
    for r in rows:
        who = r["ip_hash"] or r["voter"]
        k = (r["song_key"], r["field"], who)
        if k not in latest or r["created_at"] > latest[k][0]:
            latest[k] = (r["created_at"], json.loads(r["value"]))
    out: Dict[Tuple[str, str], List[Any]] = defaultdict(list)
    for (song, field, _), (_, v) in latest.items():
        out[(song, field)].append(v)
    return out


def _chunks(items: List[str], n: int = 500):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def shared_values(keys: List[str], voter: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """{song_key: {stat: value}}: what listeners agreed on, with this listener's own edits on top."""
    c = store.connect()
    out: Dict[str, Dict[str, Any]] = defaultdict(dict)
    keys = sorted(set(keys))
    for chunk in _chunks(keys):
        marks = ",".join("?" * len(chunk))
        rows = c.execute(f"SELECT song_key, field, voter, ip_hash, value, created_at FROM song_votes "
                         f"WHERE song_key IN ({marks})", chunk).fetchall()
        for (song, field), values in _one_per_listener(rows).items():
            a = agree(field, values)
            if a:
                out[song][field] = a["value"]
        if voter:
            for r in rows:
                if r["voter"] == voter:
                    v = json.loads(r["value"])
                    if r["field"] == "vibes":  # your own vibes are added to the agreed ones
                        v = list(dict.fromkeys([*out[r["song_key"]].get("vibes", []), *v]))[:SHOWN_VIBES]
                    out[r["song_key"]][r["field"]] = v
    return {k: v for k, v in out.items() if v}


def song_view(artist: str, title: str, voter: Optional[str] = None) -> Dict[str, Any]:
    """Everything known about one song's stats, for the "Fix this song's stats" panel."""
    c = store.connect()
    key = song_key(artist, title)
    facts = {r["field"]: {"value": json.loads(r["value"]), "source": r["source"]}
             for r in c.execute("SELECT field, value, source FROM song_facts WHERE song_key = ?", (key,))}
    rows = c.execute("SELECT song_key, field, voter, ip_hash, value, created_at FROM song_votes WHERE song_key = ?",
                     (key,)).fetchall()
    grouped = _one_per_listener(rows)
    mine = {r["field"]: json.loads(r["value"]) for r in rows if voter and r["voter"] == voter}
    stats = {}
    for f in FIELDS:
        values = grouped.get((key, f), [])
        entry: Dict[str, Any] = {"label": LABELS[f], "votes": len(values)}
        if f in facts:
            entry["looked_up"] = facts[f]["value"]
            entry["source"] = facts[f]["source"]
        a = agree(f, values)
        if a:
            entry["shared"] = a["value"]
            entry["agree"] = a["agree"]
        if f in mine:
            entry["mine"] = mine[f]
        if f == "vibes" and values:
            counts = Counter(t for tags in values for t in set(tags))
            entry["suggested"] = [{"tag": t, "votes": k} for t, k in counts.most_common(12)]
        stats[f] = entry
    return {"song_key": key, "artist": artist, "title": title, "stats": stats,
            "rules": {"min_agree": MIN_AGREE, "min_share": MIN_SHARE}, "genres": GENRES}


# ---------------------------------------------------------------------------
# Using it on a library
# ---------------------------------------------------------------------------

def _column(df: pd.DataFrame, field: str) -> str:
    if field in ("bpm", "key", "year", "genre"):
        col = _find(df, field)
    else:
        col = next((c for c in df.columns if str(c).lower() == field), None)
    if col is None:
        col = field
        df[col] = None
    if df[col].dtype != object:
        df[col] = df[col].astype(object)
    return col


def apply(df: pd.DataFrame, voter: Optional[str] = None) -> Tuple[pd.DataFrame, int]:
    """Put agreed stats (and this listener's own edits) into a library. Returns (df, songs changed).

    Agreed values replace whatever the file or a lookup said: that is the point of
    listeners correcting them. Never raises: a broken database leaves the library as it was."""
    t_col, a_col = _find(df, "title"), _find(df, "artist")
    if t_col is None or df.empty:
        return df, 0
    try:
        keys = [song_key(a if a_col and pd.notna(a) else "", t) for a, t in
                zip(df[a_col] if a_col else [""] * len(df), df[t_col].astype(str))]
        found = shared_values(keys, voter)
    except Exception:
        return df, 0
    if not found:
        return df, 0
    df = df.copy()
    cols: Dict[str, str] = {}
    changed = 0
    for i, k in zip(df.index, keys):
        vals = found.get(k)
        if not vals:
            continue
        changed += 1
        for f, v in vals.items():
            if f not in cols:
                cols[f] = _column(df, f)
            df.at[i, cols[f]] = ";".join(v) if isinstance(v, list) else v
    return df, changed


def activity(limit: int = 30) -> Dict[str, Any]:
    """The latest edits from everyone, and how many songs listeners have described."""
    c = store.connect()
    rows = c.execute(
        "SELECT v.field, v.value, v.created_at, s.artist, s.title FROM song_votes v "
        "LEFT JOIN songs s ON s.song_key = v.song_key ORDER BY v.created_at DESC LIMIT ?", (limit,)).fetchall()
    totals = c.execute("SELECT COUNT(*), COUNT(DISTINCT song_key), COUNT(DISTINCT voter) FROM song_votes").fetchone()
    looked_up = c.execute("SELECT COUNT(DISTINCT song_key) FROM song_facts").fetchone()[0]
    return {
        "recent": [{"field": r["field"], "label": LABELS.get(r["field"], r["field"]), "value": json.loads(r["value"]),
                    "artist": r["artist"], "title": r["title"], "at": r["created_at"]} for r in rows],
        "votes": totals[0], "songs": totals[1], "listeners": totals[2], "songs_looked_up": looked_up,
    }
