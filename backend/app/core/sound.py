"""
"Sound" vectors for the Music Map: one CLAP embedding per song, describing
how it actually sounds (instruments, production, vocals, energy), so the map
can group songs by sound and not only by key, tempo and tags.

The vectors come from the CLAP service (services/clap) and are stored in the
library CSV as a compact text column `sound` (base64 of 512 float16 values),
so remapping an imported library doesn't need the service again.

Audio comes from each song's 30-second Deezer preview (found via the same
cached lookup the importer uses) or from a `local_path` column when the CSV
points at files on disk. On a 560-song test, CLAP neighbours shared the song's
genre 39% of the time, against 16% for key/tempo/energy features
(docs/embedding-comparison.md).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, List, Optional, Sequence

import numpy as np
import pandas as pd

URL = os.getenv("CLAP_URL", "http://clap:8300")
COLUMN = "sound"


# ---------------------------------------------------------------------------
# Storage: vectors as short text, so they fit in a CSV cell
# ---------------------------------------------------------------------------

def encode(vec: Sequence[float]) -> str:
    return base64.b64encode(np.asarray(vec, dtype="<f2").tobytes()).decode("ascii")


def decode(value) -> Optional[np.ndarray]:
    if not isinstance(value, str) or not value:
        return None
    try:
        v = np.frombuffer(base64.b64decode(value), dtype="<f2").astype(np.float32)
    except Exception:
        return None
    n = np.linalg.norm(v)
    return v / n if v.size and np.isfinite(n) and n > 0 else None


def matrix(df: pd.DataFrame) -> Optional[np.ndarray]:
    """(n, d) unit vectors with NaN rows for songs without one; None if no song has one."""
    col = next((c for c in df.columns if c.lower() == COLUMN), None)
    if col is None:
        return None
    vecs = [decode(v) for v in df[col]]
    dims = {v.size for v in vecs if v is not None}
    if len(dims) != 1:
        return None
    d = dims.pop()
    out = np.full((len(df), d), np.nan, dtype=np.float32)
    for i, v in enumerate(vecs):
        if v is not None:
            out[i] = v
    return out


# ---------------------------------------------------------------------------
# The CLAP service
# ---------------------------------------------------------------------------

def available() -> bool:
    from app.core import modal_engines

    if modal_engines.enabled("clap"):
        return True
    try:
        with urllib.request.urlopen(f"{URL}/health", timeout=3) as r:
            return bool(json.loads(r.read()).get("model"))
    except Exception:
        return False


def _post(path: str, data: bytes, content_type: str, timeout: float = 120) -> dict:
    from app.core import modal_engines

    if modal_engines.enabled("clap"):
        return modal_engines.post_raw("clap", path, data, content_type)
    req = urllib.request.Request(f"{URL}{path}", data=data, method="POST", headers={"Content-Type": content_type})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(json.loads(e.read() or b"{}").get("detail", f"CLAP error {e.code}"))
    except urllib.error.URLError:
        raise RuntimeError("The CLAP service isn't running. Start it with: docker compose up -d clap")


def embed_audio(audio: bytes) -> np.ndarray:
    return np.asarray(_post("/embed/audio", audio, "application/octet-stream")["vector"], dtype=np.float32)


def embed_text(texts: List[str]) -> np.ndarray:
    body = json.dumps({"texts": texts}).encode()
    return np.asarray(_post("/embed/text", body, "application/json", timeout=60)["vectors"], dtype=np.float32)


# ---------------------------------------------------------------------------
# Filling the column
# ---------------------------------------------------------------------------

def _cache_dir() -> Path:
    from app.core.config import settings

    d = settings.DATA_DIR / "cache" / "sound_clap"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _preview(artist: str, title: str) -> Optional[bytes]:
    """The song's 30 s Deezer preview, found through the importer's cached lookup."""
    from app.core import library_import

    # analyse=True so a lookup made here leaves the same cache entry the importer would
    info = library_import.lookup(artist, title, analyse=True)
    if not info.get("deezer_id"):
        return None
    # Preview links expire, so ask for a fresh one
    track = library_import._get(f"https://api.deezer.com/track/{info['deezer_id']}")
    if not track.get("preview"):
        return None
    with urllib.request.urlopen(track["preview"], timeout=20) as r:
        return r.read()


def add_sound(df: pd.DataFrame, limit: int = 1500,
              progress: Optional[Callable[[int, int], None]] = None,
              stop: Optional[Callable[[], bool]] = None) -> tuple[pd.DataFrame, int]:
    """Fill the `sound` column for up to `limit` songs (most-played first). Returns (df, songs with sound).

    `stop()` returning True ends the loop early; songs already done keep their sound."""
    df = df.copy()
    if COLUMN not in df.columns:
        df[COLUMN] = None
    df[COLUMN] = df[COLUMN].astype(object)
    path_col = next((c for c in df.columns if c.lower() in ("local_path", "audio_path", "path")), None)
    plays = df["play_count"] if "play_count" in df.columns else pd.Series(0, index=df.index)
    order = plays.fillna(0).sort_values(ascending=False, kind="stable").index
    todo = [i for i in order if decode(df.at[i, COLUMN]) is None][:limit]
    from app.core.library_import import song_key

    cache = _cache_dir()
    for n, i in enumerate(todo, 1):
        if stop and stop():
            break
        artist = str(df.at[i, "artist"]) if "artist" in df.columns and pd.notna(df.at[i, "artist"]) else ""
        title = str(df.at[i, "title"]) if "title" in df.columns and pd.notna(df.at[i, "title"]) else ""
        local = Path(str(df.at[i, path_col])) if path_col and pd.notna(df.at[i, path_col]) else None
        key = str(local) if local else song_key(artist, title)
        cached = cache / (hashlib.sha1(key.lower().encode()).hexdigest() + ".txt")
        try:
            if cached.exists():
                df.at[i, COLUMN] = cached.read_text() or None
            else:
                audio = local.read_bytes() if local and local.is_file() else (_preview(artist, title) if title else None)
                code = encode(embed_audio(audio)) if audio else ""
                cached.write_text(code)  # "" remembers songs with no audio, so they aren't retried every import
                df.at[i, COLUMN] = code or None
                time.sleep(0.05)  # stay well under Deezer's rate limit
        except RuntimeError:
            raise  # the service went away: stop instead of failing every song
        except Exception:
            pass  # one bad preview shouldn't stop the import
        if progress:
            progress(n, len(todo))
    have = int(sum(decode(v) is not None for v in df[COLUMN]))
    return df, have


def search(df: pd.DataFrame, query: str, limit: int = 20) -> List[dict]:
    """Songs whose sound best matches a typed description, best first."""
    m = matrix(df)
    if m is None:
        return []
    q = embed_text([query])[0]
    q = q / (np.linalg.norm(q) or 1)
    ok = np.where(np.isfinite(m[:, 0]))[0]
    scores = m[ok] @ q
    best = ok[np.argsort(-scores)[:limit]]
    return [{"id": int(i), "score": round(float(s), 3)} for i, s in zip(best, np.sort(scores)[::-1][:limit])]
