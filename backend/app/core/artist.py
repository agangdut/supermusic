"""
"Where does my track land?" for artists: upload a song and see where it would sit
on the community atlas, which galaxy it belongs to, the songs it sits next to, and
which public maps are full of those songs (the listeners most likely to like it).

How a new song is placed:
  * With the CLAP service running and atlas songs that have a sound description,
    the upload gets one too and is matched by how it sounds.
  * Otherwise it's matched on what can be measured from the audio itself (tempo,
    key, energy, brightness) plus the genre the artist types in.

The audio is analysed and then thrown away; only the result is kept.
"""
from __future__ import annotations

import json
import math
import secrets
import tempfile
import time
from collections import Counter
from typing import Any, Dict, List, Optional

import numpy as np

from app.core import atlas, sound, store
from app.core.library_import import analyse_audio
from app.core.music_map import parse_key

NEIGHBOURS = 12


def analyse_file(data: bytes, suffix: str) -> Dict[str, Any]:
    import librosa

    with tempfile.NamedTemporaryFile(suffix=suffix) as f:
        f.write(data)
        f.flush()
        y, sr = librosa.load(f.name, sr=22050, mono=True, duration=240)
    # The middle of the song says more than a quiet intro
    if len(y) > sr * 90:
        mid = len(y) // 2
        y = y[mid - sr * 45: mid + sr * 45]
    return analyse_audio(y, sr)


def _camelot_distance(a: Optional[str], b: Optional[str]) -> float:
    """0 = same key, 1 = a step away on the Camelot wheel ... up to 6, then +1 for major vs minor."""
    if not a or not b:
        return 3.0
    na, nb = int(a[:-1]), int(b[:-1])
    d = min(abs(na - nb), 12 - abs(na - nb))
    return d + (0 if a[-1] == b[-1] else 1)


def _feature_distance(t: Dict[str, Any], f: Dict[str, Any], camelot: Optional[str], genres: List[str]) -> float:
    d = 0.0
    if f.get("bpm") and t.get("bpm"):
        x, y = float(f["bpm"]), float(t["bpm"])
        while x > y * 1.41:
            x /= 2
        while x < y / 1.41:
            x *= 2
        d += abs(math.log(x / y)) * 6
    else:
        d += 1.0
    d += _camelot_distance(camelot, t.get("camelot")) * 0.25
    for name in ("energy", "brightness"):
        if f.get(name) is not None and t.get(name) is not None:
            d += abs(float(f[name]) - float(t[name])) * 2
    if genres:
        tg = {g.strip().lower() for g in (t.get("genre") or "").split(",") if g.strip()}
        d += 0 if tg & genres else 1.5
    return d


def land(data: bytes, suffix: str, *, title: str, artist: Optional[str], genre: Optional[str],
         owner: Optional[str], public: bool) -> Dict[str, Any]:
    feats = analyse_file(data, suffix)
    if not feats:
        raise ValueError("That file is too short (or silent) to analyse. Upload at least 5 seconds of audio.")
    the_atlas = atlas.get()
    tracks = the_atlas.get("tracks") or []
    if len(tracks) < 3:
        raise ValueError("The community atlas is empty so far. It fills up as people list their maps publicly.")

    k = parse_key(feats.get("key"))
    camelot = k.camelot if k else None
    genres = {g.strip().lower() for g in (genre or "").split(",") if g.strip()}

    basis = "features"
    order: List[int] = []
    scores: Dict[int, float] = {}
    vectors = atlas.sound_vectors()
    if vectors and sound.available():
        try:
            vec = sound.embed_audio(data)
            vec = vec / (np.linalg.norm(vec) or 1)
            ids, mat = [], []
            for i, t in enumerate(tracks):
                v = sound.decode(vectors.get(t.get("song_key")))
                if v is not None and v.size == vec.size:
                    ids.append(i)
                    mat.append(v)
            if ids:
                sims = np.asarray(mat) @ vec
                best = np.argsort(-sims)[:NEIGHBOURS]
                order = [ids[j] for j in best]
                scores = {ids[j]: float(sims[j]) for j in best}
                basis = "sound"
        except RuntimeError:
            pass
    if not order:
        dist = [(_feature_distance(t, feats, camelot, genres), i) for i, t in enumerate(tracks)]
        dist.sort()
        order = [i for _, i in dist[:NEIGHBOURS]]
        scores = {i: round(1 / (1 + d), 3) for d, i in dist[:NEIGHBOURS]}

    near = [tracks[i] for i in order]
    top = near[: max(3, NEIGHBOURS // 2)]
    cluster = Counter(t["cluster"] for t in top).most_common(1)[0][0]
    cinfo = next((c for c in the_atlas.get("clusters", []) if c["id"] == cluster), {})
    pos = {ax: round(float(np.mean([t[ax] for t in top])), 2) for ax in ("x", "y", "z")}

    maps = atlas.song_maps([t.get("song_key") for t in near if t.get("song_key")])
    fans: Counter = Counter()
    info: Dict[str, Dict[str, Any]] = {}
    for t in near:
        for m in maps.get(t.get("song_key"), []):
            fans[m["id"]] += 1
            info[m["id"]] = m
    listeners = [{**info[s], "songs_near": n} for s, n in fans.most_common(8)]

    result = {
        "features": {**feats, "camelot": camelot},
        "basis": basis,
        "galaxy": {"id": cluster, "name": cinfo.get("name"), "label": cinfo.get("label"), "size": cinfo.get("size")},
        "position": pos,
        "neighbours": [{"id": t["id"], "title": t["title"], "artist": t.get("artist"), "genre": t.get("genre"),
                        "bpm": t.get("bpm"), "key": t.get("key"), "score": round(scores.get(i, 0), 3),
                        "listeners": t.get("listeners")} for i, t in zip(order, near)],
        "listeners": listeners,
    }
    track_id = secrets.token_urlsafe(6)
    store.connect().execute(
        "INSERT INTO artist_tracks (id, owner, title, artist, result, public, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (track_id, owner, title.strip()[:120], (artist or "").strip()[:120] or None, json.dumps(result),
         1 if public and owner else 0, time.time()))
    return {"id": track_id, "title": title, "artist": artist, "public": bool(public and owner), **result}


def _row(r) -> Dict[str, Any]:
    return {"id": r["id"], "owner": r["owner"], "title": r["title"], "artist": r["artist"],
            "public": bool(r["public"]), "created": r["created_at"], **json.loads(r["result"])}


def get(track_id: str) -> Optional[Dict[str, Any]]:
    r = store.connect().execute("SELECT * FROM artist_tracks WHERE id = ?", (track_id,)).fetchone()
    return _row(r) if r else None


def by_owner(username: str, include_private: bool = False) -> List[Dict[str, Any]]:
    q = "SELECT * FROM artist_tracks WHERE owner = ?" + ("" if include_private else " AND public = 1")
    return [_row(r) for r in store.connect().execute(q + " ORDER BY created_at DESC", (username,))]


def public_tracks(limit: int = 200) -> List[Dict[str, Any]]:
    rows = store.connect().execute(
        "SELECT * FROM artist_tracks WHERE public = 1 ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [_row(r) for r in rows]


def set_public(track_id: str, owner: str, public: bool) -> bool:
    cur = store.connect().execute("UPDATE artist_tracks SET public = ? WHERE id = ? AND owner = ?",
                                  (1 if public else 0, track_id, owner))
    return cur.rowcount > 0


def delete(track_id: str, owner: str) -> bool:
    cur = store.connect().execute("DELETE FROM artist_tracks WHERE id = ? AND owner = ?", (track_id, owner))
    return cur.rowcount > 0
