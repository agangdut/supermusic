from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from ..models.job import Job, JobType
from ..utils.storage import job_store, save_artifact
from ..utils.safe_paths import AUDIO, user_file
from app.core import jobs
from app.core.visualization import extract_audio_features_batch, create_umap_visualization, plot_umap
import json

router = APIRouter(prefix="/visualization", tags=["visualization"])


class VisualizationRequest(BaseModel):
    audio_paths: List[str] = Field(..., description="List of audio file paths to visualize")
    n_components: int = Field(3, ge=2, le=3, description="Number of UMAP dimensions (2 or 3)")
    n_neighbors: int = Field(15, ge=2, description="UMAP n_neighbors parameter")
    min_dist: float = Field(0.1, ge=0.0, le=1.0, description="UMAP min_dist parameter")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional metadata for tracks")


@router.post("/umap", response_model=Job)
async def create_umap_vis(req: VisualizationRequest, bg: BackgroundTasks, owner: str = Depends(jobs.job_owner)) -> Job:
    if len(req.audio_paths) > 200:
        raise HTTPException(status_code=400, detail="Up to 200 songs at a time.")
    req.audio_paths = [str(user_file(p, AUDIO, "song")) for p in req.audio_paths]
    """Create UMAP visualization from audio files."""
    job = Job(job_type=JobType.VISUALIZATION, payload=req.dict())
    job_store[str(job.id)] = job
    job.message = "Extracting audio features…"

    async def _worker(j: Job) -> None:
        try:
            # Validate paths
            audio_paths = [Path(p) for p in req.audio_paths]
            missing = [p for p in audio_paths if not p.exists()]
            if missing:
                raise FileNotFoundError(f"Audio files not found: {[str(p) for p in missing]}")
            
            j.progress = 20
            j.message = f"Extracting features from {len(audio_paths)} files…"
            
            # Extract features
            loop = asyncio.get_event_loop()
            features_df = await loop.run_in_executor(
                None, extract_audio_features_batch, [str(p) for p in audio_paths]
            )
            
            if features_df.empty:
                raise ValueError("No features extracted from audio files")
            
            # Add metadata if provided
            if req.metadata:
                for key, values in req.metadata.items():
                    if len(values) == len(features_df):
                        features_df[key] = values
            
            j.progress = 60
            j.message = "Computing UMAP embedding…"
            
            # Create UMAP visualization
            vis_data = await loop.run_in_executor(
                None,
                create_umap_visualization,
                features_df,
                req.n_components,
                req.n_neighbors,
                req.min_dist
            )
            
            j.progress = 80
            j.message = "Generating visualization…"
            
            # Create Plotly figure
            fig = await loop.run_in_executor(
                None, plot_umap, features_df, **{
                    "n_components": req.n_components,
                    "n_neighbors": req.n_neighbors,
                    "min_dist": req.min_dist
                }
            )
            
            # Save visualization as JSON (Plotly format)
            vis_json = json.dumps(fig.to_dict(), indent=2)
            artifact_path = save_artifact(j, "umap_visualization.json", vis_json.encode())
            
            # Also save raw data
            raw_data = {
                "coordinates": vis_data["coordinates"],
                "metadata": vis_data["metadata"]
            }
            raw_json = json.dumps(raw_data, indent=2)
            raw_path = save_artifact(j, "umap_data.json", raw_json.encode())
            
            j.mark_success(
                {
                    "artifacts": {
                        "visualization": artifact_path,
                        "data": raw_path
                    },
                    "metrics": {
                        "n_files": len(audio_paths),
                        "n_components": req.n_components
                    }
                },
                message="UMAP visualization complete",
            )
        except Exception as e:
            j.mark_failed(str(e), "Visualization failed")

    return jobs.submit(bg, job, _worker, owner)


@router.get("/jobs/{job_id}", response_model=Job)
async def get_visualization_job(job_id: str) -> Job:
    """Get visualization job status."""
    job = job_store.get(job_id)
    if not job or job.job_type != JobType.VISUALIZATION:
        raise HTTPException(status_code=404, detail="Visualization job not found")
    return job

