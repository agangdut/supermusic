"""
Piano mode: high-resolution piano transcription trained on MAESTRO.

Uses ByteDance's CRNN model (Kong et al., 2021, note F1 0.968 on MAESTRO)
through the `piano_transcription_inference` package. The ~170 MB checkpoint
is downloaded once into data/models and reused. Best for solo piano; for
anything else the default Basic Pitch model is the better choice.
"""
from __future__ import annotations

import os
import threading
import urllib.request
import uuid
from pathlib import Path

from app.core.config import settings

CHECKPOINT_URL = (
    "https://zenodo.org/record/4034264/files/"
    "CRNN_note_F1%3D0.9677_pedal_F1%3D0.9186.pth?download=1"
)
CHECKPOINT_MIN_BYTES = 160_000_000

_model = None
_lock = threading.Lock()


def checkpoint_path() -> Path:
    return Path(os.getenv("SM_PIANO_CHECKPOINT", "") or settings.DATA_DIR / "models" / "piano_transcription.pth")


def ensure_checkpoint() -> Path:
    """Download the checkpoint if it isn't there yet. Safe to call repeatedly."""
    path = checkpoint_path()
    if path.exists() and path.stat().st_size >= CHECKPOINT_MIN_BYTES:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    urllib.request.urlretrieve(CHECKPOINT_URL, tmp)
    if tmp.stat().st_size < CHECKPOINT_MIN_BYTES:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("Piano model download was incomplete. Try again.")
    tmp.replace(path)
    return path


def _load():
    global _model
    with _lock:
        if _model is None:
            import torch
            from piano_transcription_inference import PianoTranscription

            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            _model = PianoTranscription(device=device, checkpoint_path=str(ensure_checkpoint()))
        return _model


def transcribe_piano(audio_path: str | Path, out_dir: Path | None = None) -> Path:
    """Transcribe a piano recording to MIDI (notes, velocities and sustain pedal)."""
    import librosa
    from piano_transcription_inference import sample_rate

    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    out_dir = (out_dir or (settings.PROCESSED_DIR / "midi")) / uuid.uuid4().hex
    out_dir.mkdir(parents=True, exist_ok=True)
    midi_path = out_dir / f"{audio_path.stem}.mid"

    # The package's own load_audio breaks on current librosa, so load it ourselves
    audio, _ = librosa.load(str(audio_path), sr=sample_rate, mono=True)
    model = _load()
    with _lock:  # one transcription at a time; the model isn't thread-safe
        model.transcribe(audio, str(midi_path))
    return midi_path


def warm_up() -> None:
    """Fetch the checkpoint in the background so the first piano job doesn't wait."""
    try:
        ensure_checkpoint()
    except Exception:
        pass
