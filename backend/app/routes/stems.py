from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Dict, Any, List

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from ..models.job import Job, JobType
from ..utils.storage import job_store, save_artifact
from app.core.separator import separate_stems as run_separation
from app.core.progress import estimate_seconds, report, reporting, run_with_context

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
            audio_path = Path(req.audio_path)
            if not audio_path.exists():
                raise FileNotFoundError(f"Audio file not found: {audio_path}")
            
            try:
                import librosa

                j.eta_s = estimate_seconds("stems", float(librosa.get_duration(path=str(audio_path))))
            except Exception:
                pass
            report(f"Separating into stems with {req.model}…")

            # Run separation in executor to avoid blocking
            loop = asyncio.get_event_loop()
            stems_dict = await loop.run_in_executor(
                None, run_with_context(run_separation, str(audio_path), None, req.model)
            )

            report("Saving the stem files…")
            j.progress = 90
            
            # Copy stems to artifacts
            artifacts: Dict[str, str] = {}
            for stem_name, stem_path in stems_dict.items():
                stem_bytes = Path(stem_path).read_bytes()
                artifact_path = save_artifact(
                    j, f"{audio_path.stem}_{stem_name}.wav", stem_bytes
                )
                artifacts[stem_name] = artifact_path
            
            j.mark_success(
                {"artifacts": artifacts, "metrics": {"model": req.model, "stems": list(stems_dict.keys())}},
                message="Stem separation complete",
            )
        except Exception as e:  # pragma: no cover
            j.mark_failed(str(e), f"Failed while: {j.stage or 'starting'}")

    async def _run(j: Job) -> None:
        with reporting(j):
            await _worker(j)

    bg.add_task(_run, job)
    return job


@router.get("/jobs/{job_id}", response_model=Job)
async def get_stems_job(job_id: str) -> Job:
    job = job_store.get(job_id)
    if not job or job.job_type != JobType.STEM_SEPARATION:
        raise HTTPException(status_code=404, detail="Stems job not found")
    return job
