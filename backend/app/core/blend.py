"""
Blend two Music Maps: both libraries drawn as one map, so you can see where your
taste and a friend's overlap.

Every song is tagged by whose library it's in: "you", "them" or "both". Galaxies
where both of you have plenty of songs are the common ground; galaxies that are
nearly all one person are what that person could show the other.

Listening data (play counts, likes, dates) is left out, so neither library's
habits outweigh the other's and nobody's plays are shown to the other person.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from app.core import map_share, taste_match
from app.core.library_import import song_key
from app.core.music_map import MapOptions, _find, build_map

MAX_SONGS = 50_000


def _songs(df: pd.DataFrame) -> pd.DataFrame:
    keep = [c for c in df.columns if str(c).lower().strip() not in map_share.LISTENING_COLUMNS]
    out = df[keep].dropna(how="all").copy()
    t_col, a_col = _find(out, "title"), _find(out, "artist")
    if t_col is None:
        raise ValueError("A library needs a title column to be compared.")
    artists = out[a_col] if a_col else pd.Series([""] * len(out), index=out.index)
    out["_key"] = [song_key(a, t) for a, t in zip(artists, out[t_col])]
    # Both files must use the same column names to stack: rename to the plain field names
    rename = {}
    for f in ("title", "artist", "album", "genre", "key", "mode", "bpm", "year"):
        c = _find(out, f)
        if c is not None and c != f:
            rename[c] = f
    out = out.rename(columns=rename)
    return out.loc[:, ~out.columns.duplicated()].drop_duplicates("_key")


def blend(mine: pd.DataFrame, theirs: pd.DataFrame, weights: Dict[str, float] = None) -> Dict[str, Any]:
    a, b = _songs(mine), _songs(theirs)
    in_a, in_b = set(a["_key"]), set(b["_key"])
    union = pd.concat([a, b[~b["_key"].isin(in_a)]], ignore_index=True, sort=False)
    if len(union) > MAX_SONGS:
        raise ValueError(f"Together these libraries have {len(union):,} songs; blends are limited to {MAX_SONGS:,}.")
    keys = union["_key"].tolist()
    result = build_map(union.drop(columns=["_key"]).reset_index(drop=True), MapOptions(weights=weights or {}))

    counts = {"you": 0, "them": 0, "both": 0}
    per_cluster: Dict[int, Dict[str, int]] = {}
    for t, k in zip(result["tracks"], keys):
        who = "both" if k in in_a and k in in_b else "you" if k in in_a else "them"
        t["who"] = who
        counts[who] += 1
        pc = per_cluster.setdefault(t["cluster"], {"you": 0, "them": 0, "both": 0})
        pc[who] += 1

    galaxies: List[Dict[str, Any]] = []
    for c in result["clusters"]:
        pc = per_cluster.get(c["id"], {"you": 0, "them": 0, "both": 0})
        total = sum(pc.values()) or 1
        yours = (pc["you"] + pc["both"]) / total
        theirs_share = (pc["them"] + pc["both"]) / total
        c["blend"] = pc
        kind = "shared" if min(yours, theirs_share) >= 0.3 else "yours" if yours > theirs_share else "theirs"
        c["blend_kind"] = kind
        galaxies.append({"id": c["id"], "name": c.get("name"), "label": c.get("label"), "kind": kind, **pc})

    pa, pb = taste_match.profile(mine), taste_match.profile(theirs)
    them_for_you = taste_match.compare(pa, pb)
    you_for_them = taste_match.compare(pb, pa)
    result["recommendations"], result["insights"] = [], []
    result.pop("stats", None)
    result["blend"] = {
        "match": them_for_you["match"],
        "counts": counts,
        "shared_artists": them_for_you["shared_artists"],
        "top_shared_artists": them_for_you["top_shared_artists"],
        "for_you": them_for_you["picks"],
        "for_them": you_for_them["picks"],
        "galaxies": sorted(galaxies, key=lambda g: -(g["you"] + g["them"] + g["both"])),
    }
    result["meta"] = {**result.get("meta", {}), "source": "blend", "has_listening_data": False}
    return result
