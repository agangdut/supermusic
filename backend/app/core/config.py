from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Simple, dependency-free settings (no pydantic-settings required)
# Uses env vars if present, otherwise sensible defaults.

@dataclass(frozen=True)
class Settings:
    # Root paths
    REPO_ROOT: Path = Path(__file__).resolve().parents[2]
    DATA_DIR: Path = Path(os.getenv("SM_DATA_DIR", "") or (Path(__file__).resolve().parents[2] / "data"))
    RAW_DIR: Path = Path(os.getenv("SM_RAW_DIR", "" ) or (Path(__file__).resolve().parents[2] / "data" / "raw"))
    INTERIM_DIR: Path = Path(os.getenv("SM_INTERIM_DIR", "" ) or (Path(__file__).resolve().parents[2] / "data" / "interim"))
    PROCESSED_DIR: Path = Path(os.getenv("SM_PROCESSED_DIR", "" ) or (Path(__file__).resolve().parents[2] / "data" / "processed"))
    SAMPLES_DIR: Path = Path(os.getenv("SM_SAMPLES_DIR", "" ) or (Path(__file__).resolve().parents[2] / "data" / "samples"))
    STATIC_DIR: Path = Path(os.getenv("SM_STATIC_DIR", "" ) or (Path(__file__).resolve().parents[2] / "static"))

    # Downloading
    YTDLP_FORMAT: str = os.getenv("SM_YTDLP_FORMAT", "bestaudio/best")
    YTDLP_OUTTEMPLATE: str = os.getenv("SM_YTDLP_OUTTEMPLATE", "%(title).200B.%(ext)s")

    # Audio defaults
    SR: int = int(os.getenv("SM_SR", "22050"))  # librosa default SR

    # Separation / Transcription tool switches (external CLIs)
    DEMUCS_BIN: str = os.getenv("SM_DEMUCS_BIN", "demucs")          # if installed
    BASIC_PITCH_BIN: str = os.getenv("SM_BASIC_PITCH_BIN", "basic-pitch")  # if installed
    # tflite-runtime can't load the model under numpy 2, so default to ONNX
    BASIC_PITCH_SERIALIZATION: str = os.getenv("SM_BASIC_PITCH_SERIALIZATION", "onnx")
    # Tuned on MAESTRO validation (36 combinations): note F1 0.675 → 0.744 vs Basic Pitch defaults (0.5 / 0.3 / 127.7)
    BASIC_PITCH_ONSET: float = float(os.getenv("SM_BASIC_PITCH_ONSET", "0.6"))
    BASIC_PITCH_FRAME: float = float(os.getenv("SM_BASIC_PITCH_FRAME", "0.3"))
    BASIC_PITCH_MIN_NOTE_MS: float = float(os.getenv("SM_BASIC_PITCH_MIN_NOTE_MS", "58"))

    # Visualization
    FIG_DPI: int = int(os.getenv("SM_FIG_DPI", "140"))

# ensure key dirs exist at import time
def _ensure_dirs(s: Settings) -> None:
    for d in [s.DATA_DIR, s.RAW_DIR, s.INTERIM_DIR, s.PROCESSED_DIR, s.SAMPLES_DIR, s.STATIC_DIR]:
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

settings = Settings()
_ensure_dirs(settings)
