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

def _slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^\w\-\.]+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-") or "artifact"

def save_bytes(filename: str, content: bytes) -> str:
    safe = _slugify(filename)
    out_path = _ARTIFACT_DIR / safe
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(content)
    return str(out_path)

def save_artifact(job: Job, suggested_name: str, content: bytes) -> str:
    prefix = str(getattr(job, "id", "job"))
    name = f"{prefix}_{_slugify(suggested_name)}"
    return save_bytes(name, content)
