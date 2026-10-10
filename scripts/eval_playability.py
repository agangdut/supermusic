"""
Check the playability score against real pianists, using MAESTRO.

MAESTRO's MIDI is exactly what concert pianists played with their two hands,
so a fair playability score should rate it close to 100%. This scores a
random sample of pieces at each hand size, and also runs the two-hand rewrite
on them to show it leaves already-playable music alone.

Only the small MIDI-only zip (58 MB) is needed:

    curl -o data/raw/maestro/maestro-v3.0.0-midi.zip https://storage.googleapis.com/magentadata/datasets/maestro/v3.0.0/maestro-v3.0.0-midi.zip
    docker compose exec backend python scripts/eval_playability.py data/raw/maestro/maestro-v3.0.0-midi.zip --limit 40

The full dataset zip (data/raw/maestro/maestro-v3.0.0.zip) works too.
"""
from __future__ import annotations

import argparse
import random
import statistics
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.playability import HAND_SPANS, make_playable, playability_report  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("maestro_zip", type=Path)
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    with zipfile.ZipFile(args.maestro_zip) as z, tempfile.TemporaryDirectory() as tmp:
        names = sorted(n for n in z.namelist() if n.endswith((".midi", ".mid")))
        random.Random(args.seed).shuffle(names)
        files = []
        for name in names[: args.limit]:
            path = Path(tmp) / Path(name).name
            path.write_bytes(z.read(name))
            files.append(path)

        print(f"{len(files)} MAESTRO performances\n")
        print("| Hand size | Span | Mean playable | Worst piece | Most keys down at once |")
        print("|---|---|---|---|---|")
        for size, span in HAND_SPANS.items():
            reports = [playability_report(f, span) for f in files]
            pct = [r["playable_pct"] for r in reports]
            print(f"| {size} | {span} | {statistics.mean(pct):.2f}% | {min(pct):.1f}% "
                  f"| {max(r['max_keys_down'] for r in reports)} |")

        kept = []
        for f in files:
            _, stats = make_playable(f, Path(tmp) / f"{f.stem}_playable.mid")
            kept.append(stats["notes_after"] / max(1, stats["notes_before"]))
        print(f"\nTwo-hand rewrite kept {100 * statistics.mean(kept):.2f}% of notes on average.")


if __name__ == "__main__":
    main()
