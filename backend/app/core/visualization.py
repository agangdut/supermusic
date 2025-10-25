from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import numpy as np

try:
    import librosa
    import librosa.display  # noqa: F401
except Exception as e:  # pragma: no cover
    librosa = None
    _librosa_error = e

import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt  # noqa: E402

from app.core.config import settings


def _load(audio_path: str | Path) -> Tuple[np.ndarray, int]:
    if librosa is None:
        raise RuntimeError(
            f"librosa is not available: {_librosa_error}. "
            "Install it to enable visualizations."
        )
    y, sr = librosa.load(str(audio_path), sr=settings.SR, mono=True)
    return y, sr


def save_waveform_png(audio_path: str | Path, out_path: str | Path | None = None) -> Path:
    """
    Save a waveform image (PNG). Returns the output path.
    """
    y, sr = _load(audio_path)
    out_path = Path(out_path or (settings.STATIC_DIR / (Path(audio_path).stem + "_waveform.png")))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    plt.figure(figsize=(10, 3), dpi=settings.FIG_DPI)
    plt.plot(np.arange(len(y)) / sr, y)
    plt.xlabel("Time (s)")
    plt.ylabel("Amplitude")
    plt.title("Waveform")
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()
    return out_path


def save_melspectrogram_png(audio_path: str | Path, out_path: str | Path | None = None) -> Path:
    """
    Save a log-mel spectrogram image (PNG). Returns the output path.
    """
    y, sr = _load(audio_path)
    out_path = Path(out_path or (settings.STATIC_DIR / (Path(audio_path).stem + "_mel.png")))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    S = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=128)
    S_db = librosa.power_to_db(S, ref=np.max)

    plt.figure(figsize=(10, 3), dpi=settings.FIG_DPI)
    plt.imshow(S_db, origin="lower", aspect="auto")
    plt.colorbar(format="%+2.0f dB")
    plt.xlabel("Frames")
    plt.ylabel("Mel bins")
    plt.title("Log-Mel Spectrogram")
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()
    return out_path
