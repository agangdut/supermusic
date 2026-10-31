from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Any, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from ..models.job import Job, JobType
from ..utils.storage import job_store, output_name, save_artifact
from ..utils.safe_paths import AUDIO, user_file
from app.core import jobs
from app.core.separator import separate_stems as run_separation
from app.core.audio_converter import convert_audio_format
from app.core.config import settings
from app.core.progress import estimate_seconds, report, reporting, run_with_context


router = APIRouter(prefix="/stems", tags=["stems"])

STEM_BITRATE = "192k"   # the most a stem gets
MIN_STEM_KBPS = 96      # below this, stems start to sound watery


def stem_bitrate(audio_path: Path) -> str:
    """The original's bitrate, between MIN_STEM_KBPS and STEM_BITRATE: a stem is never
    a bigger file than the song it came from (a 128 kbps MP3 gives 128 kbps stems)."""
    import shutil as sh
    import subprocess

    top = int(STEM_BITRATE.rstrip("k"))
    ffprobe = sh.which("ffprobe")
    if not ffprobe:
        return STEM_BITRATE
    try:
        out = subprocess.run([ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries",
                              "stream=bit_rate:format=bit_rate", "-of", "csv=p=0", str(audio_path)],
                             capture_output=True, text=True, timeout=30).stdout
        bps = next(int(x) for x in out.replace(",", "\n").split() if x.strip().isdigit())
    except Exception:
        return STEM_BITRATE
    return f"{max(MIN_STEM_KBPS, min(top, round(bps / 1000)))}k"


class StemSeparationRequest(BaseModel):
    audio_path: str = Field(..., description="Input mixdown file.")
    model: str = Field("htdemucs", description="Separation model name.")
    stems: List[str] = Field(default_factory=lambda: ["vocals", "drums", "bass", "other"])


@router.post("/separate", response_model=Job)
async def separate_stems(req: StemSeparationRequest, bg: BackgroundTasks, owner: str = Depends(jobs.job_owner)) -> Job:
    req.audio_path = str(user_file(req.audio_path, AUDIO, "song"))
    job = Job(job_type=JobType.STEM_SEPARATION, payload=req.dict())
    job_store[str(job.id)] = job
    job.message = "Separating stems…"

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

            # Each job separates into a folder of its own, deleted afterwards, so two songs
            # with the same file name can't mix their stems and the disk doesn't fill up
            settings.INTERIM_DIR.mkdir(parents=True, exist_ok=True)
            work = Path(tempfile.mkdtemp(prefix="stems-", dir=settings.INTERIM_DIR))
            try:
                loop = asyncio.get_event_loop()
                stems_dict = await loop.run_in_executor(
                    None, run_with_context(run_separation, str(audio_path), work, req.model)
                )

                report("Saving the stem files…")
                j.progress = 90

                # MP3 at the original's bitrate (96-192 kbps) instead of WAV: up to 14x smaller,
                # so the stem player loads a 4-minute song in ~15-23 MB instead of ~170 MB
                artifacts: Dict[str, str] = {}
                bitrate = stem_bitrate(audio_path)
                for stem_name, stem_path in stems_dict.items():
                    mp3 = await loop.run_in_executor(
                        None, convert_audio_format, stem_path, Path(stem_path).with_suffix(".mp3"), "mp3", bitrate
                    )
                    artifacts[stem_name] = save_artifact(
                        j, output_name(audio_path, stem_name, ".mp3"), mp3.read_bytes()
                    )
            finally:
                shutil.rmtree(work, ignore_errors=True)

            j.mark_success(
                {"artifacts": artifacts, "metrics": {"model": req.model, "stems": list(stems_dict.keys())}},
                message="Stem separation complete",
            )
        except Exception as e:  # pragma: no cover
            j.mark_failed(str(e), f"Failed while: {j.stage or 'starting'}")

    async def _run(j: Job) -> None:
        with reporting(j):
            await _worker(j)

    return jobs.submit(bg, job, _run, owner)


@router.get("/jobs/{job_id}", response_model=Job)
async def get_stems_job(job_id: str) -> Job:
    job = job_store.get(job_id)
    if not job or job.job_type != JobType.STEM_SEPARATION:
        raise HTTPException(status_code=404, detail="Stems job not found")
    return job
