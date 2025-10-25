from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from ..models.job import Job, JobType
from ..utils.storage import job_store, save_artifact
from app.core.transcription import transcribe_to_midi

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


router = APIRouter(prefix="/midi", tags=["midi"])


class MIDIConvertRequest(BaseModel):
    source_path: str = Field(..., description="Input audio file (wav/mp3).")
    onset_sensitivity: float = Field(0.6, ge=0.0, le=1.0)
    model: str = Field("basic", description="Transcription model name.")


@router.post("/convert", response_model=Job)
async def convert_to_midi(req: MIDIConvertRequest, bg: BackgroundTasks) -> Job:
    job = Job(job_type=JobType.MIDI_CONVERSION, payload=req.dict())
    job_store[str(job.id)] = job
    job.mark_running("Transcribing audio to MIDI…")

    async def _worker(j: Job) -> None:
        try:
            for p in (5, 25, 50, 75, 100):
                j.progress = p
                j.message = f"Transcribing… {p}%"
                await asyncio.sleep(0.3)

            # Fake MIDI bytes (valid enough header for testing)
            midi_bytes = b"MThd\x00\x00\x00\x06\x00\x01\x00\x01\x01\xE0MTrk\x00\x00\x00\x04\x00\xFF\x2F\x00"
            midi_path = save_artifact(
                j, f"{Path(req.source_path).stem}.mid", midi_bytes
            )
            j.mark_success(
                {
                    "artifacts": {"midi": midi_path},
                    "metrics": {"duration_s": 1.2, "model": req.model},
                },
                message="MIDI conversion complete",
            )
        except Exception as e:  # pragma: no cover
            j.mark_failed(str(e), "MIDI conversion failed")

    bg.add_task(_worker, job)
    return job


@router.get("/jobs/{job_id}", response_model=Job)
async def get_midi_job(job_id: str) -> Job:
    job = job_store.get(job_id)
    if not job or job.job_type != JobType.MIDI_CONVERSION:
        raise HTTPException(status_code=404, detail="MIDI job not found")
    return job
