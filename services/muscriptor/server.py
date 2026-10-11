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
from pathlib import Path

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
        t.notes.sort(key=lambda n: (n.start, n.pitch))
    pm.write(str(path))
    return sum(len(t.notes) for t in pm.instruments)


class Req(BaseModel):
    audio_path: str
    out_dir: str


@app.get("/health")
def health():
    return {"loaded": _model is not None, "token": bool(os.getenv("HF_TOKEN")), "device": DEVICE, "model": SIZE}


@app.post("/transcribe")
def transcribe(req: Req):
    audio = Path(req.audio_path)
    if not audio.exists():
        raise HTTPException(404, f"Audio not found: {audio}")
    t = time.time()
    try:
        m = model()
    except Exception as e:  # most often: licence not accepted or HF_TOKEN missing
        raise HTTPException(503, f"MuScriptor couldn't load its model: {e}")
    out = Path(req.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{audio.stem}.mid"
    with tempfile.TemporaryDirectory() as tmp, _lock:  # one song at a time on the GPU
        # The model reads WAV/MP3/FLAC itself, but not M4A and the like: give it a plain WAV
        wav = Path(tmp) / "audio.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(audio), "-ac", "1", "-ar", "16000", str(wav)],
                       check=True)
        events = list(m.transcribe(str(wav)))
    notes = write_midi(events, path)
    return {"midi_path": str(path), "notes": notes, "seconds": round(time.time() - t, 1), "device": DEVICE, "model": SIZE}
