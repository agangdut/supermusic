"""
Client for the GAME service (services/game): turns an isolated singing voice
into notes. Full-band models catch the band well but miss much of the vocal
line; GAME is trained only on singing, so it handles slides, vibrato and
repeated syllables better.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from app.core import modal_engines
from app.core.config import settings

URL = os.getenv("GAME_URL", "http://game:8300")


def available() -> bool:
    if modal_engines.enabled("game"):
        return True
    try:
        with urllib.request.urlopen(f"{URL}/health", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def separate_vocals(audio_path: str | Path, out_dir: Path) -> tuple[Path, Path]:
    """Demucs voice/rest split on the GAME container's GPU. Raises RuntimeError if that isn't possible."""
    audio_path = Path(audio_path).resolve()
    if settings.DATA_DIR.resolve() not in audio_path.parents:  # the GAME container only sees data/
        raise RuntimeError("audio is outside the shared data folder")
    body = {"audio_path": str(audio_path), "out_dir": str(out_dir)}
    if modal_engines.enabled("game"):
        res = modal_engines.post("game", "/separate", body)
        return Path(res["vocals"]), Path(res["no_vocals"])
    req = urllib.request.Request(f"{URL}/separate", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=1800) as r:
            res = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(json.loads(e.read() or b"{}").get("detail", f"GAME error {e.code}"))
    except urllib.error.URLError:
        raise RuntimeError("The GAME service isn't running")
    return Path(res["vocals"]), Path(res["no_vocals"])


def on_gpu() -> bool:
    if modal_engines.enabled("game"):
        return True
    try:
        with urllib.request.urlopen(f"{URL}/health", timeout=3) as r:
            return json.loads(r.read()).get("device") == "cuda"
    except Exception:
        return False


def transcribe_singing(vocal_path: str | Path, out_dir: Path | None = None) -> Path:
    vocal_path = Path(vocal_path)
    out_dir = (out_dir or (settings.PROCESSED_DIR / "midi")) / uuid.uuid4().hex
    body = {"audio_path": str(vocal_path.resolve()), "out_dir": str(out_dir)}
    if modal_engines.enabled("game"):
        return Path(modal_engines.post("game", "/transcribe", body)["midi_path"])
    req = urllib.request.Request(f"{URL}/transcribe", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3600) as r:
            return Path(json.loads(r.read())["midi_path"])
    except urllib.error.HTTPError as e:
        raise RuntimeError(json.loads(e.read() or b"{}").get("detail", f"GAME error {e.code}"))
    except urllib.error.URLError:
        raise RuntimeError("The GAME vocal service isn't running. Start it with: docker compose up -d game")
