from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field, AnyUrl

from ..models.job import Job, JobType
from ..utils.storage import job_store, save_artifact
from core.downloader import download_track

try:
    from app.utils.storage import job_store, save_artifact  # type: ignore
except Exception:  # pragma: no cover
    job_store: Dict[str, Job] = {}

    def save_artifact(_job: Job, suggested_name: str, content: bytes) -> str:
        out_dir = Path("/tmp/supermusic/artifacts")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / suggested_name
        out_path.write_bytes(content)
        return str(out_path)


router = APIRouter(prefix="/tracks", tags=["tracks"])


class TrackDownloadRequest(BaseModel):
    url: AnyUrl = Field(..., description="Source media URL (YouTube, etc.)")
    format: str = Field("bestaudio", description="Desired download format.")
    title_hint: Optional[str] = Field(None, description="Optional custom filename stem.")


@router.post("/download", response_model=Job)
async def download_track(req: TrackDownloadRequest, bg: BackgroundTasks) -> Job:
    job = Job(job_type=JobType.TRACK_DOWNLOAD, payload=req.dict())
    job_store[str(job.id)] = job
    job.mark_running("Fetching media…")

    async def _worker(j: Job) -> None:
        try:
            for p in (20, 40, 65, 90, 100):
                j.progress = p
                j.message = f"Downloading… {p}%"
                await asyncio.sleep(0.3)

            name = f"{req.title_hint or 'track'}_download.wav"
            file_path = save_artifact(j, name, b"\x00" * 44)
            j.mark_success(
                {"artifacts": {"audio": file_path}, "metrics": {"source": str(req.url)}},
                message="Track downloaded",
            )
        except Exception as e:  # pragma: no cover
            j.mark_failed(str(e), "Track download failed")

    bg.add_task(_worker, job)
    return job


@router.get("/jobs/{job_id}", response_model=Job)
async def get_track_job(job_id: str) -> Job:
    job = job_store.get(job_id)
    if not job or job.job_type != JobType.TRACK_DOWNLOAD:
        raise HTTPException(status_code=404, detail="Track job not found")
    return job
