from __future__ import annotations

from pathlib import Path
from typing import List, Optional
import zipfile
import io

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..models.job import Job
from ..utils.storage import job_store

router = APIRouter(prefix="/export", tags=["export"])


class ExportRequest(BaseModel):
    job_ids: List[str] = Field(..., description="List of job IDs to export")
    format: str = Field("zip", description="Export format (zip)")


@router.post("/jobs")
async def export_jobs(req: ExportRequest) -> StreamingResponse:
    """Export artifacts from multiple jobs as ZIP."""
    jobs = []
    for job_id in req.job_ids:
        job = job_store.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        jobs.append(job)
    
    # Collect all artifacts
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for job in jobs:
            if job.result and "artifacts" in job.result:
                for artifact_type, artifact_path in job.result["artifacts"].items():
                    artifact_file = Path(artifact_path)
                    if artifact_file.exists():
                        zip_file.write(
                            artifact_path,
                            f"{job.id}/{artifact_file.name}"
                        )
    
    zip_buffer.seek(0)
    
    return StreamingResponse(
        io.BytesIO(zip_buffer.read()),
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=supermusic_export.zip"
        }
    )


@router.get("/job/{job_id}")
async def export_job(job_id: str) -> StreamingResponse:
    """Export artifacts from a single job as ZIP."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if not job.result or "artifacts" not in job.result:
        raise HTTPException(status_code=400, detail="Job has no artifacts to export")
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for artifact_type, artifact_path in job.result["artifacts"].items():
            artifact_file = Path(artifact_path)
            if artifact_file.exists():
                zip_file.write(artifact_path, artifact_file.name)
    
    zip_buffer.seek(0)
    
    return StreamingResponse(
        io.BytesIO(zip_buffer.read()),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=job_{job_id}_export.zip"
        }
    )

