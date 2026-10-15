"""
The community atlas: one Music Map drawn from every library people listed publicly.

Each listed share that kept its song list adds its songs. Songs in several
libraries appear once, and the number of listeners who have a song stands in
for its play count, so songs many people share glow brighter. No one's play
counts, likes or dates go in: only what the song is (title, artist, genre, key,
tempo, mood, sound).

The atlas is rebuilt when the set of listed maps changes, at most every
REBUILD_EVERY seconds, in a background thread; until then the last one is served.

People can pin a short note on any star (song). Notes hang off the song, not its
position, so they survive rebuilds.
"""
from __future__ import annotations

import gzip
import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from app.core import map_share, store
from app.core.config import settings
from app.core.library_import import song_key
from app.core.music_map import ALIASES, AUDIO_FEATURES, MapOptions, _find, build_map

MAX_SONGS = 20_000
REBUILD_EVERY = 600     # seconds
MAX_PINS_PER_DAY = 30
PIN_LENGTH = 200
KEEP = ("title", "artist", "album", "genre", "key", "mode", "bpm", "year")

_lock = threading.Lock()
_building = [False]


def _dir() -> Path:
    d = settings.DATA_DIR / "atlas"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _signature() -> List[str]:
    return sorted(m["id"] for m in map_share.all_listed() if m.get("has_library"))


def _library_rows(share_id: str) -> Optional[pd.DataFrame]:
    path = map_share.library_path(share_id)
    if not path:
        return None
    try:
        df = pd.read_csv(path)
    except Exception:
        return None
    cols = {}
    for f in KEEP:
        c = _find(df, f)
        if c is not None:
            cols[c] = f
    for c in df.columns:
        lc = str(c).lower().strip()
        if lc in AUDIO_FEATURES or lc == "sound":
            cols[c] = lc
    if "title" not in cols.values():
        return None
    out = df[list(cols)].rename(columns=cols)
    out = out.loc[:, ~out.columns.duplicated()]
    out["_key"] = [song_key(a, t) for a, t in zip(out.get("artist", [""] * len(out)), out["title"])]
    return out


def collect() -> tuple:
    """(songs DataFrame with a `listeners` column, {song_key: [share ids]}, share metas used)."""
    frames, owners = [], {}
    used = []
    for meta in map_share.all_listed():
        if not meta.get("has_library"):
            continue
        df = _library_rows(meta["id"])
        if df is None or df.empty:
            continue
        df = df.drop_duplicates("_key")
        for k in df["_key"]:
            owners.setdefault(k, []).append(meta["id"])
        frames.append(df)
        used.append(meta)
    if not frames:
        return pd.DataFrame(), {}, []
    allsongs = pd.concat(frames, ignore_index=True, sort=False)
    # Keep the most complete row per song (most filled-in columns)
    allsongs["_filled"] = allsongs.notna().sum(axis=1)
    allsongs = allsongs.sort_values("_filled", ascending=False).drop_duplicates("_key")
    allsongs["listeners"] = allsongs["_key"].map(lambda k: len(owners.get(k, [])))
    allsongs = allsongs.sort_values(["listeners", "_filled"], ascending=False).head(MAX_SONGS)
    allsongs = allsongs.drop(columns=["_filled"]).reset_index(drop=True)
    return allsongs, owners, used


def build() -> Dict[str, Any]:
    """Draw the atlas now and save it."""
    songs, owners, used = collect()
    sig = sorted(m["id"] for m in used)
    if len(songs) < 3:
        result: Dict[str, Any] = {"tracks": [], "edges": [], "clusters": [], "hidden_connections": [],
                                  "insights": [], "recommendations": [], "meta": {"count": 0}}
    else:
        keys = songs["_key"].tolist()
        if "sound" in songs.columns:  # kept beside the map (too big to send to browsers)
            vecs = {k: v for k, v in zip(keys, songs["sound"]) if isinstance(v, str) and v}
            with gzip.open(_dir() / "sound.json.gz", "wt", encoding="utf-8") as f:
                json.dump(vecs, f)
        df = songs.drop(columns=["_key"]).rename(columns={"listeners": "play_count"})
        result = build_map(df, MapOptions(neighbors=4))
        for t, k in zip(result["tracks"], keys):
            t["song_key"] = k
            t["listeners"] = t.pop("plays", None) or len(owners.get(k, []))
        # Popularity on the atlas isn't anyone's taste: no "for you" picks or play insights
        result["recommendations"], result["insights"] = [], []
        result.pop("stats", None)
        for c in result["clusters"]:
            c.pop("listening_share", None)
            c.pop("lift", None)
    names = {m["id"]: {"title": m.get("title"), "by": m.get("by"), "owner": m.get("owner")} for m in used}
    result["meta"] = {**result.get("meta", {}), "source": "community atlas", "built": time.time(),
                      "maps": len(used), "signature": sig, "has_listening_data": False}
    with gzip.open(_dir() / "atlas.json.gz", "wt", encoding="utf-8") as f:
        json.dump(result, f, separators=(",", ":"))
    with gzip.open(_dir() / "owners.json.gz", "wt", encoding="utf-8") as f:
        json.dump({"owners": {k: v for k, v in owners.items()}, "maps": names}, f, separators=(",", ":"))
    return result


def _load(name: str) -> Optional[Dict[str, Any]]:
    p = _dir() / name
    if not p.is_file():
        return None
    try:
        with gzip.open(p, "rt", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _rebuild_later() -> None:
    with _lock:
        if _building[0]:
            return
        _building[0] = True

    def run():
        try:
            build()
        except Exception:
            pass
        finally:
            _building[0] = False

    threading.Thread(target=run, daemon=True).start()


def get() -> Dict[str, Any]:
    """The atlas. Built on the spot the first time; afterwards refreshed in the background."""
    current = _load("atlas.json.gz")
    if current is None:
        with _lock:
            current = _load("atlas.json.gz")
            if current is None:
                current = build()
        return current
    meta = current.get("meta", {})
    if meta.get("signature") != _signature() and time.time() - meta.get("built", 0) > REBUILD_EVERY:
        _rebuild_later()
        current["meta"]["refreshing"] = True
    return current


def sound_vectors() -> Dict[str, str]:
    """{song_key: encoded CLAP vector} for atlas songs that have one."""
    return _load("sound.json.gz") or {}


def song_maps(keys: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """{song_key: [{id, title, by}]}: the public maps each song is on."""
    data = _load("owners.json.gz") or {}
    owners, maps = data.get("owners", {}), data.get("maps", {})
    return {k: [{"id": s, **maps.get(s, {})} for s in owners.get(k, [])] for k in keys}


def mine(df: pd.DataFrame) -> List[int]:
    """Atlas star ids for the songs in this library."""
    t_col, a_col = _find(df, "title"), _find(df, "artist")
    if t_col is None:
        return []
    artists = df[a_col] if a_col else [""] * len(df)
    keys = {song_key(a, t) for a, t in zip(artists, df[t_col]) if pd.notna(t)}
    atlas = get()
    return [t["id"] for t in atlas.get("tracks", []) if t.get("song_key") in keys]


# ---- pins -------------------------------------------------------------------------------

def pins(keys: Optional[List[str]] = None, limit: int = 500) -> List[Dict[str, Any]]:
    c = store.connect()
    if keys is None:
        rows = c.execute("SELECT * FROM atlas_pins ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    else:
        marks = ",".join("?" * len(keys)) or "''"
        rows = c.execute(f"SELECT * FROM atlas_pins WHERE song_key IN ({marks}) ORDER BY created_at DESC",
                         keys).fetchall()
    from app.core.social import display_names

    names = display_names([r["author"][5:] for r in rows if r["author"].startswith("user:")])
    out = []
    for r in rows:
        a = r["author"]
        out.append({"id": r["id"], "song_key": r["song_key"], "text": r["text"], "at": r["created_at"],
                    "author": names.get(a[5:], a[5:]) if a.startswith("user:") else "a listener",
                    "username": a[5:] if a.startswith("user:") else None, "voter": a})
    return out


def add_pin(song: str, text: str, author: str) -> Dict[str, Any]:
    text = " ".join(str(text or "").split())[:PIN_LENGTH]
    if not text:
        raise ValueError("Write something to pin.")
    c = store.connect()
    today = c.execute("SELECT COUNT(*) FROM atlas_pins WHERE author = ? AND created_at > ?",
                      (author, time.time() - 86400)).fetchone()[0]
    if today >= MAX_PINS_PER_DAY:
        raise ValueError(f"That's {MAX_PINS_PER_DAY} notes today. Try again tomorrow.")
    cur = c.execute("INSERT INTO atlas_pins (song_key, author, text, created_at) VALUES (?, ?, ?, ?)",
                    (song, author, text, time.time()))
    return {"id": cur.lastrowid, "song_key": song, "text": text}


def delete_pin(pin_id: int, author: str) -> bool:
    cur = store.connect().execute("DELETE FROM atlas_pins WHERE id = ? AND author = ?", (pin_id, author))
    return cur.rowcount > 0
