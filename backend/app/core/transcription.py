from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional

from app.core.config import settings


def _which(bin_name: str) -> Optional[str]:
    return shutil.which(bin_name)


def transcribe_to_midi(audio_path: str | Path, out_dir: Path | None = None) -> Path:
    """
    Transcribe polyphonic audio to MIDI using an external CLI if available.
    For a quick start, this function tries BASIC PITCH's CLI (`basic-pitch`).
      Install: pip install basic-pitch

    Returns the generated MIDI Path. Raises a clear error if no tool is present.
    """
    basic_pitch = _which(settings.BASIC_PITCH_BIN)
    if not basic_pitch:
        raise RuntimeError(
            "No transcription backend found. Install Basic Pitch CLI with `pip install basic-pitch` "
            "or wire your preferred model here."
        )

    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    # basic-pitch refuses to overwrite an existing .mid, so each run gets its own folder
    out_dir = (out_dir or (settings.PROCESSED_DIR / "midi")) / uuid.uuid4().hex
    out_dir.mkdir(parents=True, exist_ok=True)

    # basic-pitch <output_dir> <input_audio>
    cmd = [basic_pitch, "--model-serialization", settings.BASIC_PITCH_SERIALIZATION, str(out_dir), str(audio_path)]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"basic-pitch failed ({proc.returncode}):\n{proc.stdout}")

    # Find newest .mid
    midi = max(out_dir.glob("*.mid"), key=lambda p: p.stat().st_mtime, default=None)
    if not midi:
        raise RuntimeError("Transcription completed but no MIDI file was produced.")
    return midi
