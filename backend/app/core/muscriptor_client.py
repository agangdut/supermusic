"""
Client for the MuScriptor service (services/muscriptor), a multi-instrument
transcriber from 2026 trained on far more real recordings than YourMT3+.
Runs in its own container, on the GPU when there is one, and writes a
multi-track MIDI with an instrument per track.
"""
from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from app.core.config import settings

URL = os.getenv("MUSCRIPTOR_URL", "http://muscriptor:8200")


def available() -> bool:
    """Running, and able to load its model (already loaded, or has a Hugging Face token)."""
    try:
        with urllib.request.urlopen(f"{URL}/health", timeout=3) as r:
            h = json.loads(r.read())
            return bool(h.get("loaded") or h.get("token"))
    except Exception:
        return False


def transcribe_muscriptor(audio_path: str | Path, out_dir: Path | None = None) -> Path:
    audio_path = Path(audio_path)
    out_dir = (out_dir or (settings.PROCESSED_DIR / "midi")) / uuid.uuid4().hex
    body = json.dumps({"audio_path": str(audio_path.resolve()), "out_dir": str(out_dir)}).encode()
    req = urllib.request.Request(f"{URL}/transcribe", data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3600) as r:
            midi = Path(json.loads(r.read())["midi_path"])
    except urllib.error.HTTPError as e:
        raise RuntimeError(json.loads(e.read() or b"{}").get("detail", f"MuScriptor error {e.code}"))
    except urllib.error.URLError:
        raise RuntimeError("The MuScriptor service isn't running. Start it with: docker compose up -d muscriptor")
    final = out_dir / f"{audio_path.stem}.mid"
    if midi != final:
        shutil.move(str(midi), final)
    return final
