#!/usr/bin/env python3
"""
Audio → Sheet Music (MIDI + MusicXML)
-------------------------------------
CLI tool to turn an MP3/WAV file (or YouTube link) into a rough score.

Two backends are supported:
  1) basic-pitch  – polyphonic transcription using a neural model (if installed)
  2) pyin         – monophonic pitch tracking with librosa.pyin (fallback)

Inputs:
  - Local audio file (mp3/wav/flac)
  - YouTube URL (requires yt-dlp)

Outputs:
  - <basename>.mid      (MIDI)
  - <basename>.musicxml (MusicXML for MuseScore/Finale/Sibelius)

Usage:
  python audiotranscript.py input.mp3 --backend auto
  python audiotranscript.py "https://www.youtube.com/watch?v=XXXX" -o out_dir

Recommended setup (Windows/macOS/Linux):
  python -m venv .venv && source .venv/bin/activate  # (Windows: .venv\\Scripts\\activate)
  pip install --upgrade pip
  pip install librosa music21 pretty_midi yt-dlp
  # Optional (polyphonic):
  # pip install basic-pitch

Author: A ✨
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np

# --- Optional imports ---
try:
    import librosa
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

try:
    import pretty_midi  # noqa

    HAS_PRETTY_MIDI = True
except Exception:
    HAS_PRETTY_MIDI = False

BASIC_PITCH_AVAILABLE = False
try:
    BASIC_PITCH_AVAILABLE = True
except Exception:
    try:
        BASIC_PITCH_AVAILABLE = True
    except Exception:
        BASIC_PITCH_AVAILABLE = False


def sec_to_qL(seconds: float, tempo_bpm: float) -> float:
    if tempo_bpm <= 0:
        tempo_bpm = 120.0
    quarter_sec = 60.0 / tempo_bpm
    return seconds / quarter_sec


def quantize_seconds(t: float, step_sec: float) -> float:
    if step_sec <= 0:
        return t
    return round(t / step_sec) * step_sec


def transcribe_pyin(
    y: np.ndarray,
    sr: int,
    *,
    fmin: str = "C2",
    fmax: str = "C7",
    hop_length: int = 256,
    min_note_sec: float = 0.08,
) -> tuple[list[tuple[float, float, int]], float]:
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    tempo = float(tempo) if np.isfinite(tempo) and tempo > 0 else 120.0
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
        while i < n and (not vflag[i] or not np.isfinite(f0[i])):
            i += 1
        if i >= n:
            break
        start = times[i]
        pitches = []
        while i < n and vflag[i] and np.isfinite(f0[i]):
            pitches.append(f0[i])
            i += 1
        end = times[min(i, n - 1)] if i < n else times[-1]
        dur = float(end - start)
        if dur >= min_note_sec and len(pitches) > 0:
            midi = int(np.rint(librosa.hz_to_midi(np.median(pitches))))
            midi = int(np.clip(midi, 21, 108))
            notes.append((float(start), float(end), midi))
    return notes, tempo


def transcribe_basic_pitch(audio_path: str, out_midi_path: str) -> bool:
    if not BASIC_PITCH_AVAILABLE:
        return False
    try:
        from basic_pitch.inference import predict_and_save  # type: ignore

        out_dir = Path(out_midi_path).parent
        out_dir.mkdir(parents=True, exist_ok=True)
        predict_and_save(
            [audio_path],
            output_directory=str(out_dir),
            save_midi=True,
            save_model_outputs=False,
        )
        base = Path(audio_path).stem
        produced = list(out_dir.glob(f"{base}*_basic_pitch.mid"))
        if produced:
            produced[0].rename(out_midi_path)
            return True
    except Exception:
        return False
    return False


def notes_to_music21(
    notes: list[tuple[float, float, int]],
    tempo_bpm: float,
    quantize_to: int = 16,
    title: str | None = None,
    instrument_name: str = "Piano",
) -> stream.Stream:
    s = stream.Stream()
    if title:
        md = metadata.Metadata()
        md.title = title
        s.insert(0, md)
    s.append(m21tempo.MetronomeMark(number=float(tempo_bpm)))
    s.append(meter.TimeSignature("4/4"))
    try:
        instr = getattr(instrument, instrument_name.replace(" ", ""))()
    except Exception:
        instr = instrument.Piano()
    s.append(instr)
    quarter_sec = 60.0 / float(tempo_bpm if tempo_bpm > 0 else 120.0)
    step_sec = quarter_sec * (4.0 / float(quantize_to))
    notes = sorted(notes, key=lambda x: x[0])
    qnotes: list[tuple[float, float, int]] = []
    for st, en, midi in notes:
        st_q = quantize_seconds(st, step_sec)
        en_q = quantize_seconds(en, step_sec)
        if en_q <= st_q:
            en_q = st_q + step_sec
        qnotes.append((st_q, en_q, midi))
    t_cursor = 0.0
    for st, en, midi in qnotes:
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
# Symbolic refinement using a MIDI prior or key guess
# ---------------------------


def build_prior_from_midi_dir(prior_dir: Path) -> tuple[set[int], list[float]]:
    """Scan a directory of MIDI/MusicXML and build a set of common pitch classes
    and a list of common durations (quarterLength values)."""
    pcs = Counter()
    durs = Counter()
    if not prior_dir.exists():
        return set(), []
    for fp in prior_dir.glob("**/*"):
        if fp.suffix.lower() not in {".mid", ".midi", ".musicxml", ".xml"}:
            continue
        try:
            from music21 import converter

            sc = converter.parse(str(fp))
            for n in sc.recurse().notes:
                try:
                    pc = int(n.pitch.midi) % 12
                    pcs[pc] += 1
                except Exception:
                    pass
                try:
                    ql = float(n.duration.quarterLength)
                    # clamp weird tuplets
                    if 0.125 <= ql <= 8.0:
                        durs[round(ql, 3)] += 1
                except Exception:
                    pass
        except Exception:
            continue
    # Keep most common pitch classes and durations
    top_pcs = {pc for pc, _ in pcs.most_common(7)} if pcs else set()
    top_durs = [v for v, _ in durs.most_common(8)] if durs else []
    return top_pcs, top_durs


def guess_key_pitch_classes(notes: list[tuple[float, float, int]]) -> set[int]:
    """Very simple key guess: choose the rotation of major/minor that covers
    the most note pitch-classes."""
    if not notes:
        return set()
    pcs = [m % 12 for _, _, m in notes]
    counts = Counter(pcs)
    major = {0, 2, 4, 5, 7, 9, 11}
    minor = {0, 2, 3, 5, 7, 8, 10}
    best_pcset: set[int] = set()
    best_score = -1
    for tonic in range(12):
        maj = {(p + tonic) % 12 for p in major}
        minr = {(p + tonic) % 12 for p in minor}
        smaj = sum(counts[p] for p in maj)
        smin = sum(counts[p] for p in minr)
        if smaj >= smin and smaj > best_score:
            best_score, best_pcset = smaj, maj
        elif smin > best_score:
            best_score, best_pcset = smin, minr
    return best_pcset


def snap_pitch_to_pc(midi: int, allowed_pcs: set[int]) -> int:
    if not allowed_pcs:
        return midi
    target_pc = midi % 12
    if target_pc in allowed_pcs:
        return midi
    # search nearest pitch (±6 semitones)
    best = midi
    best_dist = 128
    for d in range(-6, 7):
        cand = midi + d
        if cand < 0 or cand > 127:
            continue
        if (cand % 12) in allowed_pcs and abs(d) < best_dist:
            best = cand
            best_dist = abs(d)
            if best_dist == 0:
                break
    return best


def snap_duration_to_set(dur_qL: float, allowed_qL: list[float]) -> float:
    if not allowed_qL:
        return dur_qL
    return min(allowed_qL, key=lambda x: abs(x - dur_qL))


def refine_notes_with_prior(
    notes: list[tuple[float, float, int]],
    tempo_bpm: float,
    prior_pcs: set[int] | None = None,
    prior_durs: list[float] | None = None,
) -> list[tuple[float, float, int]]:
    if not notes:
        return notes
    pcs = (
        prior_pcs
        if prior_pcs is not None and len(prior_pcs) > 0
        else guess_key_pitch_classes(notes)
    )
    durs = prior_durs if prior_durs else [0.25, 0.5, 1.0, 1.5, 2.0]
    q = []
    quarter_sec = 60.0 / (tempo_bpm if tempo_bpm > 0 else 120.0)
    for st, en, m in notes:
        # snap pitch
        m2 = snap_pitch_to_pc(m, pcs)
        # snap duration in qL then back to seconds
        qL = max(sec_to_qL(en - st, tempo_bpm), 0.25)
        qL2 = snap_duration_to_set(qL, durs)
        dur2 = qL2 * quarter_sec
        q.append((st, st + dur2, int(m2)))
    return q


def download_youtube_audio(url: str, out_dir: Path) -> Path:
    """Download a YouTube link to MP3 using yt-dlp."""
    out_file = out_dir / "yt_download.mp3"
    cmd = ["yt-dlp", "-x", "--audio-format", "mp3", "-o", str(out_file), url]
    try:
        subprocess.run(cmd, check=True)
        return out_file
    except Exception as e:
        print(f"[fatal] Failed to download YouTube audio: {e}", file=sys.stderr)
        sys.exit(3)


def main():
    p = argparse.ArgumentParser(
        description="Transcribe audio/YouTube to MIDI + MusicXML"
    )
    p.add_argument("audio", help="Path to input audio (mp3/wav/flac) or YouTube URL")
    p.add_argument("-o", "--out-dir", default=None, help="Output directory")
    p.add_argument("--backend", choices=["auto", "basic-pitch", "pyin"], default="auto")
    p.add_argument("--quant", type=int, default=16, help="Quantization grid")
    p.add_argument(
        "--min-note", type=float, default=0.08, help="Minimum note length (pyin)"
    )
    p.add_argument("--title", default=None, help="Title for the score")
    p.add_argument("--instrument", default="Piano", help="Instrument name")
    p.add_argument(
        "--prior-dir",
        default=None,
        help="Directory of MIDI/MusicXML to build a style prior",
    )
    p.add_argument(
        "--refine",
        action="store_true",
        help="Enable symbolic refinement (snap to key/rhythm)",
    )
    args = p.parse_args()

    # Build prior (optional)
    prior_pcs, prior_durs = set(), []
    if args.prior_dir:
        prior_pcs, prior_durs = build_prior_from_midi_dir(Path(args.prior_dir))
        if prior_pcs:
            print(f"[info] Prior pitch-classes: {sorted(prior_pcs)}")
        if prior_durs:
            print(f"[info] Prior durations (qL): {prior_durs[:8]}")

    audio_input = args.audio
    out_dir = Path(args.out_dir) if args.out_dir else Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)

    # If input is a YouTube URL, download first
    if audio_input.startswith("http://") or audio_input.startswith("https://"):
        print("[info] Detected YouTube link. Downloading audio…")
        audio_path = download_youtube_audio(audio_input, out_dir)
    else:
        audio_path = Path(audio_input)
        if not audio_path.exists():
            print(f"[fatal] Audio file not found: {audio_path}", file=sys.stderr)
            sys.exit(2)

    base = audio_path.stem
    out_midi = out_dir / f"{base}.mid"
    out_xml = out_dir / f"{base}.musicxml"

    backend = args.backend
    if backend == "auto":
        backend = "basic-pitch" if BASIC_PITCH_AVAILABLE else "pyin"
    print(f"[info] Backend: {backend}")

    if backend == "basic-pitch":
        ok = transcribe_basic_pitch(str(audio_path), str(out_midi))
        if ok:
            try:
                from music21 import converter

                s = converter.parse(str(out_midi))
                s.write("musicxml", fp=str(out_xml))
                print(f"[ok] Wrote: {out_midi}\n[ok] Wrote: {out_xml}")
                return
            except Exception as e:
                print(
                    f"[warn] Could not render MusicXML from MIDI: {e}. Falling back to pyin…"
                )
                backend = "pyin"
        else:
            backend = "pyin"

    if backend == "pyin":
        print("[info] Loading audio…")
        y, sr = librosa.load(str(audio_path), sr=22050, mono=True)
        print("[info] Pitch tracking (pyin)…")
        notes, tempo_bpm = transcribe_pyin(y, sr, min_note_sec=float(args.min_note))
        if (args.prior_dir or args.refine) and len(notes) > 0:
            print("[info] Refining notes with symbolic prior/key…")
            notes = refine_notes_with_prior(
                notes,
                tempo_bpm,
                prior_pcs=prior_pcs if args.prior_dir else None,
                prior_durs=prior_durs if args.prior_dir else None,
            )
        if len(notes) == 0:
            print("[error] No notes detected.")
            sys.exit(1)
        print(
            f"[info] Estimated tempo: {tempo_bpm:.1f} bpm; notes detected: {len(notes)}"
        )
        s = notes_to_music21(
            notes,
            tempo_bpm,
            quantize_to=int(args.quant),
            title=args.title or base,
            instrument_name=args.instrument,
        )
        s.write("midi", fp=str(out_midi))
        s.write("musicxml", fp=str(out_xml))
        print(f"[ok] Wrote: {out_midi}\n[ok] Wrote: {out_xml}")


if __name__ == "__main__":
    main()
