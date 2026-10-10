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
