"""
Compare Pop2Piano covers with transcribe-then-make-playable on real songs.

For each audio file, makes a two-hand piano part both ways and reports:
  raw playable     how much of the model's own output two hands can play
  notes/s          how busy the part is
  changed          notes the two-hand rewrite had to fold, drop or cut short
  fast leaps/min   one hand jumping more than an octave in under 0.15 s,
                   per minute (the rewrite doesn't control this; lower is easier)

    docker compose exec backend python scripts/compare_piano_cover.py data/raw/songs/*.mp3

Results go to stdout as a Markdown table, and the MIDI files are kept in
data/processed/cover_compare/ so you can listen to them.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import pretty_midi  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.piano_cover import piano_cover  # noqa: E402
from app.core.playability import _chords, _load_notes, make_playable  # noqa: E402


def fast_leaps_per_min(midi_path: Path, max_gap: float = 0.15, min_leap: int = 13) -> float:
    pm = pretty_midi.PrettyMIDI(str(midi_path))
    leaps = 0
    for inst in pm.instruments:
        hand = pretty_midi.PrettyMIDI()
        hand.instruments.append(inst)
        chords = _chords(_load_notes(hand))
        for a, b in zip(chords, chords[1:]):
            gap = b[0].start - a[-1].start
            ca = sum(n.pitch for n in a) / len(a)
            cb = sum(n.pitch for n in b) / len(b)
            if gap < max_gap and abs(cb - ca) >= min_leap:
                leaps += 1
    minutes = max(pm.get_end_time(), 1.0) / 60
    return leaps / minutes


def run_rules(audio: Path, model: str) -> Path:
    if model == "auto":
        from app.core.smart_transcription import transcribe_auto
        return transcribe_auto(audio)[0]
    if model == "stems":
        from app.core.smart_transcription import transcribe_stems
        return transcribe_stems(audio)[0]
    if model == "piano":
        from app.core.piano_transcription import transcribe_piano
        return transcribe_piano(audio)
    from app.core.transcription import transcribe_to_midi
    return transcribe_to_midi(audio)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio", nargs="+", type=Path)
    ap.add_argument("--rules-model", default="auto", choices=["auto", "stems", "piano", "basic"])
    ap.add_argument("--composer", default="composer1")
    ap.add_argument("--hand-span", type=int, default=14)
    args = ap.parse_args()

    out_dir = settings.PROCESSED_DIR / "cover_compare"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"| Song | Method | Raw playable | Notes/s | Changed by rewrite | Fast leaps/min | Time |")
    print("|---|---|---|---|---|---|---|")
    for audio in args.audio:
        for method in ("cover", args.rules_model):
            t = time.time()
            raw = piano_cover(audio, composer=args.composer) if method == "cover" else run_rules(audio, method)
            secs = time.time() - t
            label = "Pop2Piano" if method == "cover" else f"{method} + rewrite"
            final, s = make_playable(raw, out_dir / f"{audio.stem}_{method}_playable.mid", hand_span=args.hand_span)
            changed = s["notes_folded"] + s["notes_dropped"] + s["notes_released_early"]
            length = max(pretty_midi.PrettyMIDI(str(final)).get_end_time(), 1.0)
            print(f"| {audio.stem} | {label} | {s['playable_before_pct']:.1f}% | {s['notes_after'] / length:.1f} "
                  f"| {100 * changed / max(1, s['notes_before']):.1f}% | {fast_leaps_per_min(final):.1f} | {secs:.0f}s |",
                  flush=True)


if __name__ == "__main__":
    main()
