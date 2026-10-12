"""
Small HTTP wrapper around GAME, a singing-voice-to-notes model, so the main
backend can turn an isolated vocal (a Demucs vocal stem) into a melody.

POST /transcribe {"audio_path": "/app/data/...vocals.wav", "out_dir": "/app/data/..."}
  -> {"midi_path": "...", "notes": 123, "seconds": 4.2, "device": "cuda"}
POST /separate {"audio_path": "/app/data/...song.mp3", "out_dir": "/app/data/..."}
  -> {"vocals": ".../vocals.wav", "no_vocals": ".../no_vocals.wav", "seconds": 6.1, "device": "cuda"}
  Demucs (htdemucs, voice vs the rest) on this container's GPU.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

GAME_DIR = Path(os.getenv("GAME_DIR", "/opt/game"))
SIZE = os.getenv("GAME_MODEL", "medium")  # small / medium / large
MODELS = Path(os.getenv("GAME_MODELS_DIR", "/app/data/models/game"))
URL = f"https://github.com/openvpi/GAME/releases/download/v1.0.0/GAME-1.0-{SIZE}.zip"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

app = FastAPI(title="GAME")
_lock = threading.Lock()


def checkpoint() -> Path:
    path = MODELS / f"GAME-1.0-{SIZE}" / "model.pt"
    if path.exists():
        return path
    MODELS.mkdir(parents=True, exist_ok=True)
    tmp = MODELS / f"{SIZE}.zip.part"
    urllib.request.urlretrieve(URL, tmp)
    with zipfile.ZipFile(tmp) as z:
        z.extractall(MODELS)
    tmp.unlink()
    if not path.exists():
        raise RuntimeError(f"GAME download didn't contain {path.name}")
    return path


class Req(BaseModel):
    audio_path: str
    out_dir: str


@app.get("/health")
def health():
    return {"device": DEVICE, "model": SIZE, "downloaded": (MODELS / f"GAME-1.0-{SIZE}" / "model.pt").exists()}


@app.post("/separate")
def separate(req: Req):
    audio = Path(req.audio_path)
    if not audio.exists():
        raise HTTPException(404, f"Audio not found: {audio}")
    t = time.time()
    with _lock:  # one GPU job at a time
        proc = subprocess.run(
            [sys.executable, "-m", "demucs.separate", "-n", "htdemucs", "--two-stems", "vocals", "-d", DEVICE,
             "-o", req.out_dir, str(audio)], capture_output=True, text=True)
    folder = Path(req.out_dir) / "htdemucs" / audio.stem
    if proc.returncode != 0 or not (folder / "vocals.wav").exists():
        raise HTTPException(500, f"Demucs failed: {(proc.stderr or proc.stdout)[-800:]}")
    return {"vocals": str(folder / "vocals.wav"), "no_vocals": str(folder / "no_vocals.wav"),
            "seconds": round(time.time() - t, 1), "device": DEVICE}


@app.post("/transcribe")
def transcribe(req: Req):
    audio = Path(req.audio_path)
    if not audio.exists():
        raise HTTPException(404, f"Audio not found: {audio}")
    t = time.time()
    with _lock:
        try:
            model = checkpoint()
        except Exception as e:
            raise HTTPException(503, f"GAME couldn't get its model: {e}")
        out = Path(req.out_dir)
        work = out / "_game"
        work.mkdir(parents=True, exist_ok=True)
        src = work / f"{audio.stem}.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(audio), "-ac", "1", str(src)], check=True)
        proc = subprocess.run(
            [sys.executable, "infer.py", "extract", str(src), "-m", str(model), "--output-dir", str(work),
             "--precision", "16-mixed" if DEVICE == "cuda" else "32-true"],
            cwd=GAME_DIR, capture_output=True, text=True)
        midi = work / f"{audio.stem}.mid"
        if proc.returncode != 0 or not midi.exists():
            raise HTTPException(500, f"GAME failed: {(proc.stderr or proc.stdout)[-800:]}")
        final = out / f"{audio.stem}.mid"
        shutil.move(str(midi), final)
        shutil.rmtree(work, ignore_errors=True)
    import pretty_midi

    notes = sum(len(i.notes) for i in pretty_midi.PrettyMIDI(str(final)).instruments)
    return {"midi_path": str(final), "notes": notes, "seconds": round(time.time() - t, 1), "device": DEVICE}
