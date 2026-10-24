"""
Getting listeners to check song stats.

Fixing a stat used to mean opening a form. Here it is one tap:

  * Quick checks. "Is this song about 120 BPM?" Yes saves a vote for that value;
    No offers the likely alternatives (half or double time, the relative key, the
    year either side) and a tap-along tempo button on the page.
  * Asked on songs you know. The map sends its most-played songs and gets back the
    ones with a stat listeners haven't settled yet, which you haven't answered.
  * Impact. How many public maps your agreed fixes reach, and how many songs you
    helped settle this month.
  * Rewards for agreed fixes only: badges per stat and genre ("Tempo checker:
    Jazz") and milestones (a week of Plus after 25 agreed fixes...). A fix nobody
    else agrees with earns nothing, so there is nothing to gain from guessing.

A stat is "settled" once SETTLED listeners agree on it; after that nobody is asked
about it again.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

from app.core import atlas, community, store
from app.core.genres import GENRES
from app.core.library_import import song_key
from app.core.music_map import Key, parse_key

SETTLED = 3                                # agreeing listeners after which a stat isn't asked about any more
CHECK_FIELDS = ("bpm", "key", "genre", "year")
QUIZ_FIELDS = ("genre", "year")            # things a quiz player can know without hearing the song
BADGE_AT = 5                               # agreed fixes of one stat, in one genre, for a badge
BADGE_NAMES = {"bpm": "Tempo checker", "key": "Key finder", "genre": "Genre guide", "year": "Time keeper",
               "energy": "Mood reader", "danceability": "Mood reader", "valence": "Mood reader",
               "acousticness": "Mood reader", "vibes": "Vibe tagger"}
# Milestones of agreed fixes. Plus and Studio credits aren't on sale yet, so these are
# kept as "earned" and handed out when they are.
REWARDS = [(25, "plus_week", "A week of Plus"), (50, "studio_10", "10 Studio credits"),
           (100, "plus_month", "A month of Plus"), (250, "plus_year", "A year of Plus")]


# ---------------------------------------------------------------------------
# Where each stat stands
# ---------------------------------------------------------------------------

def _rows(keys: List[str]) -> Dict[tuple, list]:
    out: Dict[tuple, list] = defaultdict(list)
    c = store.connect()
    for chunk in community._chunks(sorted(set(keys))):
        marks = ",".join("?" * len(chunk))
        for r in c.execute(f"SELECT song_key, field, voter, ip_hash, value, created_at FROM song_votes "
                           f"WHERE song_key IN ({marks})", chunk):
            out[(r["song_key"], r["field"])].append(r)
    return out


def _facts(keys: List[str]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = defaultdict(dict)
    c = store.connect()
    for chunk in community._chunks(sorted(set(keys))):
        marks = ",".join("?" * len(chunk))
        for r in c.execute(f"SELECT song_key, field, value FROM song_facts WHERE song_key IN ({marks})", chunk):
            out[r["song_key"]][r["field"]] = json.loads(r["value"])
    return out


def _state(rows: list) -> Dict[str, Any]:
    """{"agreed": value or None, "agree": n}: what listeners agree on for one stat of one song."""
    if not rows:
        return {"agreed": None, "agree": 0}
    k = (rows[0]["song_key"], rows[0]["field"])
    a = community.agree(k[1], community._one_per_listener(rows).get(k, []))
    return {"agreed": a["value"] if a else None, "agree": a["agree"] if a else 0}


def _usable(field: str, value: Any) -> Any:
    """`value` in the form a vote takes, or None when it isn't a sensible answer to ask about."""
    if value is None or value == "" or value == []:
        return None
    try:
        return community.normalise(field, value)
    except community.VoteError:
        return None


def reach(keys: List[str]) -> Dict[str, int]:
    """{song_key: public maps it's on}."""
    try:
        return {k: len(v) for k, v in atlas.song_maps(keys).items()}
    except Exception:
        return {k: 0 for k in keys}


# ---------------------------------------------------------------------------
# Which songs to ask about
# ---------------------------------------------------------------------------

def _open_fields(key: str, known: Dict[str, Any], rows, facts, voter: Optional[str],
                 fields=CHECK_FIELDS) -> List[tuple]:
    """[(field, value to ask about)] for stats of one song that aren't settled and this listener hasn't answered."""
    out = []
    for f in fields:
        r = rows.get((key, f), [])
        if voter and any(x["voter"] == voter for x in r):
            continue
        st = _state(r)
        if st["agree"] >= SETTLED:
            continue
        v = _usable(f, st["agreed"]) or _usable(f, facts.get(key, {}).get(f)) or _usable(f, known.get(f))
        if v is not None:
            out.append((f, v))
    return out


def needs_check(songs: List[Dict[str, Any]], voter: Optional[str], limit: int = 50) -> List[Dict[str, Any]]:
    """Of these songs (most played first), the ones with a stat worth a quick check, in the same order."""
    songs = [s for s in songs if str(s.get("title") or "").strip()]
    keys = [song_key(s.get("artist") or "", s["title"]) for s in songs]
    rows, facts = _rows(keys), _facts(keys)
    out = []
    for s, k in zip(songs, keys):
        fields = _open_fields(k, s, rows, facts, voter)
        if fields:
            out.append({"artist": s.get("artist") or "", "title": s["title"], "fields": [f for f, _ in fields]})
            if len(out) >= limit:
                break
    return out


# ---------------------------------------------------------------------------
# The question
# ---------------------------------------------------------------------------

def _chord(k: Key) -> List[int]:
    """MIDI notes of the key's home chord, around middle C, for the page to play."""
    root = 60 + k.pitch if k.pitch < 7 else 48 + k.pitch
    return [root, root + (3 if k.minor else 4), root + 7]


def _relative(k: Key) -> Key:
    return Key((k.pitch + 3) % 12, False) if k.minor else Key((k.pitch + 9) % 12, True)


def _ask(field: str, value: Any, title: str) -> Dict[str, Any]:
    q: Dict[str, Any] = {"field": field, "label": community.LABELS[field], "value": value}
    if field == "bpm":
        q["prompt"] = f"Is “{title}” about {round(value)} BPM?"
        q["shown"] = f"{round(value)} BPM"
        q["alternatives"] = [{"value": v, "label": f"{round(v)} BPM ({name})"} for v, name in
                             ((round(value / 2, 1), "half time"), (round(value * 2, 1), "double time")) if 40 <= v <= 250]
    elif field == "key":
        k = parse_key(value)
        rel = _relative(k)
        q["prompt"] = f"Does “{title}” sit in {k.long_name}?"
        q["shown"] = k.long_name
        q["chord"] = _chord(k)
        q["alternatives"] = [{"value": rel.name, "label": rel.long_name, "chord": _chord(rel)}]
    elif field == "genre":
        shown = " / ".join(value)
        q["prompt"] = f"Is “{title}” {shown}?"
        q["shown"] = shown
        q["alternatives"] = [{"value": [g], "label": g} for g in GENRES if g not in value]
    else:  # year
        q["prompt"] = f"Did “{title}” come out in {value}?"
        q["shown"] = str(value)
        q["alternatives"] = [{"value": y, "label": str(y)} for y in (value - 1, value + 1) if y <= time.gmtime().tm_year]
    return q


def question(artist: str, title: str, known: Dict[str, Any], voter: Optional[str],
             fields=CHECK_FIELDS) -> Optional[Dict[str, Any]]:
    """One yes/no check for this song, or None when there's nothing left to ask this listener."""
    if not str(title or "").strip():
        return None
    key = song_key(artist, title)
    rows, facts = _rows([key]), _facts([key])
    open_ = _open_fields(key, known, rows, facts, voter, fields)
    if not open_:
        return None
    field, value = open_[0]
    q = _ask(field, value, title)
    st = _state(rows.get((key, field), []))
    return {**q, "artist": artist, "title": title, "agree": st["agree"], "settled_at": SETTLED,
            "reach": reach([key]).get(key, 0), "left": len(open_)}


def quiz_check(voter: Optional[str], rng) -> Optional[Dict[str, Any]]:
    """A bonus "help check" question for the quiz, about a song on the community atlas."""
    tracks = [t for t in atlas.get().get("tracks", []) if t.get("title")]
    rng.shuffle(tracks)
    for t in tracks[:60]:
        q = question(t.get("artist") or "", t["title"], {"genre": t.get("genre"), "year": t.get("year")},
                     voter, QUIZ_FIELDS)
        if q:
            return q
    return None


# ---------------------------------------------------------------------------
# After an answer, and over time
# ---------------------------------------------------------------------------

def after_vote(artist: str, title: str, field: str) -> Dict[str, Any]:
    """What a vote just did: {"agree", "agreed", "settled", "reach"}."""
    key = song_key(artist, title)
    st = _state(_rows([key]).get((key, field), []))
    return {"agree": st["agree"], "agreed": st["agreed"] is not None, "settled": st["agree"] >= SETTLED,
            "settled_at": SETTLED, "reach": reach([key]).get(key, 0)}


def _genre_of(key: str, rows, facts) -> Optional[str]:
    g = _state(rows.get((key, "genre"), []))["agreed"] or facts.get(key, {}).get("genre")
    if isinstance(g, str):
        g = g.split(";")
    g = [x for x in (g or []) if x in GENRES]
    return g[0] if g else None


def agreed_fixes(voters: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """{voter: [{song_key, field, genre, agreed_at}]}: the fixes of these voters that listeners agree with."""
    from app.core.social import _matches

    voters = [v for v in voters if v]
    if not voters:
        return {}
    c = store.connect()
    marks = ",".join("?" * len(voters))
    mine = c.execute(f"SELECT song_key, field, voter, value, created_at FROM song_votes WHERE voter IN ({marks})",
                     voters).fetchall()
    keys = sorted({r["song_key"] for r in mine})
    rows, facts = _rows(keys), _facts(keys)
    states = {k: _state(v) for k, v in rows.items()}
    out: Dict[str, List[Dict[str, Any]]] = {v: [] for v in voters}
    for r in mine:
        k = (r["song_key"], r["field"])
        agreed = states.get(k, {}).get("agreed")
        if agreed is None or not _matches(r["field"], json.loads(r["value"]), agreed):
            continue
        # When it was settled: the latest vote among the agreeing ones is a fair stand-in
        when = max(x["created_at"] for x in rows[k])
        out[r["voter"]].append({"song_key": r["song_key"], "field": r["field"],
                                "genre": _genre_of(r["song_key"], rows, facts), "agreed_at": when})
    return out


def badges(fixes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """ "Tempo checker: Jazz" for BADGE_AT agreed tempo fixes on jazz songs, and so on."""
    counts: Dict[tuple, int] = defaultdict(int)
    for f in fixes:
        if f["genre"]:
            counts[(BADGE_NAMES.get(f["field"], "Checker"), f["genre"])] += 1
    out = [{"id": f"{name}:{genre}".lower().replace(" ", "-"), "label": f"{name}: {genre}",
            "hint": f"{n} agreed {name.split()[0].lower()} fixes on {genre} songs", "count": n}
           for (name, genre), n in counts.items() if n >= BADGE_AT]
    return sorted(out, key=lambda b: -b["count"])


def rewards(agreed: int) -> Dict[str, Any]:
    earned = [{"id": i, "label": label, "at": at} for at, i, label in REWARDS if agreed >= at]
    nxt = next(({"id": i, "label": label, "at": at, "left": at - agreed} for at, i, label in REWARDS if agreed < at), None)
    return {"earned": earned, "next": nxt}


def impact(voter: str) -> Dict[str, Any]:
    """What one listener's checking has done: agreed fixes, public maps reached, songs settled this month."""
    fixes = agreed_fixes([voter]).get(voter, [])
    keys = sorted({f["song_key"] for f in fixes})
    try:
        maps = atlas.song_maps(keys)
    except Exception:
        maps = {}
    reached = {m["id"] for k in keys for m in maps.get(k, [])}
    month = time.time() - 30 * 86400
    return {"agreed": len(fixes), "songs": len(keys), "maps_reached": len(reached),
            "settled_this_month": len({f["song_key"] for f in fixes if f["agreed_at"] > month}),
            "badges": badges(fixes), "rewards": rewards(len(fixes))}


def top_checkers(limit: int = 3) -> Dict[str, List[Dict[str, Any]]]:
    """{genre: [{username, agreed}]}: who has the most agreed fixes on each genre's songs."""
    c = store.connect()
    voters = [r[0] for r in c.execute("SELECT DISTINCT voter FROM song_votes WHERE voter LIKE 'user:%'")]
    by_genre: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for v, fixes in agreed_fixes(voters).items():
        for f in fixes:
            if f["genre"]:
                by_genre[f["genre"]][v[5:]] += 1
    return {g: [{"username": u, "agreed": n} for u, n in sorted(people.items(), key=lambda x: -x[1])[:limit]]
            for g, people in sorted(by_genre.items())}
