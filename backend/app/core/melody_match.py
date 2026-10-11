"""
Melody match: how closely a MIDI file follows what the singer actually sings.

The idea is to draw two pitch "shapes" over time and lay them on top of each
other:

* the **sung shape** comes straight from the isolated vocal stem: every 20 ms
  a pitch tracker (pYIN) says which pitch the voice is on, or that it's silent;
* the **MIDI shape** is the melody line of the transcription: the "Lead
  vocal" track if there is one, otherwise the highest note playing at each
  moment (the tune usually sits on top).

Then we count, over the moments where the singer is singing:

  melody_match   the MIDI plays the right note (within half a semitone).
                 This is the headline number: higher is better.
  octave_ok      right note name but maybe in the wrong octave (a common,
                 forgivable mistake; a piano cover often moves the tune up).
  coverage       the MIDI plays *some* note while the voice sings.
  extra          share of the MIDI melody where the singer is actually silent
                 (stray notes; lower is better).

These are the standard melody-extraction scores (raw pitch accuracy, raw
chroma accuracy, voicing recall, voicing false alarm), so numbers can be
compared between modes and songs. It needs no hand-made answer key, which is
what makes it usable on any pop song, but it only judges the melody, not the
chords, bass or drums.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import numpy as np

SR = 16000
HOP = 320                 # 20 ms per frame
TOLERANCE = 0.5           # semitones: "same note" if within half a semitone
VOICE_WORDS = ("sing", "voice", "vocal")


def sung_pitch(vocals_path: str | Path) -> np.ndarray:
    """MIDI pitch (float) of the voice every 20 ms; NaN where it's silent."""
    import librosa

    y, _ = librosa.load(str(vocals_path), sr=SR, mono=True)
    if not np.any(y):
        return np.array([])
    f0, voiced, _ = librosa.pyin(
        y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C6"),
        sr=SR, frame_length=2048, hop_length=HOP,
    )
    # pYIN hears faint bleed from other instruments as "voiced"; ignore near-silence
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=HOP)[0][: len(f0)]
    loud = rms > max(1e-4, 0.05 * np.percentile(rms, 95))
    pitch = librosa.hz_to_midi(f0)
    pitch[~(voiced & loud)] = np.nan
    return pitch


def midi_melody(midi_path: str | Path, frames: int) -> np.ndarray:
    """The MIDI's melody line on the same 20 ms grid; NaN where nothing plays."""
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(str(midi_path))
    tuned = [i for i in pm.instruments if not i.is_drum]
    lead = [i for i in tuned if any(w in i.name.lower() for w in VOICE_WORDS)]
    notes = [n for i in (lead or tuned) for n in i.notes]
    line = np.full(frames, np.nan)
    step = HOP / SR
    for n in notes:
        a, b = int(round(n.start / step)), int(round(n.end / step))
        seg = line[a:min(b, frames)]
        # keep the highest note at each moment ("skyline")
        np.fmax(seg, n.pitch, out=seg)
    return line


def compare(sung: np.ndarray, played: np.ndarray) -> Dict[str, float]:
    n = min(len(sung), len(played))
    sung, played = sung[:n], played[:n]
    singing, playing = ~np.isnan(sung), ~np.isnan(played)
    both = singing & playing
    if not singing.any():
        raise ValueError("No singing found in the vocal stem.")
    diff = np.abs(np.where(both, sung, 0) - np.where(both, played, 0))
    exact = both & (diff <= TOLERANCE)
    octave = both & (np.abs(((diff + 6) % 12) - 6) <= TOLERANCE)
    pct = lambda x: round(100 * float(x), 1)  # noqa: E731
    return {
        "melody_match": pct(exact.sum() / singing.sum()),
        "octave_ok": pct(octave.sum() / singing.sum()),
        "coverage": pct(both.sum() / singing.sum()),
        "extra": pct((playing & ~singing).sum() / playing.sum()) if playing.any() else 0.0,
        "sung_seconds": round(float(singing.sum()) * HOP / SR, 1),
    }


def melody_match(midi_path: str | Path, vocals_path: str | Path,
                 sung: Optional[np.ndarray] = None) -> Dict[str, float]:
    """Score one MIDI file against an isolated vocal. Pass `sung` to reuse a
    pitch track when scoring several MIDI files against the same song."""
    if sung is None:
        sung = sung_pitch(vocals_path)
    return compare(sung, midi_melody(midi_path, len(sung)))
