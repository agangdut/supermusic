from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field, model_validator

from ..models.job import Job, JobStatus, JobType
from ..utils.storage import job_store, save_artifact
from app.core.humanize import render_audio
from app.core.piano_cover import piano_cover
from app.core.piano_transcription import transcribe_piano
from app.core.smart_transcription import transcribe_auto, transcribe_stems
from app.core.playability import DEFAULT_SPAN, make_playable, playability_report
from app.core.transcription import transcribe_to_midi
from app.core.yourmt3_client import transcribe_multi
from app.core.progress import estimate_seconds, report, reporting, run_with_context
from app.core.vocals import lead_vocal_track, transcribe_vocal_aware

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


STEM_NAMES = ("vocals", "drums", "bass", "guitar", "piano", "other")


class MIDIConvertRequest(BaseModel):
    source_path: Optional[str] = Field(None, description="Input audio file (wav/mp3). Not needed with stem_job_id.")
    onset_sensitivity: float = Field(0.6, ge=0.0, le=1.0)
    model: str = Field(
        "basic",
        description=(
            '"auto" (detect the instruments and pick the best of the others), '
            '"basic" (Basic Pitch, any instrument, fastest), '
            '"piano" (MAESTRO-trained, solo piano), '
            '"stems" (split into 6 stems, transcribe each, multi-track MIDI), '
            '"cover" (Pop2Piano: arrange the song for solo piano), '
            '"multi" (YourMT3+: every instrument in a full mix, best on bands; needs the yourmt3 service).'
        ),
        pattern="^(auto|basic|piano|stems|cover|multi)$",
    )
    composer: str = Field("composer1", description="Piano cover style, composer1 to composer21.", pattern="^composer([1-9]|1[0-9]|2[01])$")
    playable: bool = Field(False, description="Rewrite the MIDI so two hands (10 fingers) can play it.")
    vocal_track: bool = Field(
        True,
        description="Give the voice its own clean melody track. For General this first separates the voice "
                    "(slower) so it can't turn into instrument notes.",
    )
    hand_span: int = Field(DEFAULT_SPAN, ge=10, le=17, description="Widest stretch per hand, in semitones (12 = octave, 14 = ninth, 16 = tenth).")
    stems: Optional[List[str]] = Field(
        None,
        description=f"Stems mode only: transcribe just these stems ({', '.join(STEM_NAMES)}). Empty means all.",
    )
    stem_job_id: Optional[str] = Field(
        None,
        description="Reuse the stems of a finished stem-separation job instead of separating again "
                    "(implies the stems model).",
    )

    @model_validator(mode="after")
    def _check(self):
        if self.stems:
            self.stems = [s.lower() for s in self.stems]
            bad = [s for s in self.stems if s not in STEM_NAMES]
            if bad:
                raise ValueError(f"Unknown stem(s): {', '.join(bad)}. Choose from {', '.join(STEM_NAMES)}.")
        if self.stem_job_id:
            self.model = "stems"
        elif not self.source_path:
            raise ValueError("Give source_path (an audio file) or stem_job_id (an earlier stem separation).")
        return self


def _separated_stems(job_id: str) -> tuple[Path, Dict[str, str]]:
    """The original audio and the stem files of a finished stem-separation job."""
    job = job_store.get(job_id)
    if not job or job.job_type != JobType.STEM_SEPARATION:
        raise HTTPException(status_code=404, detail="Stem separation job not found")
    if job.status != JobStatus.done or not (job.result or {}).get("artifacts"):
        raise HTTPException(status_code=409, detail="That stem separation hasn't finished yet")
    stems = {name: path for name, path in job.result["artifacts"].items() if Path(path).exists()}
    return Path((job.payload or {}).get("audio_path", "")), stems


@router.post("/convert", response_model=Job)
async def convert_to_midi(req: MIDIConvertRequest, bg: BackgroundTasks) -> Job:
    separated = _separated_stems(req.stem_job_id) if req.stem_job_id else None
    if separated:
        if not req.source_path:
            req.source_path = str(separated[0])
        if req.stems:
            missing = [s for s in req.stems if s not in separated[1]]
            if missing:
                raise HTTPException(status_code=400, detail=f"That separation has no {', '.join(missing)} stem")
    job = Job(job_type=JobType.MIDI_CONVERSION, payload=req.dict())
    job_store[str(job.id)] = job
    job.mark_running("Transcribing audio to MIDI…")

    async def _worker(j: Job) -> None:
        try:
            report("Checking the audio file…")
            audio_path = Path(req.source_path)
            if not audio_path.exists() and not separated:
                raise FileNotFoundError(f"Audio file not found: {audio_path}")
            try:
                import librosa

                duration_s = float(librosa.get_duration(path=str(audio_path)))
            except Exception:
                duration_s = None
            if separated:  # no separation to wait for, just one General pass per picked stem
                per_stem = estimate_seconds("basic", duration_s)
                j.eta_s = per_stem and round(per_stem * len(req.stems or separated[1]), 1)
            else:
                j.eta_s = estimate_seconds(req.model, duration_s, vocal_split=(req.model == "basic" and req.vocal_track))
            j.progress = 5

            def run():
                report({
                    "auto": "Listening for which instruments are playing…",
                    "piano": "Transcribing piano…",
                    "stems": (
                        f"Transcribing the {' + '.join(req.stems) if req.stems else 'separated'} stems…" if separated
                        else "Splitting the song into 6 parts…"
                    ),
                    "cover": "Arranging a piano cover…",
                    "multi": "Transcribing every instrument with YourMT3+…",
                }.get(req.model, "Transcribing…"))
                if req.model == "auto":
                    return transcribe_auto(audio_path)
                if req.model == "stems":
                    return transcribe_stems(audio_path, only=req.stems or None, stems=separated[1] if separated else None)
                if req.model == "multi":
                    midi = transcribe_multi(audio_path)
                    if not req.vocal_track:
                        return midi, {}
                    report("Cleaning up the vocal melody…")
                    return lead_vocal_track(midi)
                if req.model == "basic" and req.vocal_track:
                    return transcribe_vocal_aware(audio_path, transcribe_to_midi)
                if req.model == "cover":
                    return piano_cover(audio_path, composer=req.composer), {}
                fn = transcribe_piano if req.model == "piano" else transcribe_to_midi
                return fn(str(audio_path)), {}

            # Run transcription in executor to avoid blocking
            loop = asyncio.get_event_loop()
            midi_path, info = await loop.run_in_executor(None, run_with_context(run))

            report("Saving the MIDI file…")
            j.progress = 90

            artifacts = {}
            playability = None
            if req.playable:
                report("Arranging for two hands…")
                playable_path, playability = await loop.run_in_executor(
                    None, lambda: make_playable(midi_path, hand_span=req.hand_span)
                )
                artifacts["midi_original"] = save_artifact(j, f"{audio_path.stem}.mid", midi_path.read_bytes())
                midi_path = playable_path

            # A listenable piano rendering, when FluidSynth is installed
            report("Rendering a piano preview…")
            preview = await loop.run_in_executor(None, render_audio, midi_path)
            if preview:
                artifacts["preview"] = save_artifact(j, preview.name, preview.read_bytes())

            # Read MIDI file and save as artifact
            midi_bytes = midi_path.read_bytes()
            artifact_path = save_artifact(j, midi_path.name if req.playable else f"{audio_path.stem}.mid", midi_bytes)
            
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
            j.mark_failed(str(e), f"Failed while: {j.stage or 'starting'}")

    async def _run(j: Job) -> None:
        with reporting(j):
            await _worker(j)

    bg.add_task(_run, job)
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
