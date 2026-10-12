"""
Vocal-aware transcription.

Transcription models hear a singer as just another instrument: sung or
rapped syllables turn into stray guitar, strings or synth notes, and the
real melody gets lost among them. This module separates the voice first:

1. Demucs splits the song into `vocals` and `no_vocals` (accompaniment).
2. The accompaniment is transcribed on its own, so the voice can't leak
   into instrument tracks.
3. The vocal stem is transcribed separately and cleaned up into a single
   monophonic "Lead vocal" melody (one note at a time, no blips).

`sung_ratio` measures how much of the vocal holds a steady pitch. It is
reported for information only: on real songs it didn't separate singing
from rap reliably (autotuned melodic rap scores higher than a soft ballad),
so the vocal track is always kept and you can mute it in the player.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

import numpy as np

from app.core.config import settings
from app.core.separator import separate_stems

VOCAL_PROGRAM = 53         # General MIDI "Voice Oohs"
MIN_NOTE = 0.08            # seconds; shorter melody notes are blips
MERGE_GAP = 0.04           # join same-pitch notes split by tiny gaps
VOCAL_SPAN = 14            # semitones either side of the melody's median pitch
VOCAL_PRESENT = 0.02       # vocal energy share below this = instrumental


def _work_dir() -> Path:
    d = settings.INTERIM_DIR / "vocals" / uuid.uuid4().hex
    d.mkdir(parents=True, exist_ok=True)
    return d


def split_vocals(audio_path: str | Path) -> Tuple[Path, Path, float]:
    """Returns (vocals.wav, no_vocals.wav, vocal share of the total energy)."""
    from app.core.smart_transcription import _energy

    stems = separate_stems(audio_path, _work_dir(), model="htdemucs", two_stems="vocals")
    v, a = Path(stems["vocals"]), Path(stems["no_vocals"])
    ev, ea = _energy(v), _energy(a)
    return v, a, ev / ((ev + ea) or 1.0)


def sung_ratio(vocals: Path) -> float:
    """How much of the voiced time holds a steady pitch (singing ≈ high, rap ≈ low)."""
    import librosa

    y, sr = librosa.load(str(vocals), sr=16000, mono=True)
    if not np.any(y):
        return 0.0
    hop = 160  # 10 ms
    f0 = librosa.yin(y, fmin=80, fmax=1000, sr=sr, frame_length=1024, hop_length=hop)
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=hop)[0][: len(f0)]
    voiced = rms > max(1e-4, 0.1 * np.percentile(rms, 95))
    cents = 1200 * np.log2(f0 / 440.0)
    # A frame is "held" if pitch stays within 50 cents across the next 100 ms
    win = 10
    held = np.zeros_like(voiced)
    for i in range(len(f0) - win):
        if voiced[i: i + win].all():
            seg = cents[i: i + win]
            held[i] = (seg.max() - seg.min()) < 50
    return float(held[voiced].mean()) if voiced.any() else 0.0


def clean_melody(notes):
    """One note at a time: keep the strongest, drop blips, merge tiny gaps."""
    import pretty_midi

    notes = sorted(notes, key=lambda n: n.start)
    mono = []
    for n in notes:
        if mono and n.start < mono[-1].end:
            prev = mono[-1]
            # overlapping: keep the louder/longer one, trim the other
            if (n.velocity, n.end - n.start) > (prev.velocity, prev.end - prev.start):
                prev.end = n.start
                if prev.end - prev.start < MIN_NOTE:
                    mono.pop()
                mono.append(n)
            continue
        mono.append(n)
    merged = []
    for n in mono:
        if merged and n.pitch == merged[-1].pitch and n.start - merged[-1].end <= MERGE_GAP:
            merged[-1].end = n.end
            continue
        merged.append(n)
    kept = [n for n in merged if n.end - n.start >= MIN_NOTE]
    if kept:
        # A lead vocal stays within about an octave of its centre; far-off notes are
        # bass or hi-hat bleed in the vocal stem, or octave errors
        centre = float(np.median([n.pitch for n in kept]))
        kept = [n for n in kept if abs(n.pitch - centre) <= VOCAL_SPAN]
    return [pretty_midi.Note(velocity=n.velocity, pitch=n.pitch, start=n.start, end=n.end) for n in kept]


def vocal_melody(vocals: Path, engine: Callable[[Path], Path]):
    """Transcribe the isolated vocal and reduce it to one melody line."""
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(str(engine(vocals)))
    singing = [i for i in pm.instruments if not i.is_drum and any(w in i.name.lower() for w in ("sing", "voice", "vocal"))]
    source = singing or [i for i in pm.instruments if not i.is_drum]
    return clean_melody([n for i in source for n in i.notes])


def transcribe_vocal_aware(audio_path: str | Path, engine: Callable[[Path], Path],
                           out_dir: Optional[Path] = None) -> Tuple[Path, Dict]:
    """Accompaniment through `engine`, vocals as a separate clean melody track."""
    import pretty_midi

    audio_path = Path(audio_path)
    from app.core.progress import report

    report("Separating the voice from the music…")
    vocals, backing, share = split_vocals(audio_path)
    info: Dict = {"vocal_share": round(share, 3)}

    if share < VOCAL_PRESENT:  # instrumental: nothing to separate
        info["vocals"] = "none detected"
        return Path(engine(audio_path)), info

    report("Transcribing the music without the voice…")
    accomp = pretty_midi.PrettyMIDI(str(engine(backing)))
    # anything the engine still calls a voice in the backing is leakage
    accomp.instruments = [i for i in accomp.instruments
                          if not any(w in i.name.lower() for w in ("sing", "voice", "vocal"))]
    for i in accomp.instruments:
        if not i.name.strip():
            i.name = "Instruments"

    report("Transcribing the vocal melody…")
    melody = vocal_melody(vocals, engine)
    inst = pretty_midi.Instrument(program=VOCAL_PROGRAM, name="Lead vocal")
    inst.notes = melody
    accomp.instruments.insert(0, inst)
    info["vocal_notes"] = len(melody)
    info["vocal_stem"] = str(vocals)  # lets the caller score the melody
    info["sung_ratio"] = round(sung_ratio(vocals), 3)

    out = (out_dir or settings.PROCESSED_DIR / "midi") / uuid.uuid4().hex
    out.mkdir(parents=True, exist_ok=True)
    midi_path = out / f"{audio_path.stem}.mid"
    accomp.write(str(midi_path))
    return midi_path, info


def lead_vocal_track(midi_path: str | Path) -> Tuple[Path, Dict]:
    """For multi-instrument output (YourMT3+): fold every singing-voice track into
    one clean, monophonic "Lead vocal" melody. No separation needed: in our tests
    YourMT3+ already labels the voice (scripts/eval_vocals.py), and splitting the
    voice off first cost piano accuracy (0.91 → 0.86)."""
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(str(midi_path))
    voice = [i for i in pm.instruments if not i.is_drum and any(w in i.name.lower() for w in ("sing", "voice", "vocal"))]
    if not voice:
        return Path(midi_path), {"vocals": "none detected"}
    lead = pretty_midi.Instrument(program=VOCAL_PROGRAM, name="Lead vocal")
    lead.notes = clean_melody([n for i in voice for n in i.notes])
    pm.instruments = [lead] + [i for i in pm.instruments if i not in voice]
    out = Path(midi_path).with_name(Path(midi_path).stem + "_lead.mid")
    pm.write(str(out))
    return out, {"vocal_notes": len(lead.notes)}


GAME_MIN_NOTE = 0.05  # seconds; GAME's own segmentation is good, so only drop clicks


def sung_lead_vocal(midi_path: str | Path, audio_path: str | Path) -> Tuple[Path, Dict]:
    """For full-band output: replace the model's own voice track with GAME's
    transcription of the separated vocal, which follows the singer more closely.
    Falls back to `lead_vocal_track` when the song has no vocals."""
    import pretty_midi

    from app.core.game_client import transcribe_singing
    from app.core.progress import begin

    begin("separate_vocals", "Separating the voice to transcribe the singing…")
    vocals, _backing, share = split_vocals(audio_path)
    if share < VOCAL_PRESENT:
        path, info = lead_vocal_track(midi_path)
        return path, {**info, "vocal_share": round(share, 3)}

    begin("game", "Transcribing the singing with GAME…")
    try:
        sung = pretty_midi.PrettyMIDI(str(transcribe_singing(vocals)))
    except RuntimeError:  # GAME down or failed: the full-band model's own voice track still works
        path, info = lead_vocal_track(midi_path)
        return path, {**info, "vocal_share": round(share, 3), "vocal_stem": str(vocals)}
    notes = sorted((n for i in sung.instruments for n in i.notes if n.end - n.start >= GAME_MIN_NOTE),
                   key=lambda n: n.start)
    pm = pretty_midi.PrettyMIDI(str(midi_path))
    voice = [i for i in pm.instruments if not i.is_drum and any(w in i.name.lower() for w in ("sing", "voice", "vocal"))]
    lead = pretty_midi.Instrument(program=VOCAL_PROGRAM, name="Lead vocal")
    lead.notes = [pretty_midi.Note(velocity=90, pitch=n.pitch, start=n.start, end=n.end) for n in notes]
    pm.instruments = [lead] + [i for i in pm.instruments if i not in voice]
    out = Path(midi_path).with_name(Path(midi_path).stem + "_lead.mid")
    pm.write(str(out))
    return out, {"vocal_notes": len(lead.notes), "vocal_engine": "GAME", "vocal_share": round(share, 3),
                 "vocal_stem": str(vocals)}
