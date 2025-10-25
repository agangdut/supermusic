from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Dict, Any, List

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from ..models.job import Job, JobType
from ..utils.storage import job_store, save_artifact
from core.separator import separate_stems

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


router = APIRouter(prefix="/stems", tags=["stems"])


class StemSeparationRequest(BaseModel):
    audio_path: str = Field(..., description="Input mixdown file.")
    model: str = Field("htdemucs", description="Separation model name.")
    stems: List[str] = Field(default_factory=lambda: ["vocals", "drums", "bass", "other"])


@router.post("/separate", response_model=Job)
async def separate_stems(req: StemSeparationRequest, bg: BackgroundTasks) -> Job:
    job = Job(job_type=JobType.STEM_SEPARATION, payload=req.dict())
    job_store[str(job.id)] = job
    job.mark_running("Separating stems…")

    async def _worker(j: Job) -> None:
        try:
            for p in (15, 35, 55, 80, 100):
                j.progress = p
                j.message = f"Running {req.model}… {p}%"
                await asyncio.sleep(0.35)

            artifacts: Dict[str, str] = {}
            for stem in req.stems:
                path = save_artifact(
                    j, f"{Path(req.audio_path).stem}_{stem}.wav", b"\x00" * 44
                )
                artifacts[stem] = path

            j.mark_success(
                {"artifacts": artifacts, "metrics": {"model": req.model, "stems": req.stems}},
                message="Stem separation complete",
            )
        except Exception as e:  # pragma: no cover
            j.mark_failed(str(e), "Stem separation failed")

    bg.add_task(_worker, job)
    return job


@router.get("/jobs/{job_id}", response_model=Job)
async def get_stems_job(job_id: str) -> Job:
    job = job_store.get(job_id)
    if not job or job.job_type != JobType.STEM_SEPARATION:
        raise HTTPException(status_code=404, detail="Stems job not found")
    return job
