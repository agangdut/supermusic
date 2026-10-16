"""
Files a request may point at.

Some endpoints take the path of a file the server saved earlier (an upload, an
import, a result). Without a check, a visitor could send any path and have the
server read, say, its own database. `user_file` only lets through files inside
the folders SuperMusic writes uploads and results to, with an expected extension.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional

from fastapi import HTTPException

from app.core.config import settings

AUDIO = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".opus", ".webm", ".mp4", ".aac"}
CSV = {".csv", ".tsv"}
MIDI = {".mid", ".midi"}


def user_roots() -> List[Path]:
    """Where uploads, imports and results are written."""
    from app.routes.upload import UPLOAD_DIR
    from app.utils.storage import _ARTIFACT_DIR

    return [p.resolve() for p in (UPLOAD_DIR, _ARTIFACT_DIR, settings.PROCESSED_DIR)]


def is_user_file(path: str | Path, kinds: Iterable[str]) -> bool:
    try:
        p = Path(path).resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    return p.suffix.lower() in set(kinds) and p.is_file() and any(p.is_relative_to(r) for r in user_roots())


def user_file(path: Optional[str | Path], kinds: Iterable[str], what: str = "file") -> Path:
    """The resolved path, or a 404 (the same answer whether the file is missing or off-limits)."""
    if not path or not is_user_file(path, kinds):
        raise HTTPException(status_code=404, detail=f"That {what} isn't on the server any more. Upload it again.")
    return Path(path).resolve()
