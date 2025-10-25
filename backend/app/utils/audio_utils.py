from __future__ import annotations

import io
import wave
from typing import Dict, Iterable, Tuple


def _blank_wav_bytes(duration_s: float = 0.01, sr: int = 44100) -> bytes:
    """
    Create a minimal PCM WAV with silence—handy as a placeholder artifact.
    """
    nframes = max(1, int(duration_s * sr))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sr)
        wf.writeframes(b"\x00\x00" * 2 * nframes)
    return buf.getvalue()


def separate_stems(
    audio_path: str,
    stems: Iterable[str] = ("vocals", "drums", "bass", "other"),
    model: str = "htdemucs",
) -> Tuple[Dict[str, bytes], Dict[str, float]]:
    """
    Stub separation that returns tiny valid WAV bytes for each requested stem.
    Returns (artifacts, metrics).
    """
    artifacts = {stem: _blank_wav_bytes() for stem in stems}
    metrics = {"model": model, "input": audio_path, "num_stems": len(artifacts)}
    return artifacts, metrics
