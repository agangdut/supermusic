"""
On real songs: how many "instrument" notes are really the singer?

Ground-truth MIDI doesn't exist for most songs, so this compares two runs
of the same engine:

  full mix     the song as is
  backing      the same song with the vocal removed (Demucs no_vocals)

Instrument notes (anything not on a voice/vocal track) that appear in the
full-mix run but have no match in the backing run (same pitch, onset
within 50 ms) were caused by the voice. We report them per minute, and
how many of them sit on the vocal's own pitch (within a semitone of the
separated vocal's melody), which pins them on the singer.

    docker compose exec backend python scripts/eval_vocal_leakage.py song1.mp3 song2.mp3 --engines basic multi
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import numpy as np  # noqa: E402
import pretty_midi  # noqa: E402

VOICE = ("sing", "voice", "vocal")


def instrument_notes(midi: Path, seconds: float):
    pm = pretty_midi.PrettyMIDI(str(midi))
    return [n for i in pm.instruments if not i.is_drum and not any(w in i.name.lower() for w in VOICE)
            for n in i.notes if n.start < seconds]


def engine_fn(name):
    if name == "multi":
        from app.core.yourmt3_client import transcribe_multi
        return transcribe_multi
    from app.core.transcription import transcribe_to_midi
    return transcribe_to_midi


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("songs", nargs="+")
    ap.add_argument("--engines", nargs="+", default=["basic", "multi"])
    ap.add_argument("--seconds", type=float, default=90)
    args = ap.parse_args()

    from app.core.vocals import clean_melody, split_vocals

    lines = ["| Song | Engine | Instrument notes/min (full mix) | Caused by the voice /min | …of those on the vocal's pitch |",
             "|---|---|---|---|---|"]
    for song in args.songs:
        vocals, backing, share = split_vocals(song)
        mins = args.seconds / 60
        for eng in args.engines:
            fn = engine_fn(eng)
            full = instrument_notes(Path(fn(Path(song))), args.seconds)
            back = instrument_notes(Path(fn(backing)), args.seconds)
            melody = clean_melody([n for i in pretty_midi.PrettyMIDI(str(fn(vocals))).instruments
                                   if not i.is_drum for n in i.notes])
            back_idx = {}
            for n in back:
                back_idx.setdefault(n.pitch, []).append(n.start)
            extra = [n for n in full if not any(abs(s - n.start) <= 0.05 for s in back_idx.get(n.pitch, []))]
            on_voice = [n for n in extra if any(m.start - 0.05 <= n.start <= m.end and abs(m.pitch - n.pitch) <= 1
                                                for m in melody)]
            name = Path(song).stem[:40]
            lines.append(f"| {name} | {eng} | {len(full) / mins:.0f} | {len(extra) / mins:.0f} | {len(on_voice) / mins:.0f} |")
            print(lines[-1], flush=True)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
