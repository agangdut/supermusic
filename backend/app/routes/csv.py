from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from ..models.job import Job, JobType
from ..utils.storage import job_store, save_artifact
from app.core.metadata import enrich_track_record

# Optional shared store (fallback if not present)
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


router = APIRouter(prefix="/csv", tags=["csv"])


class CSVEnrichmentRequest(BaseModel):
    csv_path: str = Field(..., description="Path to input CSV.")
    strategy: str = Field(
        "youtube+acousticbrainz",
        description="Enrichment strategy pipeline identifier.",
    )
    options: Dict[str, Any] = Field(default_factory=dict)


@router.post("/enrich", response_model=Job)
async def enrich_csv(req: CSVEnrichmentRequest, bg: BackgroundTasks) -> Job:
    job = Job(job_type=JobType.CSV_ENRICHMENT, payload=req.dict())
    job_store[str(job.id)] = job
    job.mark_running("Starting CSV enrichment…")

    async def _worker(j: Job) -> None:
        try:
            # Simulate incremental progress
            for p in (10, 35, 60, 85, 100):
                j.progress = p
                j.message = f"Enriching… {p}%"
                await asyncio.sleep(0.25)
            # Create a tiny “enriched” CSV artifact
            artifact_path = save_artifact(
                j, f"enriched_{Path(req.csv_path).stem}.csv",
                b"title,artist,enriched\nexample,artist,true\n",
            )
            j.mark_success(
                {
                    "artifacts": {"csv": artifact_path},
                    "metrics": {"rows_processed": 1, "strategy": req.strategy},
                },
                message="CSV enrichment complete",
            )
        except Exception as e:  # pragma: no cover
            j.mark_failed(str(e), "CSV enrichment failed")

    bg.add_task(_worker, job)
    return job


@router.get("/jobs/{job_id}", response_model=Job)
async def get_csv_job(job_id: str) -> Job:
    job = job_store.get(job_id)
    if not job or job.job_type != JobType.CSV_ENRICHMENT:
        raise HTTPException(status_code=404, detail="CSV job not found")
    return job
