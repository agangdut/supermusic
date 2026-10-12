# backend/app/utils/storage.py
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, Iterable, Optional, TYPE_CHECKING

# Avoid runtime import of models to prevent circular imports.
if TYPE_CHECKING:  # only for type checkers; no runtime dependency
    from ..models.job import Job, JobType  # noqa: F401
else:
    Job = object  # type: ignore
    JobType = object  # type: ignore

# ------------------------------------------------------------------------------
# Simple in-memory job store
# ------------------------------------------------------------------------------
job_store: Dict[str, Job] = {}  # defined at import time

def get_job(job_id: str) -> Optional[Job]:
    return job_store.get(job_id)

def put_job(job: Job) -> None:
    # str() so UUID works as key
    job_store[str(getattr(job, "id", ""))] = job

def list_jobs(job_type: Optional[JobType] = None) -> Iterable[Job]:
    if job_type is None:
        return list(job_store.values())
    return [j for j in job_store.values() if getattr(j, "job_type", None) == job_type]

# ------------------------------------------------------------------------------
# Artifact saving
# ------------------------------------------------------------------------------
_ARTIFACT_DIR = Path(os.getenv("SUPERMUSIC_ARTIFACT_DIR", Path(os.getenv("TMP", "/tmp")) / "supermusic" / "artifacts"))
_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

# Words in brackets that only describe the upload, not the song:
# "Song (Official Music Video)", "Song [Lyrics]", "Song (Official Visualizer) [HD]"
_NOISE = re.compile(
    r"\s*[\(\[][^\)\]]*\b(official|video|audio|lyrics?|visuali[sz]er|hd|hq|4k|mv)\b[^\)\]]*[\)\]]",
    re.IGNORECASE,
)
# Characters Windows and macOS don't allow in a file name
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def song_title(name: str) -> str:
    """A readable title from an uploaded file's name: "G Herbo - 1 Chance (Official
    Music Video)_2.mp3" -> "G Herbo - 1 Chance". Drops the extension, the bracketed
    video words, a trailing duplicate counter, and underscores used as spaces."""
    stem = Path(str(name)).stem if Path(str(name)).suffix.lower() in _MEDIA_EXT else str(name)
    stem = re.sub(r"(_\d+| \(\d+\))$", "", stem)
    stem = _NOISE.sub("", stem).replace("_", " ")
    stem = re.sub(r"\s+", " ", stem).strip(" -.")
    return stem or "song"


def output_name(source: str | Path, label: str = "", ext: str = "") -> str:
    """The name a result file gets: the song's title, then what the file is.
    output_name("G Herbo - 1 Chance.mp3", "two hands", ".mid") -> "G Herbo - 1 Chance (two hands).mid" """
    title = song_title(Path(str(source)).name)
    return f"{title} ({label}){ext}" if label else f"{title}{ext}"


_MEDIA_EXT = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".opus", ".mid", ".midi", ".csv", ".zip", ".webm", ".mp4"}


def _safe_filename(text: str) -> str:
    text = _UNSAFE.sub("", text).strip().strip(".")
    return re.sub(r"\s+", " ", text) or "artifact"


def save_bytes(filename: str, content: bytes) -> str:
    """Save into the artifact folder under a readable name. If that name is taken
    (the same song run twice), the new file becomes "Name (2).ext", "Name (3).ext", ..."""
    safe = Path(_safe_filename(filename))
    out_path = _ARTIFACT_DIR / safe.name
    n = 2
    while out_path.exists():
        out_path = _ARTIFACT_DIR / f"{safe.stem} ({n}){safe.suffix}"
        n += 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(content)
    return str(out_path)


def save_artifact(job: Job, suggested_name: str, content: bytes) -> str:
    """Save a job's result file. The name is what the person downloads, so it should
    read like one: build it with output_name()."""
    return save_bytes(suggested_name, content)
