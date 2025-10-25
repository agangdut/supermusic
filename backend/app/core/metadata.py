from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

try:
    import librosa
except Exception as e:  # pragma: no cover
    librosa = None
    _librosa_error = e

from app.core.config import settings


# crude key mapping helper
_PITCH_CLASS_TO_KEY = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _estimate_key(y: np.ndarray, sr: int) -> Optional[str]:
    """
    Very rough key estimation via chroma energy peak (CENS).
    Not musicologically perfect; just a quick heuristic.
    """
    try:
        chroma = librosa.feature.chroma_cens(y=y, sr=sr)  # (12, frames)
        pitch_class = int(chroma.mean(axis=1).argmax())
        return _PITCH_CLASS_TO_KEY[pitch_class]
    except Exception:
        return None


def extract_basic_audio_features(audio_path: str | Path) -> Dict[str, Any]:
    """
    Extract lightweight features: duration_sec, bpm, key (rough), sr.
    Requires librosa. Returns an info dict; missing fields become None.
    """
    if librosa is None:
        raise RuntimeError(
            f"librosa is not available: {_librosa_error}. "
            "Install it (and soundfile) to enable metadata extraction."
        )

    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    y, sr = librosa.load(str(audio_path), sr=settings.SR, mono=True)
    duration_sec = float(librosa.get_duration(y=y, sr=sr))

    bpm = None
    try:
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = int(round(float(tempo)))
    except Exception:
        pass

    key = _estimate_key(y, sr)

    return {
        "path": str(audio_path),
        "sr": sr,
        "duration_sec": duration_sec,
        "bpm": bpm,
        "key": key,
    }


def enrich_track_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Given a CSV-like row with fields {title, artist, local_path? youtube_url?},
    ensure we have a local audio path and enrich with basic features.
    """
    local_path = record.get("local_path") or ""
    youtube_url = record.get("youtube_url") or ""

    path = local_path or youtube_url
    if not path:
        raise ValueError("Record must include either 'local_path' or 'youtube_url'.")

    # If it's a URL, downloader should be called upstream; here we only read features.
    return extract_basic_audio_features(path)
