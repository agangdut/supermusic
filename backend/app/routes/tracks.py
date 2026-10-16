from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field, AnyUrl

from ..models.job import Job, JobType
from ..utils.storage import job_store, output_name, save_artifact
from app.core.downloader import download_audio
from app.core import jobs


router = APIRouter(prefix="/tracks", tags=["tracks"])


class TrackDownloadRequest(BaseModel):
    url: AnyUrl = Field(..., description="Source media URL (YouTube, etc.)")
    format: str = Field("bestaudio", description="Desired download format.")
    title_hint: Optional[str] = Field(None, description="Optional custom filename stem.")


# Only these sites, so the server can't be told to fetch addresses on its own network
ALLOWED_HOSTS = ("youtube.com", "youtu.be", "soundcloud.com", "bandcamp.com")


def downloads_enabled() -> bool:
    """Off on the public site (SM_ENABLE_DOWNLOADS=0): downloading from YouTube breaks its terms."""
    return os.getenv("SM_ENABLE_DOWNLOADS", "1") == "1"


@router.post("/download", response_model=Job)
async def download_track(req: TrackDownloadRequest, bg: BackgroundTasks, owner: str = Depends(jobs.job_owner)) -> Job:
    if not downloads_enabled():
        raise HTTPException(status_code=403, detail="Downloading from links is turned off on this server.")
    host = (req.url.host or "").lower()
    if not any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS):
        raise HTTPException(status_code=400, detail="Links from YouTube, SoundCloud or Bandcamp only.")
    job = Job(job_type=JobType.TRACK_DOWNLOAD, payload=req.dict())
    job_store[str(job.id)] = job
    job.message = "Fetching media…"

    async def _worker(j: Job) -> None:
        try:
            j.progress = 10
            j.message = "Initializing download…"
            await asyncio.sleep(0.1)
            
            j.progress = 30
            j.message = f"Downloading from {str(req.url)[:50]}…"
            
            # Run download in executor to avoid blocking
            loop = asyncio.get_event_loop()
            audio_path = await loop.run_in_executor(
                None, download_audio, str(req.url)
            )
            
            j.progress = 80
            j.message = "Saving audio file…"
            
            # Read audio file and save as artifact
            audio_bytes = Path(audio_path).read_bytes()
            artifact_name = output_name(req.title_hint or Path(audio_path).stem, "", Path(audio_path).suffix)
            artifact_path = save_artifact(j, artifact_name, audio_bytes)
            
            # Get file size for metrics
            file_size = Path(audio_path).stat().st_size
            
            j.mark_success(
                {
                    "artifacts": {"audio": artifact_path},
                    "metrics": {"source": str(req.url), "size_bytes": file_size},
                },
                message="Track downloaded",
            )
        except Exception as e:  # pragma: no cover
            j.mark_failed(str(e), "Track download failed")

    return jobs.submit(bg, job, _worker, owner)


@router.get("/jobs/{job_id}", response_model=Job)
async def get_track_job(job_id: str) -> Job:
    job = job_store.get(job_id)
    if not job or job.job_type != JobType.TRACK_DOWNLOAD:
        raise HTTPException(status_code=404, detail="Track job not found")
    return job
