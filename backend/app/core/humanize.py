"""
Make a generated piano part sound played, not typed, and render it to audio.

Pop2Piano writes every note at the same loudness and never touches the
sustain pedal, so it sounds mechanical however good the notes are. This adds:

- dynamics that follow the original song (quiet verse, loud chorus), with the
  melody voiced above the accompaniment and the bass slightly forward,
- sustain pedal, changed with each new bass note the way pianists pedal pop
  accompaniments, and lifted when the bass rests so it doesn't blur.

`render_audio` plays the result through a real piano sound (FluidSynth) so
you can hear it properly; Windows' built-in MIDI player makes anything sound
cheap.
"""
from __future__ import annotations

import os
import random
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

SOUNDFONT = os.getenv("SM_SOUNDFONT", "/usr/share/sounds/sf2/FluidR3_GM.sf2")
CHORD_WINDOW = 0.03
BASS_BELOW = 55          # G3: notes under this count as the bass line
PEDAL_GAP = 0.06         # how long the pedal is up when it's changed
PEDAL_MAX_HOLD = 2.0     # lift if the bass hasn't moved for this long


def _loudness_curve(audio_path: Path, hop_s: float = 0.05):
    """Song loudness over time, smoothed over ~2 s and scaled 0..1."""
    import librosa
    import numpy as np

    y, sr = librosa.load(str(audio_path), sr=22050, mono=True)
    hop = int(sr * hop_s)
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    db = librosa.amplitude_to_db(rms + 1e-6)
    k = max(1, int(2.0 / hop_s))
    db = np.convolve(db, np.ones(k) / k, mode="same")
    lo, hi = np.percentile(db, [10, 95])
    curve = np.clip((db - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    return lambda t: float(curve[min(len(curve) - 1, max(0, int(t / hop_s)))])


def _groups(notes) -> List[list]:
    groups: List[list] = []
    for n in sorted(notes, key=lambda n: (n.start, n.pitch)):
        if groups and n.start - groups[-1][0].start <= CHORD_WINDOW:
            groups[-1].append(n)
        else:
            groups.append([n])
    return groups


def _pedal(notes) -> list:
    """Sustain pedal: re-pedal on every new bass note, lift when the bass rests."""
    import pretty_midi

    bass_onsets = sorted({round(n.start, 3) for n in notes if n.pitch < BASS_BELOW})
    if not bass_onsets:
        return []
    end = max(n.end for n in notes)
    events = []
    for i, t in enumerate(bass_onsets):
        nxt = bass_onsets[i + 1] if i + 1 < len(bass_onsets) else end
        events.append(pretty_midi.ControlChange(64, 0, max(0.0, t - 0.005)))
        events.append(pretty_midi.ControlChange(64, 100, t + PEDAL_GAP))
        if nxt - t > PEDAL_MAX_HOLD:
            events.append(pretty_midi.ControlChange(64, 0, t + PEDAL_MAX_HOLD))
    events.append(pretty_midi.ControlChange(64, 0, end))
    return events


def humanize(midi_path: str | Path, audio_path: str | Path | None = None,
             out_path: str | Path | None = None, seed: int = 0) -> Path:
    """Add dynamics and pedal to a piano MIDI. Overwrites it unless `out_path` is given."""
    import pretty_midi

    midi_path = Path(midi_path)
    out_path = Path(out_path) if out_path else midi_path
    pm = pretty_midi.PrettyMIDI(str(midi_path))
    loud = _loudness_curve(Path(audio_path)) if audio_path else (lambda t: 0.5)
    rng = random.Random(seed)

    for inst in pm.instruments:
        if inst.is_drum or not inst.notes:
            continue
        for chord in _groups(inst.notes):
            base = 48 + 44 * loud(chord[0].start)  # pp-ish verse to f chorus
            top = max(n.pitch for n in chord)
            bottom = min(n.pitch for n in chord)
            for n in chord:
                if n.pitch == top:
                    v = base + 10            # melody sings over the rest
                elif n.pitch == bottom and n.pitch < BASS_BELOW:
                    v = base + 2             # bass slightly forward
                else:
                    v = base - 10            # inner voices sit back
                n.velocity = int(max(20, min(115, v + rng.uniform(-4, 4))))
        if not any(cc.number == 64 for cc in inst.control_changes):
            inst.control_changes += _pedal(inst.notes)
    pm.write(str(out_path))
    return out_path


def can_render() -> bool:
    return bool(shutil.which("fluidsynth")) and Path(SOUNDFONT).exists()


def render_audio(midi_path: str | Path, out_path: str | Path | None = None) -> Optional[Path]:
    """Render MIDI to MP3 with a real piano sound. Returns None if FluidSynth isn't installed."""
    if not can_render():
        return None
    midi_path = Path(midi_path)
    out_path = Path(out_path) if out_path else midi_path.with_suffix(".mp3")
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "render.wav"
        subprocess.run(["fluidsynth", "-ni", "-g", "0.8", "-r", "44100", "-F", str(wav), SOUNDFONT, str(midi_path)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav),
                        "-af", "loudnorm=I=-16:TP=-1.5", "-b:a", "192k", str(out_path)], check=True)
    return out_path
