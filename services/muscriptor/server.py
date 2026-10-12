"""
Small HTTP wrapper around MuScriptor so the main backend can call it.

POST /transcribe {"audio_path": "/app/data/...", "out_dir": "/app/data/..."}
  -> {"midi_path": "...", "seconds": 12.3, "device": "cuda", "model": "medium"}

Paths are inside the shared ./data volume. The model loads on the first
request (the weights download once into the data volume).
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import List, Optional

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

SIZE = os.getenv("MUSCRIPTOR_MODEL", "medium")  # small / medium / large (large needs >6 GB of GPU memory)
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

app = FastAPI(title="MuScriptor")
_model = None
_lock = threading.RLock()


def model():
    global _model
    with _lock:
        if _model is None:
            from muscriptor import TranscriptionModel

            _model = TranscriptionModel.load_model(weights_path=SIZE, device=DEVICE)
        return _model


def write_midi(events, path: Path) -> int:
    """Notes at the times the model heard them. MuScriptor's own MIDI writer shifts
    notes onto a detected beat grid, which reads well as sheet music but moves
    them away from the audio, so the MIDI is built here instead."""
    import pretty_midi
    from muscriptor import NoteEndEvent, NoteStartEvent

    m = model()
    pm = pretty_midi.PrettyMIDI()
    tracks: dict = {}
    for ev in events:
        if not isinstance(ev, NoteEndEvent):
            continue
        start: NoteStartEvent = ev.start_event
        drum = start.instrument == "drums"
        if start.instrument not in tracks:
            try:
                program = 0 if drum else m._program_for_instrument(start.instrument)
            except ValueError:
                program = 0
            tracks[start.instrument] = pretty_midi.Instrument(
                program=program, is_drum=drum, name=start.instrument.replace("_", " ").capitalize())
        end = max(ev.end_time, start.start_time + (0.05 if drum else 0.01))
        tracks[start.instrument].notes.append(pretty_midi.Note(90, start.pitch, start.start_time, end))
    pm.instruments = [t for t in tracks.values() if t.notes]
    for t in pm.instruments:
        t.notes = _trim_overlaps(t.notes)
    pm.write(str(path))
    return sum(len(t.notes) for t in pm.instruments)


def _trim_overlaps(notes: list) -> list:
    """Same clean-up as the official MIDI writer (trim_overlapping_notes): a note that is
    still sounding when the same pitch starts again ends there, and a note left with no
    length (the model wrote the same note twice at one moment) is dropped."""
    by_pitch: dict = {}
    for n in notes:
        by_pitch.setdefault(n.pitch, []).append(n)
    kept = []
    for same in by_pitch.values():
        same.sort(key=lambda n: n.start)
        for a, b in zip(same, same[1:]):
            if a.end > b.start:
                a.end = b.start
        kept += [n for n in same if n.start < n.end]
    return sorted(kept, key=lambda n: (n.start, n.pitch))


class Req(BaseModel):
    audio_path: str
    out_dir: str
    fast: Optional[bool] = None                 # None = the MUSCRIPTOR_FAST setting
    instruments: Optional[List[str]] = None     # only these instruments may appear (e.g. ["electric_bass"])
    beam_size: int = 1                          # >1 searches more alternatives: slower, maybe more accurate


# Speed/quality trade-off. Off (default): 5-second sections are transcribed one after
# another, each told which notes are still held from the last one. On: 4 sections at a
# time on the GPU, roughly 3x faster, with slightly worse joins between sections.
FAST = os.getenv("MUSCRIPTOR_FAST", "1") == "1"

_jobs: dict = {}
_gpu = threading.Lock()  # one song at a time on the GPU; others wait their turn


@app.get("/health")
def health():
    return {"loaded": _model is not None, "token": bool(os.getenv("HF_TOKEN")), "device": DEVICE,
            "model": SIZE, "fast": FAST}


def _run(job_id: str, audio: Path, out: Path, req: Req) -> dict:
    from muscriptor.events import ProgressEvent

    job = _jobs.setdefault(job_id, {"status": "waiting", "completed": 0, "total": None})
    t = time.time()
    job["status"] = "loading"
    try:
        m = model()
    except Exception as e:  # most often: licence not accepted or HF_TOKEN missing
        job.update(status="error", error=f"MuScriptor couldn't load its model: {e}")
        raise HTTPException(503, job["error"])
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{audio.stem}.mid"
    try:
        job["status"] = "waiting"
        with tempfile.TemporaryDirectory() as tmp, _gpu:
            job.update(status="running", started=time.time())
            # The model reads WAV/MP3/FLAC itself, but not M4A and the like: give it a plain WAV
            wav = Path(tmp) / "audio.wav"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(audio), "-ac", "1", "-ar", "16000",
                            str(wav)], check=True)
            fast = FAST if req.fast is None else req.fast
            kwargs = {"prelude_forcing": False, "batch_size": 4} if fast else {}
            if req.instruments:
                kwargs["instruments"] = req.instruments
            if req.beam_size > 1:
                kwargs["beam_size"] = req.beam_size
            events = []
            for ev in m.transcribe(str(wav), **kwargs):
                if isinstance(ev, ProgressEvent):
                    job.update(completed=ev.completed, total=ev.total)
                    if ev.completed == 0:
                        job["gen_started"] = time.time()
                    else:
                        # sections differ (busy ones take longer), so this is an average
                        per = (time.time() - job["gen_started"]) / ev.completed
                        job["remaining_s"] = round(per * (ev.total - ev.completed), 1)
                else:
                    events.append(ev)
        notes = write_midi(events, path)
    except Exception as e:
        job.update(status="error", error=str(e))
        raise
    result = {"midi_path": str(path), "notes": notes, "seconds": round(time.time() - t, 1),
              "device": DEVICE, "model": SIZE, "fast": fast}
    job.update(status="done", remaining_s=0, **result)
    return result


@app.post("/transcribe")
def transcribe(req: Req):
    """Blocking: returns when the MIDI is written."""
    audio = Path(req.audio_path)
    if not audio.exists():
        raise HTTPException(404, f"Audio not found: {audio}")
    return _run(uuid.uuid4().hex, audio, Path(req.out_dir), req)


@app.post("/jobs")
def start_job(req: Req):
    """Start in the background; poll GET /jobs/{id} for progress (sections done of total)."""
    audio = Path(req.audio_path)
    if not audio.exists():
        raise HTTPException(404, f"Audio not found: {audio}")
    job_id = uuid.uuid4().hex
    _jobs[job_id] = {"status": "waiting", "completed": 0, "total": None, "device": DEVICE}

    def work():
        try:
            _run(job_id, audio, Path(req.out_dir), req)
        except Exception:
            pass  # the error is on the job

    threading.Thread(target=work, daemon=True).start()
    return {"id": job_id}


@app.get("/jobs/{job_id}")
def job_status(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "No such job (the service may have restarted)")
    return {k: v for k, v in job.items() if k != "gen_started"}
