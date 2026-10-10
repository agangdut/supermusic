"""
Smarter audio → MIDI for real songs.

Two ideas, built on the 6-stem Demucs model (vocals, drums, bass, guitar,
piano, other):

* **Stems mode**: separate the song first, then transcribe each part on its
  own so drums and vocals stop being mistaken for notes. Piano goes through
  the MAESTRO piano model, drums become a General MIDI drum track, and every
  other part goes through Basic Pitch. The result is one multi-track MIDI
  with a named track per instrument.

* **Auto mode**: separate a short excerpt, measure how much of the energy
  each instrument carries, and pick the best model: Piano when the track is
  mostly piano, Stems for busy mixes, General otherwise.
"""
from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

from app.core.config import settings
from app.core.piano_transcription import transcribe_piano
from app.core.separator import separate_stems
from app.core.transcription import transcribe_to_midi

SIX_STEM_MODEL = "htdemucs_6s"

# General MIDI programs for each stem (0-based)
PROGRAMS = {"piano": 0, "guitar": 25, "bass": 33, "vocals": 53, "other": 48}
GM_KICK, GM_SNARE, GM_HAT = 36, 38, 42

# Auto-mode thresholds (share of total energy, 0..1)
PIANO_DOMINANT = 0.6   # piano is basically the whole track → Piano model alone
PIANO_PRESENT = 0.15   # piano is a real part of a band → Stems
BUSY_MIX = 0.25        # drums + vocals above this → Stems
MIN_STEM_SHARE = 0.02  # skip near-silent stems
PIANO_TRACK_MIN = 0.08 # below this the "piano" stem is usually just leakage


def _work_dir(name: str) -> Path:
    d = settings.INTERIM_DIR / name / uuid.uuid4().hex
    d.mkdir(parents=True, exist_ok=True)
    return d


def _energy(path: str | Path) -> float:
    import soundfile as sf

    total = 0.0
    with sf.SoundFile(str(path)) as f:
        for block in f.blocks(blocksize=262144, dtype="float32"):
            total += float(np.square(block).sum())
    return total


def stem_shares(stems: Dict[str, str]) -> Dict[str, float]:
    energies = {name: _energy(p) for name, p in stems.items()}
    total = sum(energies.values()) or 1.0
    return {name: round(e / total, 3) for name, e in sorted(energies.items(), key=lambda kv: -kv[1])}


# ---------------------------------------------------------------------------
# Drums → General MIDI
# ---------------------------------------------------------------------------

def drums_to_notes(path: str | Path):
    """Turn a drum stem into kick / snare / hi-hat hits from onsets and their spectrum."""
    import librosa
    import pretty_midi

    from scipy.signal import find_peaks

    y, sr = librosa.load(str(path), sr=22050, mono=True)
    if not np.any(y):
        return []
    hop = 512
    strength = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    peak = float(strength.max()) or 1.0
    # librosa's own peak picker crashes (numba gufunc) in this image, so use scipy's
    frames, _ = find_peaks(
        strength,
        height=float(strength.mean() + 0.5 * strength.std()),
        distance=max(1, int(0.06 * sr / hop)),  # at most one hit per 60 ms per stem
    )
    onsets = frames * hop
    notes = []
    win = int(0.05 * sr)
    freqs = np.fft.rfftfreq(win, 1 / sr)
    low, mid, high = freqs < 150, (freqs >= 150) & (freqs < 4000), freqs >= 6000
    for s in onsets:
        seg = y[s: s + win]
        if len(seg) < win:
            seg = np.pad(seg, (0, win - len(seg)))
        spec = np.abs(np.fft.rfft(seg * np.hanning(win))) ** 2
        e_low, e_mid, e_high = spec[low].sum(), spec[mid].sum(), spec[high].sum()
        pitch = GM_KICK if e_low >= max(e_mid, e_high) else GM_HAT if e_high >= e_mid else GM_SNARE
        frame = min(len(strength) - 1, s // hop)
        velocity = int(np.clip(40 + 87 * strength[frame] / peak, 1, 127))
        t = s / sr
        notes.append(pretty_midi.Note(velocity=velocity, pitch=pitch, start=t, end=t + 0.1))
    return notes


# ---------------------------------------------------------------------------
# Stems mode
# ---------------------------------------------------------------------------

def transcribe_stems(audio_path: str | Path, out_dir: Optional[Path] = None) -> Tuple[Path, Dict]:
    """Separate into 6 stems, transcribe each, merge. Returns (midi_path, info)."""
    import pretty_midi

    audio_path = Path(audio_path)
    stems = separate_stems(audio_path, _work_dir("stems6"), model=SIX_STEM_MODEL)
    shares = stem_shares(stems)

    merged = pretty_midi.PrettyMIDI()
    tracks: Dict[str, int] = {}
    for name, path in stems.items():
        if shares.get(name, 0) < MIN_STEM_SHARE:
            continue
        if name == "piano" and shares.get(name, 0) < PIANO_TRACK_MIN:
            continue
        if name == "drums":
            inst = pretty_midi.Instrument(program=0, is_drum=True, name="Drums")
            inst.notes = drums_to_notes(path)
        else:
            # The piano model copes with a band around it far better than with
            # Demucs' piano stem (0.87 vs 0.66 note F1 in scripts/eval_mix.py),
            # so it listens to the original mix.
            midi = transcribe_piano(audio_path) if name == "piano" else transcribe_to_midi(path)
            inst = pretty_midi.Instrument(program=PROGRAMS.get(name, 0), name=name.capitalize())
            for src in pretty_midi.PrettyMIDI(str(midi)).instruments:
                inst.notes.extend(src.notes)
                if name == "piano":
                    inst.control_changes.extend(src.control_changes)  # sustain pedal
            if name == "vocals":
                from app.core.vocals import VOCAL_PROGRAM, clean_melody

                # A voice sings one note at a time; Basic Pitch hears chords in it
                inst.notes = clean_melody(inst.notes)
                inst.program, inst.name = VOCAL_PROGRAM, "Lead vocal"
        if inst.notes:
            merged.instruments.append(inst)
            tracks[name] = len(inst.notes)

    if not merged.instruments:
        raise RuntimeError("No notes found in any stem.")
    out_dir = (out_dir or (settings.PROCESSED_DIR / "midi")) / uuid.uuid4().hex
    out_dir.mkdir(parents=True, exist_ok=True)
    midi_path = out_dir / f"{audio_path.stem}.mid"
    merged.write(str(midi_path))
    return midi_path, {"stem_shares": shares, "tracks": tracks}


# ---------------------------------------------------------------------------
# Auto mode
# ---------------------------------------------------------------------------

def _excerpt(audio_path: Path, seconds: int = 30) -> Path:
    """Middle `seconds` of the track as WAV (intros are often unrepresentative)."""
    import soundfile as sf

    duration = sf.info(str(audio_path)).duration if audio_path.suffix.lower() in {".wav", ".flac", ".ogg"} else None
    if duration is None:
        import librosa

        duration = librosa.get_duration(path=str(audio_path))
    start = max(0.0, duration / 2 - seconds / 2)
    out = _work_dir("excerpt") / "excerpt.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-t", str(seconds), "-i", str(audio_path), str(out)],
        check=True,
    )
    return out


def detect_instruments(audio_path: str | Path) -> Dict[str, float]:
    """Energy share per instrument, measured on a 30-second excerpt."""
    excerpt = _excerpt(Path(audio_path))
    stems = separate_stems(excerpt, _work_dir("detect"), model=SIX_STEM_MODEL)
    return stem_shares(stems)


def choose_model(shares: Dict[str, float], multi_available: bool = False) -> Tuple[str, str]:
    piano = shares.get("piano", 0)
    busy = shares.get("drums", 0) + shares.get("vocals", 0)
    if piano >= PIANO_DOMINANT:
        return "piano", f"mostly piano ({round(piano * 100)}% of the sound)"
    if multi_available:
        # YourMT3+ beats Stems and General on everything but solo piano
        # (piano in a band: 0.92 vs 0.87 vs 0.47 note F1; see docs/transcription-accuracy.md)
        top = max(shares, key=shares.get) if shares else "unknown"
        return "multi", f"a mix led by {top} ({round(shares.get(top, 0) * 100)}%)"
    if piano >= PIANO_PRESENT:
        return "stems", f"piano in a band ({round(piano * 100)}% piano)"
    if busy >= BUSY_MIX:
        return "stems", f"a full mix with drums/vocals ({round(busy * 100)}% of the sound)"
    top = max(shares, key=shares.get) if shares else "unknown"
    return "basic", f"mainly {top} ({round(shares.get(top, 0) * 100)}%)"


def transcribe_auto(audio_path: str | Path) -> Tuple[Path, Dict]:
    from app.core.yourmt3_client import available, transcribe_multi

    shares = detect_instruments(audio_path)
    model, why = choose_model(shares, multi_available=available())
    if model == "piano":
        midi, info = transcribe_piano(audio_path), {}
    elif model == "multi":
        from app.core.vocals import lead_vocal_track

        midi, info = lead_vocal_track(transcribe_multi(audio_path))
    elif model == "stems":
        midi, info = transcribe_stems(audio_path)
    else:
        midi, info = transcribe_to_midi(audio_path), {}
    return midi, {"chosen_model": model, "reason": why, "detected": shares, **info}
