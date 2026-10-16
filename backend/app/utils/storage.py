# backend/app/utils/storage.py
from __future__ import annotations

import os
import re
import secrets
from pathlib import Path
from typing import Dict, Iterable, Optional, TYPE_CHECKING

# Avoid runtime import of models to prevent circular imports.
if TYPE_CHECKING:  # only for type checkers; no runtime dependency
    from ..models.job import Job, JobType  # noqa: F401
else:
    Job = object  # type: ignore
    JobType = object  # type: ignore

# ------------------------------------------------------------------------------
# Job store: kept in memory while the server runs, and saved to the SQLite file
# (data/supermusic.db) whenever a job starts or ends, so a restart doesn't lose
# finished results. A job that was still running when the server stopped comes
# back as failed, with a note to start it again.
# ------------------------------------------------------------------------------
_RESTARTED = "The server restarted while this was running. Start it again."


class JobStore(dict):
    def get(self, job_id, default=None):  # type: ignore[override]
        job = super().get(job_id)
        if job is None:
            job = _load_job(str(job_id))
            if job is not None:
                super().__setitem__(str(job_id), job)
        return job if job is not None else default

    def __contains__(self, job_id) -> bool:  # type: ignore[override]
        return self.get(job_id) is not None

    def __getitem__(self, job_id):
        job = self.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job


job_store: Dict[str, Job] = JobStore()  # defined at import time


def save_job(job: Job) -> None:
    """Write a job's current state to the database. Never lets a database problem break the job."""
    try:
        from app.core import store

        store.connect().execute(
            "INSERT INTO jobs (id, job_type, status, data, updated_at) VALUES (?, ?, ?, ?, strftime('%s','now')) "
            "ON CONFLICT(id) DO UPDATE SET status=excluded.status, data=excluded.data, updated_at=excluded.updated_at",
            (str(job.id), str(getattr(job.job_type, "value", job.job_type)), str(getattr(job.status, "value", job.status)),
             job.model_dump_json()),
        )
    except Exception:
        pass


def _load_job(job_id: str) -> Optional[Job]:
    try:
        from app.core import store
        from app.models.job import Job as JobModel, JobStatus

        row = store.connect().execute("SELECT data FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            return None
        job = JobModel.model_validate_json(row["data"])
    except Exception:
        return None
    if job.status in (JobStatus.queued, JobStatus.running):
        job.mark_failed(_RESTARTED, "Stopped by a server restart")
    return job


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
    """Save into the artifact folder under a readable name, in a folder of its own."""
    safe = Path(_safe_filename(filename))
    # Each result gets its own folder with a random name, so the download link
    # can't be guessed from the song's name by someone else.
    folder = _ARTIFACT_DIR / secrets.token_urlsafe(12)
    out_path = folder / safe.name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(content)
    return str(out_path)


def save_artifact(job: Job, suggested_name: str, content: bytes) -> str:
    """Save a job's result file. The name is what the person downloads, so it should
    read like one: build it with output_name()."""
    return save_bytes(suggested_name, content)
