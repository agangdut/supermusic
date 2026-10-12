"""
Which mode gets the tune right? Score every transcription mode against the
singer's own voice.

For each song the voice is separated once and its pitch traced every 20 ms
(the "sung shape"). Each mode then transcribes the song, and its melody line
is laid over that shape (see backend/app/core/melody_match.py):

  match     % of sung time where the MIDI plays the right note (higher = better)
  octave    same, but forgiving the wrong octave
  coverage  % of sung time where the MIDI plays any note
  extra     % of the MIDI melody where nobody is singing (lower = better)

    docker compose exec backend python scripts/compare_melody.py data/raw/songs
    docker compose exec backend python scripts/compare_melody.py song.mp3 --modes general,vocals_stem,multi
    docker compose exec backend python scripts/compare_melody.py data/raw/songs --modes general,muscriptor,game
    docker compose exec backend python scripts/compare_melody.py song.mp3 --midi a.mid b.mid

--midi scores MIDI files you already have (from SuperMusic or any other tool)
against the song instead of transcribing it again.

Modes: general (voice separated, then Basic Pitch), general_raw (Basic Pitch on
the full mix), vocals_stem (Stems mode with only the vocals picked), stems (all
six stems), multi (YourMT3+; needs the yourmt3 service), muscriptor (Full band,
MuScriptor's own voice track), game (Full band with GAME singing the Lead vocal), cover (Pop2Piano),
auto. Results print as a Markdown table; MIDI files are kept in
data/processed/melody_compare/.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.core.melody_match import melody_match, sung_pitch  # noqa: E402
from app.core.vocals import split_vocals  # noqa: E402

AUDIO = {".mp3", ".wav", ".flac", ".m4a", ".ogg"}


def run_mode(mode: str, audio: Path) -> Path:
    from app.core.transcription import transcribe_to_midi

    if mode == "general":
        from app.core.vocals import transcribe_vocal_aware
        return transcribe_vocal_aware(audio, transcribe_to_midi)[0]
    if mode == "general_raw":
        return Path(transcribe_to_midi(str(audio)))
    if mode in ("vocals_stem", "stems"):
        from app.core.smart_transcription import transcribe_stems
        return transcribe_stems(audio, only=["vocals"] if mode == "vocals_stem" else None)[0]
    if mode == "multi":
        from app.core.vocals import lead_vocal_track
        from app.core.yourmt3_client import transcribe_multi
        return lead_vocal_track(transcribe_multi(audio))[0]
    if mode in ("muscriptor", "game"):  # Full band: MuScriptor's own voice, or GAME on the vocal stem
        from app.core.muscriptor_client import transcribe_muscriptor
        from app.core.vocals import lead_vocal_track, sung_lead_vocal
        raw = transcribe_muscriptor(audio)
        return (sung_lead_vocal(raw, audio) if mode == "game" else lead_vocal_track(raw))[0]
    if mode == "cover":
        from app.core.piano_cover import piano_cover
        return piano_cover(audio)
    if mode == "auto":
        from app.core.smart_transcription import transcribe_auto
        return transcribe_auto(audio)[0]
    raise SystemExit(f"Unknown mode: {mode}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="Audio files or folders of them")
    ap.add_argument("--modes", default="general,vocals_stem,multi,cover")
    ap.add_argument("--limit", type=int, default=0, help="Only the first N songs")
    ap.add_argument("--midi", nargs="+", type=Path, help="Score these MIDI files instead of running modes")
    args = ap.parse_args()

    songs = []
    for item in map(Path, args.inputs):
        songs += sorted(p for p in item.rglob("*") if p.suffix.lower() in AUDIO) if item.is_dir() else [item]
    if args.limit:
        songs = songs[: args.limit]
    given = {p.stem: p for p in args.midi or []}
    modes = list(given) or [m.strip() for m in args.modes.split(",") if m.strip()]
    out_dir = settings.PROCESSED_DIR / "melody_compare"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("| song | mode | match % | octave % | coverage % | extra % | time s |")
    print("|---|---|---|---|---|---|---|")
    totals = {m: [] for m in modes}
    for song in songs:
        vocals, _, share = split_vocals(song)
        if share < 0.02:
            print(f"| {song.stem} | (instrumental, skipped) | | | | | |", flush=True)
            continue
        sung = sung_pitch(vocals)
        for mode in modes:
            t = time.time()
            try:
                if mode in given:
                    midi = given[mode]
                else:
                    midi = run_mode(mode, song)
                    shutil.copy(midi, out_dir / f"{song.stem} - {mode}.mid")
                s = melody_match(midi, vocals, sung=sung)
            except Exception as e:  # keep going: one broken mode shouldn't stop the run
                print(f"| {song.stem} | {mode} | error: {str(e).splitlines()[0][:80]} | | | | |", flush=True)
                continue
            totals[mode].append(s["melody_match"])
            print(f"| {song.stem} | {mode} | {s['melody_match']} | {s['octave_ok']} | {s['coverage']} "
                  f"| {s['extra']} | {time.time() - t:.0f} |", flush=True)

    print("\nAverage melody match per mode (higher = closer to the singer):")
    for mode, vals in sorted(totals.items(), key=lambda kv: -(sum(kv[1]) / len(kv[1]) if kv[1] else -1)):
        print(f"  {mode:12s} {sum(vals) / len(vals):5.1f}%  ({len(vals)} songs)" if vals else f"  {mode:12s}   n/a")


if __name__ == "__main__":
    main()
