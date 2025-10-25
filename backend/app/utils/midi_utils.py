from __future__ import annotations

from typing import Dict, Tuple


def transcribe_to_midi_bytes(
    source_path: str,
    onset_sensitivity: float = 0.6,
    model: str = "basic",
) -> Tuple[bytes, Dict[str, float]]:
    """
    Return a tiny but valid Standard MIDI file (SMF) header+track.
    This is a placeholder; swap in real transcription later.
    """
    # Header (MThd), format 1, one track, division 480 (0x01E0)
    header = b"MThd\x00\x00\x00\x06\x00\x01\x00\x01\x01\xE0"
    # Single empty track with End-of-Track meta event
    track = b"MTrk\x00\x00\x00\x04\x00\xFF\x2F\x00"
    midi = header + track
    metrics = {"model": model, "onset_sensitivity": float(onset_sensitivity), "input": source_path}
    return midi, metrics
