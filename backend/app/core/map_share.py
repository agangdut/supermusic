"""Shared Music Maps: a snapshot of a map that anyone with the link can open.

Accounts and jobs still live in memory, so shares are plain files on disk instead
(data/shared_maps/<id>/), which survive a restart because docker compose mounts data/.
Each share holds:

  meta.json      title, who shared it, when, whether it's listed on /maps
  map.json.gz    the map exactly as the sharer saw it (tracks, clusters, links, stats)
  library.csv    the songs behind it, so visitors can Remap, see "songs you may like",
                 search by sound and start a radio station

There are no accounts to own a share, so creating one returns a secret delete token;
only its hash is stored. The browser that shared the map keeps the token.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
import secrets
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from app.core import map_showcase, store
from app.core.config import settings
from app.core.music_map import ALIASES

ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,24}$")

# Listening data someone may not want public: how often they play each song, skips,
# likes, when they first/last played it, which playlists it's on
LISTENING_FIELDS = ("plays", "rating", "liked", "skips", "first_played", "last_played", "added", "playlists")
LISTENING_COLUMNS = {a for f in LISTENING_FIELDS for a in ALIASES[f]} | {"ms_played", "minutes_played", "engagement"}
TRACK_LISTENING_KEYS = {"plays", "engagement", "skips", "liked", "first_played", "last_played", "added", "playlists"}

SPOTIFY_PREFIXES = ("https://open.spotify.com/",)
YOUTUBE_PREFIXES = ("https://www.youtube.com/", "https://youtube.com/", "https://music.youtube.com/", "https://youtu.be/")


def share_dir() -> Path:
    d = settings.DATA_DIR / "shared_maps"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _folder(share_id: str) -> Optional[Path]:
    if not ID_RE.match(share_id or ""):
        return None
    f = share_dir() / share_id
    return f if (f / "meta.json").is_file() else None


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def clean_map(result: Dict[str, Any], include_listening: bool) -> Dict[str, Any]:
    """What visitors get. The map comes from the sharer's browser, so links are checked
    (a shared map must not carry a javascript: link) and listening data is dropped on request."""
    tracks = result.get("tracks")
    if not isinstance(tracks, list) or not tracks or not all(isinstance(t, dict) for t in tracks):
        raise ValueError("That doesn't look like a Music Map (no tracks).")
    out = dict(result)
    clean_tracks = []
    for t in tracks:
        t = dict(t)
        for key, prefixes in (("spotify_url", SPOTIFY_PREFIXES), ("youtube_url", YOUTUBE_PREFIXES)):
            v = t.get(key)
            if v is not None and not (isinstance(v, str) and v.startswith(prefixes)):
                t.pop(key)
        if not include_listening:
            for k in TRACK_LISTENING_KEYS:
                t.pop(k, None)
        clean_tracks.append(t)
    out["tracks"] = clean_tracks
    meta = dict(out.get("meta") or {})
    meta.pop("library_csv", None)  # a path on the sharer's server; visitors use the share's copy
    if not include_listening:
        out["insights"] = []
        out["recommendations"] = []
        out.pop("stats", None)  # every breakdown in it is weighted by plays
        out["clusters"] = [{k: v for k, v in c.items() if k not in ("listening_share", "lift")}
                           for c in out.get("clusters") or []]
        meta["has_listening_data"] = False
    out["meta"] = meta
    return out


def _clean_library(df: pd.DataFrame, include_listening: bool) -> pd.DataFrame:
    if include_listening:
        return df
    return df[[c for c in df.columns if str(c).lower().strip() not in LISTENING_COLUMNS]]


def create(result: Dict[str, Any], *, title: str, by: Optional[str], listed: bool,
           include_listening: bool, library: Optional[Path]) -> Dict[str, Any]:
    cleaned = clean_map(result, include_listening)
    share_id = secrets.token_urlsafe(6)  # 8 characters, ~280 trillion possibilities
    token = secrets.token_urlsafe(18)
    folder = share_dir() / share_id
    folder.mkdir(parents=True)
    try:
        has_library = False
        if library is not None:
            df = pd.read_csv(library)
            _clean_library(df, include_listening).to_csv(folder / "library.csv", index=False)
            has_library = True
        with gzip.open(folder / "map.json.gz", "wt", encoding="utf-8") as f:
            json.dump(cleaned, f, separators=(",", ":"))
        clusters = sorted(cleaned.get("clusters") or [], key=lambda c: -c.get("size", 0))
        meta = {
            "id": share_id,
            "title": title,
            "by": by or None,
            "listed": listed,
            "created": int(time.time()),
            "songs": len(cleaned["tracks"]),
            "clusters": [c.get("label") for c in clusters[:4] if c.get("label")],
            "listening": include_listening,
            "has_library": has_library,
            "token_sha256": _hash(token),
        }
        _add_extras(folder, meta, cleaned)
        (folder / "meta.json").write_text(json.dumps(meta))
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return {"id": share_id, "delete_token": token, **public_meta(meta)}


def _add_extras(folder: Path, meta: Dict[str, Any], m: Dict[str, Any]) -> None:
    """The picture and showcase stats for the Shared maps page. A failure here must never
    lose the share itself, so it just leaves them out."""
    try:
        meta["showcase"] = map_showcase.showcase(m)
    except Exception:
        meta["showcase"] = None
    try:
        map_showcase.render_picture(m, folder / "picture.png")
        meta["picture"] = True
    except Exception:
        meta["picture"] = False


def _ensure_extras(folder: Path, meta: Dict[str, Any]) -> Dict[str, Any]:
    """Maps shared before pictures existed get theirs the first time they're listed."""
    if "showcase" in meta and "picture" in meta:
        return meta
    with gzip.open(folder / "map.json.gz", "rt", encoding="utf-8") as fh:
        m = json.load(fh)
    _add_extras(folder, meta, m)
    (folder / "meta.json").write_text(json.dumps(meta))
    return meta


def picture_path(share_id: str) -> Optional[Path]:
    f = _folder(share_id)
    if not f:
        return None
    _ensure_extras(f, json.loads((f / "meta.json").read_text()))
    p = f / "picture.png"
    return p if p.is_file() else None


# ---- upvotes -------------------------------------------------------------------------

MAX_VOTES_PER_NETWORK = 3  # browser ids are free to make; one home network can't stuff a map


class VoteError(ValueError):
    pass


def votes(share_ids: List[str], voter: Optional[str]) -> Dict[str, Dict[str, Any]]:
    """{share_id: {"votes": n, "voted": bool}}."""
    if not share_ids:
        return {}
    c = store.connect()
    marks = ",".join("?" * len(share_ids))
    counts = dict(c.execute(f"SELECT share_id, COUNT(*) FROM map_votes WHERE share_id IN ({marks}) GROUP BY share_id",
                            share_ids).fetchall())
    mine = set()
    if voter:
        mine = {r[0] for r in c.execute(f"SELECT share_id FROM map_votes WHERE voter = ? AND share_id IN ({marks})",
                                        [voter, *share_ids])}
    return {s: {"votes": int(counts.get(s, 0)), "voted": s in mine} for s in share_ids}


def vote(share_id: str, voter: str, ip: Optional[str], up: bool) -> Dict[str, Any]:
    """Upvote a map (up=True) or take the upvote back. One per listener."""
    if not _folder(share_id):
        raise LookupError(share_id)
    with store.tx() as c:
        if not up:
            c.execute("DELETE FROM map_votes WHERE share_id = ? AND voter = ?", (share_id, voter))
        elif not c.execute("SELECT 1 FROM map_votes WHERE share_id = ? AND voter = ?", (share_id, voter)).fetchone():
            if ip and c.execute("SELECT COUNT(*) FROM map_votes WHERE share_id = ? AND ip_hash = ?",
                                (share_id, ip)).fetchone()[0] >= MAX_VOTES_PER_NETWORK:
                raise VoteError("This map already has several upvotes from your network.")
            c.execute("INSERT INTO map_votes (share_id, voter, ip_hash, created_at) VALUES (?, ?, ?, ?)",
                      (share_id, voter, ip, time.time()))
    return votes([share_id], voter)[share_id]


def public_meta(meta: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in meta.items() if k != "token_sha256"}


def read_meta(share_id: str) -> Optional[Dict[str, Any]]:
    f = _folder(share_id)
    return json.loads((f / "meta.json").read_text()) if f else None


def get(share_id: str) -> Optional[Dict[str, Any]]:
    f = _folder(share_id)
    if not f:
        return None
    meta = json.loads((f / "meta.json").read_text())
    with gzip.open(f / "map.json.gz", "rt", encoding="utf-8") as fh:
        result = json.load(fh)
    return {**public_meta(meta), "map": result}


def library_path(share_id: str) -> Optional[Path]:
    f = _folder(share_id)
    p = f / "library.csv" if f else None
    return p if p and p.is_file() else None


def list_public(limit: int = 50, sort: str = "new", voter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Listed maps with their upvotes. sort: "new" (newest first) or "top" (most upvoted)."""
    metas = []
    for meta_file in share_dir().glob("*/meta.json"):
        try:
            meta = json.loads(meta_file.read_text())
            if meta.get("listed"):
                metas.append(public_meta(_ensure_extras(meta_file.parent, meta)))
        except Exception:
            continue
    v = votes([m["id"] for m in metas], voter)
    for m in metas:
        m.update(v.get(m["id"], {"votes": 0, "voted": False}))
    if sort == "top":
        metas.sort(key=lambda m: (-m["votes"], -m.get("created", 0)))
    else:
        metas.sort(key=lambda m: -m.get("created", 0))
    return metas[:limit]


def delete(share_id: str, token: str) -> bool:
    """True when the token matched and the share is gone."""
    f = _folder(share_id)
    if not f:
        return False
    meta = json.loads((f / "meta.json").read_text())
    if not secrets.compare_digest(meta.get("token_sha256", ""), _hash(token or "")):
        return False
    shutil.rmtree(f, ignore_errors=True)
    store.connect().execute("DELETE FROM map_votes WHERE share_id = ?", (share_id,))
    return True
