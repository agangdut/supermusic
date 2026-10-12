from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List, Dict, Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from ..models.job import Job, JobType
from ..utils.storage import job_store, output_name, save_artifact
from app.core.csv_enrichment import enrich_csv_file
from app.core.transcription import transcribe_to_midi
from app.core.separator import separate_stems
import zipfile
import io

router = APIRouter(prefix="/batch", tags=["batch"])


class BatchProcessRequest(BaseModel):
    audio_files: List[str] = Field(..., description="List of audio file paths")
    operations: List[str] = Field(
        default=["transcribe"],
        description="Operations to perform: transcribe, separate, both"
    )


@router.post("/process", response_model=Job)
async def batch_process(req: BatchProcessRequest, bg: BackgroundTasks) -> Job:
    """Process multiple audio files in batch."""
    job = Job(job_type=JobType.MIDI_CONVERSION, payload=req.dict())
    job_store[str(job.id)] = job
    job.mark_running(f"Processing {len(req.audio_files)} files…")

    async def _worker(j: Job) -> None:
        try:
            results = []
            total = len(req.audio_files)
            
            for idx, audio_path in enumerate(req.audio_files):
                j.progress = int((idx / total) * 90)
                j.message = f"Processing file {idx + 1}/{total}…"
                
                audio_file = Path(audio_path)
                if not audio_file.exists():
                    results.append({"file": audio_path, "error": "File not found"})
                    continue
                
                file_results = {"file": audio_path, "artifacts": {}}
                
                try:
                    # Transcribe if requested
                    if "transcribe" in req.operations or "both" in req.operations:
                        loop = asyncio.get_event_loop()
                        midi_path = await loop.run_in_executor(
                            None, transcribe_to_midi, str(audio_file)
                        )
                        midi_bytes = midi_path.read_bytes()
                        artifact_path = save_artifact(
                            j, output_name(audio_file, "General", ".mid"), midi_bytes
                        )
                        file_results["artifacts"]["midi"] = artifact_path
                    
                    # Separate stems if requested
                    if "separate" in req.operations or "both" in req.operations:
                        loop = asyncio.get_event_loop()
                        stems_dict = await loop.run_in_executor(
                            None, separate_stems, str(audio_file)
                        )
                        for stem_name, stem_path in stems_dict.items():
                            stem_bytes = Path(stem_path).read_bytes()
                            artifact_path = save_artifact(
                                j, output_name(audio_file, stem_name, ".wav"), stem_bytes
                            )
                            file_results["artifacts"][stem_name] = artifact_path
                    
                    results.append(file_results)
                except Exception as e:
                    results.append({"file": audio_path, "error": str(e)})
            
            # Create ZIP archive of all artifacts
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for result in results:
                    if "artifacts" in result:
                        for artifact_type, artifact_path in result["artifacts"].items():
                            artifact_file = Path(artifact_path)
                            if artifact_file.exists():
                                zip_file.write(artifact_path, artifact_file.name)
            
            zip_path = save_artifact(j, "SuperMusic batch results.zip", zip_buffer.getvalue())
            
            j.mark_success(
                {
                    "artifacts": {"zip": zip_path},
                    "results": results,
                    "metrics": {"total_files": total, "successful": len([r for r in results if "error" not in r])}
                },
                message="Batch processing complete",
            )
        except Exception as e:
            j.mark_failed(str(e), "Batch processing failed")

    bg.add_task(_worker, job)
    return job


@router.get("/jobs/{job_id}", response_model=Job)
async def get_batch_job(job_id: str) -> Job:
    """Get batch job status."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Batch job not found")
    return job

