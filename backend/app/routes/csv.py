from __future__ import annotations

import asyncio
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..models.job import Job, JobType
from ..utils.storage import job_store, save_artifact
from app.core.metadata import enrich_track_record

# Optional shared store (fallback if not present)


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
            from app.core.csv_enrichment import enrich_csv_file
            
            j.progress = 10
            j.message = "Reading CSV file…"
            await asyncio.sleep(0.1)
            
            csv_path = Path(req.csv_path)
            if not csv_path.exists():
                raise FileNotFoundError(f"CSV file not found: {csv_path}")
            
            # Count rows for progress tracking
            import pandas as pd
            df = pd.read_csv(csv_path)
            total_rows = len(df)
            
            j.progress = 20
            j.message = f"Processing {total_rows} rows…"
            
            # Run enrichment in executor
            loop = asyncio.get_event_loop()
            enriched_path = await loop.run_in_executor(
                None, enrich_csv_file, str(csv_path), None, req.strategy, req.options
            )
            
            j.progress = 90
            j.message = "Saving enriched CSV…"
            
            # Read enriched CSV and save as artifact
            enriched_bytes = Path(enriched_path).read_bytes()
            artifact_path = save_artifact(
                j, f"{csv_path.stem} (enriched).csv", enriched_bytes
            )
            
            j.mark_success(
                {
                    "artifacts": {"csv": artifact_path},
                    "metrics": {"rows_processed": total_rows, "strategy": req.strategy},
                },
                message="CSV enrichment complete",
            )
        except Exception as e:  # pragma: no cover
            j.mark_failed(str(e), "CSV enrichment failed")

    bg.add_task(_worker, job)
    return job


COVERAGE = ["genre", "year", "bpm", "key", "energy", "play_count", "first_played", "liked", "playlists"]


def _coverage(df) -> Dict[str, float]:
    """Share of songs that have each field filled in."""
    return {c: round(float(df[c].notna().mean()), 3) for c in COVERAGE if c in df and len(df)}


@router.post("/enrich-files", response_model=Job)
async def enrich_files(
    files: List[UploadFile] = File(..., description="CSVs and Spotify / Apple Music exports (JSON or text); several at once is fine."),
    lookup: bool = Form(True, description="Look songs up online for genre, year, tempo, key and energy."),
    limit: int = Form(2000, ge=0, le=50_000, description="Look up at most this many songs (most-played first)."),
) -> Job:
    """Combine several files into one deduplicated track list and fill in what's missing.

    Each file is recognised from its columns (Exportify CSV, Spotify StreamingHistory /
    Streaming_History_Audio / YourLibrary / Playlist JSON, Apple Music exports, any CSV
    with title and artist). The same song in several files becomes one row, with play and
    skip counts added up. The result is one CSV that the Music Map can open directly."""
    from app.core import library_import

    parsed, detected = [], []
    for f in files:
        data = await f.read()
        try:
            df, label = library_import.parse_file(f.filename or "upload", data)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Couldn't read {f.filename}: {e}")
        parsed.append(df)
        detected.append({"file": f.filename, "type": label, "songs": int(len(df))})

    names = [d["file"] for d in detected]
    job = Job(job_type=JobType.CSV_ENRICHMENT, payload={"files": names, "lookup": lookup, "limit": limit})
    job_store[str(job.id)] = job
    job.mark_running(f"Combining {len(files)} file{'s' if len(files) != 1 else ''}…")
    job.progress = 5

    def work() -> None:
        try:
            df = library_import.merge(parsed)
            before = _coverage(df)
            rows_in = sum(d["songs"] for d in detected)
            found = None
            if lookup and limit > 0:
                job.message = "Checking which songs need looking up…"

                def progress(done: int, total: int) -> None:
                    job.progress = int(10 + 85 * done / max(total, 1))
                    job.message = f"Looking songs up online… {done:,} of {total:,}"
                    job.updated_at = datetime.utcnow()

                df, found = library_import.enrich(df, limit=limit, progress=progress)
            job.message = "Saving…"
            df = df.dropna(axis=1, how="all")  # columns no file had
            name = Path(names[0]).stem if len(names) == 1 else f"Library ({len(names)} files)"
            path = save_artifact(job, f"{name} (enriched).csv", df.to_csv(index=False).encode("utf-8"))
            metrics = {
                "files": detected,
                "rows_in": rows_in,
                "songs": int(len(df)),
                "duplicates_merged": int(rows_in - len(df)),
                "coverage_before": before,
                "coverage_after": _coverage(df),
            }
            if found is not None:
                metrics["matched_online"] = int(found)
            job.mark_success({"artifacts": {"csv": path}, "library_csv": path, "metrics": metrics},
                             message=f"{len(df):,} songs ready")
        except Exception as e:  # pragma: no cover
            job.mark_failed(str(e), "CSV enrichment failed")

    threading.Thread(target=work, daemon=True).start()
    return job


@router.get("/jobs/{job_id}", response_model=Job)
async def get_csv_job(job_id: str) -> Job:
    job = job_store.get(job_id)
    if not job or job.job_type != JobType.CSV_ENRICHMENT:
        raise HTTPException(status_code=404, detail="CSV job not found")
    return job
