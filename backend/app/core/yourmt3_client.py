"""
Client for the YourMT3+ service (services/yourmt3), a multi-instrument
transcriber that runs in its own container, on the GPU when there is one.
It writes a multi-track MIDI with an instrument per track (piano, guitar,
bass, strings, drums, ...).
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

URL = os.getenv("YOURMT3_URL", "http://yourmt3:8100")


def available() -> bool:
    try:
        with urllib.request.urlopen(f"{URL}/health", timeout=3) as r:
            return bool(json.loads(r.read()).get("loaded"))
    except Exception:
        return False


def transcribe_multi(audio_path: str | Path, out_dir: Path | None = None) -> Path:
    audio_path = Path(audio_path)
    out_dir = (out_dir or (settings.PROCESSED_DIR / "midi")) / uuid.uuid4().hex
    body = json.dumps({"audio_path": str(audio_path.resolve()), "out_dir": str(out_dir)}).encode()
    req = urllib.request.Request(f"{URL}/transcribe", data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3600) as r:
            midi = Path(json.loads(r.read())["midi_path"])
    except urllib.error.HTTPError as e:
        raise RuntimeError(json.loads(e.read() or b"{}").get("detail", f"YourMT3+ error {e.code}"))
    except urllib.error.URLError:
        raise RuntimeError("The YourMT3+ service isn't running. Start it with: docker compose up -d yourmt3")
    final = out_dir / f"{audio_path.stem}.mid"
    shutil.move(str(midi), final)
    return final
