from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from ..models.job import Job, JobType
from ..utils.storage import job_store, save_artifact
from app.core.piano_cover import piano_cover
from app.core.piano_transcription import transcribe_piano
from app.core.smart_transcription import transcribe_auto, transcribe_stems
from app.core.playability import DEFAULT_SPAN, make_playable, playability_report
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
    model: str = Field(
        "basic",
        description=(
            '"auto" (detect the instruments and pick the best of the others), '
            '"basic" (Basic Pitch, any instrument, fastest), '
            '"piano" (MAESTRO-trained, solo piano), '
            '"stems" (split into 6 stems, transcribe each, multi-track MIDI), '
            '"cover" (Pop2Piano: arrange the song for solo piano).'
        ),
        pattern="^(auto|basic|piano|stems|cover)$",
    )
    composer: str = Field("composer1", description="Piano cover style, composer1 to composer21.", pattern="^composer([1-9]|1[0-9]|2[01])$")
    playable: bool = Field(False, description="Rewrite the MIDI so two hands (10 fingers) can play it.")
    hand_span: int = Field(DEFAULT_SPAN, ge=10, le=17, description="Widest stretch per hand, in semitones (12 = octave, 14 = ninth, 16 = tenth).")


@router.post("/convert", response_model=Job)
async def convert_to_midi(req: MIDIConvertRequest, bg: BackgroundTasks) -> Job:
    job = Job(job_type=JobType.MIDI_CONVERSION, payload=req.dict())
    job_store[str(job.id)] = job
    job.mark_running("Transcribing audio to MIDI…")

    async def _worker(j: Job) -> None:
        try:
            j.progress = 10
            j.message = "Loading audio file…"
            await asyncio.sleep(0.1)
            
            audio_path = Path(req.source_path)
            if not audio_path.exists():
                raise FileNotFoundError(f"Audio file not found: {audio_path}")
            
            j.progress = 30
            j.message = {
                "auto": "Listening for instruments, then transcribing…",
                "piano": "Transcribing piano to MIDI…",
                "stems": "Splitting into stems, then transcribing each…",
                "cover": "Arranging a piano cover…",
            }.get(req.model, "Transcribing to MIDI…")

            def run():
                if req.model == "auto":
                    return transcribe_auto(audio_path)
                if req.model == "stems":
                    return transcribe_stems(audio_path)
                if req.model == "cover":
                    return piano_cover(audio_path, composer=req.composer), {}
                fn = transcribe_piano if req.model == "piano" else transcribe_to_midi
                return fn(str(audio_path)), {}

            # Run transcription in executor to avoid blocking
            loop = asyncio.get_event_loop()
            midi_path, info = await loop.run_in_executor(None, run)

            j.progress = 80
            j.message = "Saving MIDI file…"
            
            artifacts = {}
            playability = None
            if req.playable:
                j.message = "Arranging for two hands…"
                playable_path, playability = await loop.run_in_executor(
                    None, lambda: make_playable(midi_path, hand_span=req.hand_span)
                )
                artifacts["midi_original"] = save_artifact(j, f"{audio_path.stem}.mid", midi_path.read_bytes())
                midi_path = playable_path

            # Read MIDI file and save as artifact
            midi_bytes = midi_path.read_bytes()
            artifact_path = save_artifact(j, midi_path.name if req.playable else f"{audio_path.stem}.mid", midi_bytes)
            
            # Get audio duration for metrics
            try:
                import librosa
                y, sr = librosa.load(str(audio_path), sr=None)
                duration_s = float(librosa.get_duration(y=y, sr=sr))
            except Exception:
                duration_s = None
            
            j.mark_success(
                {
                    "artifacts": {"midi": artifact_path, **artifacts},
                    "metrics": {
                        "duration_s": duration_s, "model": req.model, **info,
                        **({"playability": playability} if playability else {}),
                    },
                },
                message=(
                    f"MIDI conversion complete (detected {info['reason']}, used {info['chosen_model']})"
                    if "chosen_model" in info else "MIDI conversion complete"
                ),
            )
        except Exception as e:  # pragma: no cover
            j.mark_failed(str(e), "MIDI conversion failed")

    bg.add_task(_worker, job)
    return job


class PlayabilityRequest(BaseModel):
    midi_path: str = Field(..., description="MIDI file to score.")
    hand_span: int = Field(DEFAULT_SPAN, ge=10, le=17)


@router.post("/playability")
async def score_playability(req: PlayabilityRequest) -> Dict[str, Any]:
    """How much of a MIDI file two hands can play (100 = every moment)."""
    path = Path(req.midi_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"MIDI file not found: {path}")
    return playability_report(path, req.hand_span)


@router.get("/jobs/{job_id}", response_model=Job)
async def get_midi_job(job_id: str) -> Job:
    job = job_store.get(job_id)
    if not job or job.job_type != JobType.MIDI_CONVERSION:
        raise HTTPException(status_code=404, detail="MIDI job not found")
    return job
