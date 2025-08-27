#!/usr/bin/env python3
"""
Audio → Sheet Music (MIDI + MusicXML)
-------------------------------------
CLI tool to turn an MP3/WAV file into a rough score.

Two backends are supported:
  1) basic-pitch  – polyphonic transcription using a neural model (if installed)
  2) pyin         – monophonic pitch tracking with librosa.pyin (fallback)

Outputs:
  - <basename>.mid      (MIDI)
  - <basename>.musicxml (MusicXML for MuseScore/Finale/Sibelius)

Usage:
  python audiotranscript.py input.mp3 --backend auto
  python audiotranscript.py input.mp3 -o out_dir --quant 16 --min-note 0.10

Recommended setup (Windows/macOS/Linux):
  python -m venv .venv && source .venv/bin/activate  # (Windows: .venv\\Scripts\\activate)
  pip install --upgrade pip
  pip install librosa music21 pretty_midi
  # Optional (polyphonic):
  # pip install basic-pitch

Notes:
- For best results with songs that have many instruments, first isolate the piano/vocal
  stem with a source-separation tool (e.g., demucs/spleeter), then run this script.
- The pyin backend works best on monophonic melody lines.
- MusicXML can be opened in MuseScore and exported to PDF as clean sheet music.

Author: you ✨
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

# --- Optional imports guarded with helpful errors ---
try:
    import librosa
    import librosa.display  # noqa: F401 (useful for debugging)
except Exception:
    print(
        "[fatal] librosa is required. Install with: pip install librosa",
        file=sys.stderr,
    )
    raise

try:
    from music21 import instrument, metadata, meter
    from music21 import note as m21note
    from music21 import stream
    from music21 import tempo as m21tempo
except Exception:
    print(
        "[fatal] music21 is required. Install with: pip install music21",
        file=sys.stderr,
    )
    raise

# pretty_midi is optional (helps write cleaner MIDI when using basic-pitch)
try:
    import pretty_midi  # noqa: F401

    HAS_PRETTY_MIDI = True
except Exception:
    HAS_PRETTY_MIDI = False

# basic-pitch (optional polyphonic backend)
BASIC_PITCH_AVAILABLE = False
try:
    # There are two public APIs across versions; we’ll support either.
    BASIC_PITCH_AVAILABLE = True
except Exception:
    try:
        BASIC_PITCH_AVAILABLE = True
    except Exception:
        BASIC_PITCH_AVAILABLE = False


# ---------------------------
# Utility helpers
# ---------------------------


def sec_to_qL(seconds: float, tempo_bpm: float) -> float:
    """Convert seconds to music21 quarterLength at a given tempo."""
    if tempo_bpm <= 0:
        tempo_bpm = 120.0
    quarter_sec = 60.0 / tempo_bpm
    return seconds / quarter_sec


def quantize_seconds(t: float, step_sec: float) -> float:
    if step_sec <= 0:
        return t
    return round(t / step_sec) * step_sec


# ---------------------------
# pyin backend (monophonic)
# ---------------------------


def transcribe_pyin(
    y: np.ndarray,
    sr: int,
    *,
    fmin: str = "C2",
    fmax: str = "C7",
    hop_length: int = 256,
    min_note_sec: float = 0.08,
) -> tuple[list[tuple[float, float, int]], float]:
    """Return list of notes as (start_sec, end_sec, midi_pitch) and estimated tempo.

    This segments continuous voiced regions from librosa.pyin, maps to median pitch,
    and filters out super short blips.
    """
    # Tempo estimate (for quantization & score durations)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    tempo = float(tempo) if np.isfinite(tempo) and tempo > 0 else 120.0

    # pyin f0 track
    f0, vflag, vprob = librosa.pyin(
        y,
        fmin=librosa.note_to_hz(fmin),
        fmax=librosa.note_to_hz(fmax),
        frame_length=2048,
        hop_length=hop_length,
    )
    times = librosa.times_like(f0, sr=sr, hop_length=hop_length)

    notes: list[tuple[float, float, int]] = []
    i = 0
    n = len(f0)
    while i < n:
        # Skip unvoiced frames
        while i < n and (not vflag[i] or not np.isfinite(f0[i])):
            i += 1
        if i >= n:
            break
        start = times[i]
        pitches = []
        # Accumulate contiguous voiced frames
        while i < n and vflag[i] and np.isfinite(f0[i]):
            pitches.append(f0[i])
            i += 1
        end = times[min(i, n - 1)] if i < n else times[-1]
        dur = float(end - start)
        if dur >= min_note_sec and len(pitches) > 0:
            midi = int(np.rint(librosa.hz_to_midi(np.median(pitches))))
            # Clip to MIDI 21-108 (piano range) for nicer scores
            midi = int(np.clip(midi, 21, 108))
            notes.append((float(start), float(end), midi))
    return notes, tempo


# ---------------------------
# basic-pitch backend (polyphonic)
# ---------------------------


def transcribe_basic_pitch(audio_path: str, out_midi_path: str) -> bool:
    """Use basic-pitch to predict and save a MIDI file directly.

    Returns True if we could save a MIDI file to out_midi_path.
    """
    if not BASIC_PITCH_AVAILABLE:
        return False
    try:
        # Try the newer convenience API first
        from basic_pitch.inference import predict_and_save  # type: ignore

        out_dir = Path(out_midi_path).parent
        out_dir.mkdir(parents=True, exist_ok=True)
        predict_and_save(
            [audio_path],
            output_directory=str(out_dir),
            save_midi=True,
            save_model_outputs=False,
        )
        # basic-pitch names files like <name>_basic_pitch.mid; move/rename if present
        base = Path(audio_path).stem
        produced = list(out_dir.glob(f"{base}*_basic_pitch.mid"))
        if produced:
            produced[0].rename(out_midi_path)
            return True
    except Exception:
        # Fallback to lower-level API; leave as best-effort
        try:
            from basic_pitch import save_predictions  # type: ignore
            from basic_pitch.inference import predict  # type: ignore

            audio, sr = librosa.load(audio_path, sr=22050, mono=True)
            model_output, midi_data, note_events = predict(audio, sr)
            # Save MIDI via helper
            out_dir = Path(out_midi_path).parent
            out_dir.mkdir(parents=True, exist_ok=True)
            save_predictions.save_midi(midi_data, out_midi_path)
            return True
        except Exception:
            return False
    return False


# ---------------------------
# Build a score with music21
# ---------------------------


def notes_to_music21(
    notes: list[tuple[float, float, int]],
    tempo_bpm: float,
    quantize_to: int = 16,
    title: str | None = None,
    instrument_name: str = "Piano",
) -> stream.Stream:
    """Create a music21 Stream from timed MIDI notes.

    - quantize_to: rhythmic grid denominator (e.g., 16 = sixteenth-note grid)
    """
    s = stream.Stream()
    if title:
        md = metadata.Metadata()
        md.title = title
        s.insert(0, md)

    s.append(m21tempo.MetronomeMark(number=float(tempo_bpm)))
    s.append(meter.TimeSignature("4/4"))

    # Instrument
    try:
        instr = getattr(instrument, instrument_name.replace(" ", ""))()
    except Exception:
        instr = instrument.Piano()
    s.append(instr)

    # Quantization step (in seconds)
    quarter_sec = 60.0 / float(tempo_bpm if tempo_bpm > 0 else 120.0)
    step_sec = quarter_sec * (4.0 / float(quantize_to))  # e.g., 16th = quarter/4

    # Sort & quantize
    notes = sorted(notes, key=lambda x: x[0])
    qnotes: list[tuple[float, float, int]] = []
    for st, en, midi in notes:
        st_q = quantize_seconds(st, step_sec)
        en_q = quantize_seconds(en, step_sec)
        if en_q <= st_q:
            en_q = st_q + step_sec
        qnotes.append((st_q, en_q, midi))

    # Build sequential stream with rests
    t_cursor = 0.0
    for st, en, midi in qnotes:
        # Insert rest if gap
        if st > t_cursor + 1e-4:
            rest_qL = sec_to_qL(st - t_cursor, tempo_bpm)
            r = m21note.Rest()
            r.duration.quarterLength = max(rest_qL, 0.25)
            s.append(r)
            t_cursor = st
        dur_qL = sec_to_qL(en - st, tempo_bpm)
        n = m21note.Note(midi)
        n.duration.quarterLength = max(dur_qL, 0.25)
        s.append(n)
        t_cursor = en

    return s


# ---------------------------
# Main
# ---------------------------


def main():
    p = argparse.ArgumentParser(description="Transcribe audio to MIDI + MusicXML")
    p.add_argument("audio", help="Path to input audio (mp3/wav/flac)")
    p.add_argument(
        "-o",
        "--out-dir",
        default=None,
        help="Output directory (default: alongside input)",
    )
    p.add_argument(
        "--backend",
        choices=["auto", "basic-pitch", "pyin"],
        default="auto",
        help="Transcription backend",
    )
    p.add_argument(
        "--quant",
        type=int,
        default=16,
        help="Quantization grid (e.g., 16 for sixteenths)",
    )
    p.add_argument(
        "--min-note",
        type=float,
        default=0.08,
        help="Minimum note length in seconds (pyin)",
    )
    p.add_argument("--title", default=None, help="Title for the score (optional)")
    p.add_argument(
        "--instrument",
        default="Piano",
        help="Music21 instrument name (e.g., Piano, AcousticGuitar)",
    )
    args = p.parse_args()

    audio_path = Path(args.audio)
    if not audio_path.exists():
        print(f"[fatal] Audio file not found: {audio_path}", file=sys.stderr)
        sys.exit(2)

    out_dir = Path(args.out_dir) if args.out_dir else audio_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    base = audio_path.stem
    out_midi = out_dir / f"{base}.mid"
    out_xml = out_dir / f"{base}.musicxml"

    backend = args.backend
    if backend == "auto":
        backend = "basic-pitch" if BASIC_PITCH_AVAILABLE else "pyin"

    print(f"[info] Backend: {backend}")

    if backend == "basic-pitch":
        ok = transcribe_basic_pitch(str(audio_path), str(out_midi))
        if not ok:
            print("[warn] basic-pitch not available or failed. Falling back to pyin…")
            backend = "pyin"
        else:
            # We still generate MusicXML by loading the MIDI into music21
            try:
                s = stream.Score()
                s.insert(0, metadata.Metadata())
                s.metadata.title = args.title or base
                # music21 can parse MIDI back into a Stream
                from music21 import converter

                s = converter.parse(str(out_midi))
                s.write("musicxml", fp=str(out_xml))
                print(f"[ok] Wrote: {out_midi}\n[ok] Wrote: {out_xml}")
                return
            except Exception as e:
                print(
                    f"[warn] Could not render MusicXML from MIDI: {e}. Continuing with pyin backup."
                )
                backend = "pyin"

    if backend == "pyin":
        print("[info] Loading audio…")
        y, sr = librosa.load(str(audio_path), sr=22050, mono=True)
        print("[info] Pitch tracking (pyin)…")
        notes, tempo_bpm = transcribe_pyin(y, sr, min_note_sec=float(args.min_note))
        if len(notes) == 0:
            print(
                "[error] No notes detected. Try increasing --min-note or using basic-pitch."
            )
            sys.exit(1)
        print(
            f"[info] Estimated tempo: {tempo_bpm:.1f} bpm; notes detected: {len(notes)}"
        )
        print("[info] Building score…")
        s = notes_to_music21(
            notes,
            tempo_bpm=tempo_bpm,
            quantize_to=int(args.quant),
            title=args.title or base,
            instrument_name=args.instrument,
        )
        print("[info] Writing files…")
        s.write("midi", fp=str(out_midi))
        s.write("musicxml", fp=str(out_xml))
        print(f"[ok] Wrote: {out_midi}\n[ok] Wrote: {out_xml}")


if __name__ == "__main__":
    main()
