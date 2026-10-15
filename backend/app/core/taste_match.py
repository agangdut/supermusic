"""
"Listeners like you": how close your library is to each map people have shared
publicly, and songs from the closest ones that you don't have yet.

How close two libraries are is measured on artists, not exact songs: two
people who both love an artist rarely saved the very same tracks. Each library
becomes a list of "how much of my listening is this artist" (play counts when
the file has them, otherwise one per song), and the match is the cosine
similarity of the two lists: 100% means the same artists in the same
proportions, 0% means no artist in common.
"""
from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from app.core import map_share
from app.core.library_import import song_key
from app.core.music_map import _find

_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def _first_artist(a: Any) -> str:
    return song_key(a, "").split("|")[0]


def profile(df: pd.DataFrame) -> Dict[str, Any]:
    """Artist weights, song keys and a row per song (for picks) for one library."""
    t_col, a_col, p_col = _find(df, "title"), _find(df, "artist"), _find(df, "plays")
    if t_col is None or a_col is None:
        return {"artists": Counter(), "songs": set(), "names": {}, "rows": []}
    plays = pd.to_numeric(df[p_col], errors="coerce").fillna(0) if p_col else pd.Series(0, index=df.index)
    use_plays = bool(p_col) and plays.sum() > 0
    artists: Counter = Counter()
    names: Dict[str, str] = {}
    rows = []
    songs = set()
    for title, artist, n in zip(df[t_col], df[a_col], plays):
        if pd.isna(title) or pd.isna(artist):
            continue
        a = _first_artist(artist)
        if not a:
            continue
        artists[a] += float(n) if use_plays else 1.0
        names.setdefault(a, str(artist).split(",")[0].strip())
        k = song_key(artist, title)
        if k not in songs:
            songs.add(k)
            rows.append({"key": k, "title": str(title), "artist": str(artist), "artist_key": a, "plays": float(n)})
    return {"artists": artists, "songs": songs, "names": names, "rows": rows}


def _cosine(a: Counter, b: Counter) -> float:
    dot = sum(v * b.get(k, 0.0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def _share_profile(share_id: str) -> Optional[Dict[str, Any]]:
    path = map_share.library_path(share_id)
    if not path:
        return None
    mtime = Path(path).stat().st_mtime
    hit = _cache.get(share_id)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        prof = profile(pd.read_csv(path))
    except Exception:
        return None
    _cache[share_id] = (mtime, prof)
    return prof


def compare(mine: Dict[str, Any], theirs: Dict[str, Any], picks: int = 8) -> Dict[str, Any]:
    both_artists = sorted(set(mine["artists"]) & set(theirs["artists"]),
                          key=lambda a: -(mine["artists"][a] / max(1, sum(mine["artists"].values()))
                                          + theirs["artists"][a] / max(1, sum(theirs["artists"].values()))))
    both_songs = mine["songs"] & theirs["songs"]
    # Their songs you don't have: artists you already like first, then what they play most
    yours = mine["artists"]
    candidates = [r for r in theirs["rows"] if r["key"] not in mine["songs"]]
    candidates.sort(key=lambda r: (-(r["artist_key"] in yours), -r["plays"]))
    seen_artists: Counter = Counter()
    chosen = []
    for r in candidates:
        if seen_artists[r["artist_key"]] >= 2:  # no more than two by one artist
            continue
        seen_artists[r["artist_key"]] += 1
        chosen.append({"title": r["title"], "artist": r["artist"], "you_like_artist": r["artist_key"] in yours})
        if len(chosen) >= picks:
            break
    return {
        "match": round(100 * _cosine(mine["artists"], theirs["artists"])),
        "shared_songs": len(both_songs),
        "shared_artists": len(both_artists),
        "top_shared_artists": [theirs["names"].get(a, a) for a in both_artists[:5]],
        "picks": chosen,
    }


def matches(df: pd.DataFrame, exclude: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """Publicly listed shared maps, closest to this library first."""
    mine = profile(df)
    out = []
    for meta in map_share.list_public(limit=200):
        sid = meta.get("id")
        if not sid or sid == exclude or not meta.get("has_library"):
            continue
        theirs = _share_profile(sid)
        if not theirs or not theirs["rows"]:
            continue
        c = compare(mine, theirs)
        if c["shared_artists"] == 0:
            continue
        out.append({"share_id": sid, "title": meta.get("title"), "by": meta.get("by"),
                    "songs": len(theirs["rows"]), **c})
    out.sort(key=lambda m: (-m["match"], -m["shared_songs"]))
    return out[:limit]
