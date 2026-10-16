from __future__ import annotations

import asyncio
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, Depends
from app.core import jobs
from pydantic import BaseModel, Field

from ..models.job import Job, JobType
from ..utils.storage import job_store, save_artifact
from ..utils.safe_paths import CSV, user_file
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


@router.post("/enrich", response_model=Job, dependencies=[Depends(jobs.rate_limit("enrich", 20))])
async def enrich_csv(req: CSVEnrichmentRequest, bg: BackgroundTasks) -> Job:
    req.csv_path = str(user_file(req.csv_path, CSV, "CSV"))
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


@router.post("/enrich-files", response_model=Job, dependencies=[Depends(jobs.rate_limit("enrich", 20))])
async def enrich_files(
    files: List[UploadFile] = File(..., description="CSVs and Spotify / Apple Music exports (JSON or text); several at once is fine."),
    lookup: bool = Form(True, description="Look songs up online for genre, year, tempo, key and energy."),
    limit: int = Form(2000, ge=0, le=50_000, description="Look up at most this many songs (most-played first)."),
    output: str = Form("combined", pattern="^(combined|separate)$",
                       description="combined: one CSV for all files. separate: one enriched CSV per input file."),
) -> Job:
    """Combine several files into one deduplicated track list and fill in what's missing.

    Each file is recognised from its columns (Exportify CSV, Spotify StreamingHistory /
    Streaming_History_Audio / YourLibrary / Playlist JSON, Apple Music exports, any CSV
    with title and artist). The same song in several files becomes one row, with play and
    skip counts added up. The result is one CSV that the Music Map can open directly.

    With output=separate, each input file gets its own enriched CSV instead (songs are
    still looked up once, even when they appear in several files), plus a zip of them all."""
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
    job = Job(job_type=JobType.CSV_ENRICHMENT, payload={"files": names, "lookup": lookup, "limit": limit, "output": output})
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
            if output == "separate":
                return _save_separate(job, parsed, detected, df, before, found)
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


class LastfmImportRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64, description="Last.fm username.")
    max_tracks: int = Field(2000, ge=1, le=20_000, description="Read at most this many top tracks (most-played first).")
    recent_pages: int = Field(25, ge=0, le=100, description="Pages of 200 recent scrobbles to read for play dates.")
    lookup: bool = Field(True, description="Look songs up online for genre, year, tempo, key and energy.")
    limit: int = Field(2000, ge=0, le=50_000, description="Look up at most this many songs (most-played first).")


@router.get("/lastfm/status")
def lastfm_status() -> dict:
    """Whether the server has a LASTFM_API_KEY, so the UI can say what's missing before anyone tries."""
    from app.core import lastfm_import
    return {"enabled": lastfm_import.enabled()}


@router.post("/import-lastfm", response_model=Job, dependencies=[Depends(jobs.rate_limit("enrich", 20))])
async def import_lastfm(req: LastfmImportRequest) -> Job:
    """Read a listener's library from Last.fm by username, then enrich it like any other import.

    Runs in the background: the job reports progress while it reads Last.fm and while it
    looks songs up, and finishes with one enriched CSV the Music Map can open."""
    from app.core import lastfm_import, library_import

    if not lastfm_import.enabled():
        raise HTTPException(status_code=503, detail="Last.fm import isn't set up on this server: add a free "
                            "LASTFM_API_KEY to .env (https://www.last.fm/api/account/create) and restart.")
    username = req.username.strip()
    job = Job(job_type=JobType.CSV_ENRICHMENT, payload={"source": "lastfm", **req.dict(), "username": username})
    job_store[str(job.id)] = job
    job.mark_running(f"Connecting to Last.fm for {username}…")
    job.progress = 2

    def work() -> None:
        try:
            def reading(msg: str, frac: float) -> None:
                job.message = msg
                job.progress = int(2 + 13 * frac)
                job.updated_at = datetime.utcnow()

            df, summary = lastfm_import.fetch(username, max_tracks=req.max_tracks,
                                              recent_pages=req.recent_pages, progress=reading)
            before = _coverage(df)
            found = None
            if req.lookup and req.limit > 0:
                job.message = f"Got {len(df):,} songs from Last.fm. Checking which need looking up…"

                def progress(done: int, total: int) -> None:
                    job.progress = int(15 + 80 * done / max(total, 1))
                    job.message = f"Looking songs up online… {done:,} of {total:,}"
                    job.updated_at = datetime.utcnow()

                df, found = library_import.enrich(df, limit=req.limit, progress=progress)
            job.message = "Saving…"
            df = df.dropna(axis=1, how="all")
            path = save_artifact(job, f"{summary['user']} - Last.fm (enriched).csv", df.to_csv(index=False).encode("utf-8"))
            metrics = {
                "files": [{"file": f"Last.fm: {summary['user']}", "type": "Last.fm library", "songs": int(len(df))}],
                "rows_in": int(len(df)),
                "songs": int(len(df)),
                "duplicates_merged": 0,
                "coverage_before": before,
                "coverage_after": _coverage(df),
                "lastfm": summary,
            }
            if found is not None:
                metrics["matched_online"] = int(found)
            job.mark_success({"artifacts": {"csv": path}, "library_csv": path, "metrics": metrics},
                             message=f"{len(df):,} songs from Last.fm ready")
        except lastfm_import.LastfmError as e:
            job.mark_failed(str(e), "Last.fm import failed")
            job.error_hint = str(e)  # already written for the listener
        except Exception as e:  # pragma: no cover
            job.mark_failed(str(e), "Last.fm import failed")

    threading.Thread(target=work, daemon=True).start()
    return job


LOOKED_UP = ["genre", "genre_source", "year", "bpm", "key", "energy", "brightness"]


def _save_separate(job: Job, parsed, detected, combined, before, found) -> None:
    """One enriched CSV per input file. Each keeps only its own songs and its own play counts;
    details looked up online (once, on the combined list) are copied in by song."""
    import io
    import zipfile

    from app.core import library_import

    combined = combined.copy()
    combined["_k"] = [library_import.song_key(a, t) for a, t in zip(combined["artist"], combined["title"])]
    looked = combined.drop_duplicates("_k").set_index("_k")
    outputs, artifacts, buf = [], {}, io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for n, (df, info) in enumerate(zip(parsed, detected), start=1):
            if not len(df):
                outputs.append({**info, "csv": None, "songs": 0})
                continue
            one = library_import.merge([df])
            keys = [library_import.song_key(a, t) for a, t in zip(one["artist"], one["title"])]
            for col in LOOKED_UP:
                if col in looked:
                    filled = looked[col].reindex(keys).to_numpy()
                    one[col] = one[col].where(one[col].notna(), filled) if col in one else filled
            one = one.dropna(axis=1, how="all")
            name = f"{Path(info['file'] or f'file {n}').stem} (enriched).csv"
            data = one.to_csv(index=False).encode("utf-8")
            path = save_artifact(job, name, data)
            zf.writestr(Path(path).name, data)
            artifacts[f"csv_{n}"] = path
            outputs.append({**info, "csv": path, "songs": int(len(one)), "coverage_after": _coverage(one)})
    zip_path = save_artifact(job, f"Enriched files ({len(artifacts)}).zip", buf.getvalue())
    metrics = {
        "files": detected,
        "outputs": outputs,
        "rows_in": sum(d["songs"] for d in detected),
        "songs": int(len(combined)),
        "coverage_before": before,
        "coverage_after": _coverage(combined.drop(columns="_k")),
    }
    if found is not None:
        metrics["matched_online"] = int(found)
    first = next((o["csv"] for o in outputs if o["csv"]), None)
    job.mark_success({"artifacts": {"zip": zip_path, **artifacts}, "library_csv": first, "metrics": metrics},
                     message=f"{len(artifacts)} enriched files ready")


@router.get("/jobs/{job_id}", response_model=Job)
async def get_csv_job(job_id: str) -> Job:
    job = job_store.get(job_id)
    if not job or job.job_type != JobType.CSV_ENRICHMENT:
        raise HTTPException(status_code=404, detail="CSV job not found")
    return job
