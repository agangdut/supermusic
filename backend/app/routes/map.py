from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.core.music_map import MapOptions, build_map

router = APIRouter(prefix="/map", tags=["map"])

SAMPLE_CSV = Path(__file__).resolve().parents[1] / "sample_data" / "sample_library.csv"


class MapRequest(BaseModel):
    csv_path: Optional[str] = Field(None, description="Server path from /upload/csv. Leave empty with sample=true.")
    sample: bool = Field(False, description="Use the bundled sample library instead of an upload.")
    neighbors: int = Field(4, ge=1, le=15, description="Links drawn from each track to its closest matches.")
    clusters: Optional[int] = Field(None, ge=1, le=20, description="Fixed number of groups; empty picks one.")
    weights: Dict[str, float] = Field(
        default_factory=dict,
        description="How much each aspect shapes the map: key, tempo, genre, mood, artist, era (0-2).",
    )


@router.post("/build")
async def build(req: MapRequest) -> dict:
    """Build a 3D taste map from a CSV of tracks. Fast enough to run inline."""
    path = SAMPLE_CSV if req.sample else Path(req.csv_path or "")
    if not req.sample and not req.csv_path:
        raise HTTPException(status_code=400, detail="Send csv_path, or sample=true.")
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"CSV file not found: {path}")
    try:
        df = pd.read_csv(path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Couldn't read that CSV: {e}")
    if len(df) > 5000:
        raise HTTPException(status_code=400, detail="Maps are limited to 5,000 tracks for now.")

    opts = MapOptions(
        neighbors=req.neighbors,
        clusters=req.clusters,
        weights={k: max(0.0, min(2.0, float(v))) for k, v in req.weights.items()},
    )
    try:
        result = await run_in_threadpool(build_map, df, opts)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    result["meta"]["source"] = "sample" if req.sample else path.name
    return result


def warm_up() -> None:
    """UMAP compiles itself on first use (~10s). Do that at startup, not on the first click."""
    try:
        build_map(pd.read_csv(SAMPLE_CSV), MapOptions())
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Import from Spotify / Apple Music exports
# ---------------------------------------------------------------------------

import threading  # noqa: E402
import uuid  # noqa: E402
from typing import List  # noqa: E402

from fastapi import File, Form, UploadFile  # noqa: E402

from app.core import library_import  # noqa: E402
from app.core.config import settings  # noqa: E402

_imports: Dict[str, dict] = {}


@router.post("/import")
async def import_library(
    files: List[UploadFile] = File(..., description="Spotify / Apple Music exports or CSVs; several at once is fine."),
    enrich: bool = Form(True, description="Look songs up on Deezer and analyse 30 s previews for genre/tempo/key/energy."),
    limit: int = Form(1500, ge=1, le=5000),
) -> dict:
    parsed, detected = [], []
    for f in files:
        data = await f.read()
        try:
            df, label = library_import.parse_file(f.filename or "upload", data)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Couldn't read {f.filename}: {e}")
        parsed.append(df)
        detected.append({"file": f.filename, "type": label, "songs": int(len(df))})

    job_id = uuid.uuid4().hex
    job = _imports[job_id] = {"id": job_id, "status": "running", "progress": 0, "detected": detected,
                              "message": "Merging your files…", "result": None, "error": None}

    def work() -> None:
        try:
            df = library_import.merge(parsed)
            job["songs"] = int(len(df))
            found = None
            if enrich:
                def tick(n, total):
                    job["progress"] = round(90 * n / max(total, 1))
                    job["message"] = f"Looking up songs online… {n} of {total}"
                df, found = library_import.enrich(df, limit=limit, progress=tick)
            out = settings.PROCESSED_DIR / "library"
            out.mkdir(parents=True, exist_ok=True)
            csv_path = out / f"library_{job_id[:8]}.csv"
            df.to_csv(csv_path, index=False)
            job["message"] = "Drawing your map…"
            job["progress"] = 95
            # Columns nobody filled in would otherwise look like (empty) data
            result = build_map(df.dropna(axis=1, how="all"), MapOptions())
            result["meta"]["source"] = ", ".join(d["type"] for d in detected)
            result["meta"]["library_csv"] = str(csv_path)
            if found is not None:
                result["meta"]["matched_online"] = found
            job.update(status="done", progress=100, message="Done", result=result)
        except Exception as e:
            job.update(status="error", error=str(e), message="Import failed")

    threading.Thread(target=work, daemon=True).start()
    return {k: v for k, v in job.items() if k != "result"}


@router.get("/import/{job_id}")
def import_status(job_id: str) -> dict:
    job = _imports.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Unknown import")
    return job
