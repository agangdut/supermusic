"""
Our MuScriptor wrapper against the official MuScriptor server, on one song of your own.

    docker compose --profile ref up -d muscriptor_ref
    docker compose exec backend python scripts/compare_muscriptor.py data/uploads/song.mp3

Writes three MIDIs to data/processed/muscriptor_compare/<song>/ (open them in any DAW
or MIDI viewer side by side):
  ours_fast.mid    our service in fast mode (the app's default)
  ours_exact.mid   our service with fast mode off (the official decoding settings)
  official.mid     the official server (official.raw.mid is exactly what it sent, with
                   its bar-alignment shift still in)

and prints the notes per instrument in each, and how closely each of ours agrees with
the official one (a note agrees if one in the other file has the same pitch and starts
within 50 ms). Identical settings should agree almost completely; anything else is a
real difference between the two.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

import pretty_midi  # noqa: E402

from eval_pop import f1, load, matches  # noqa: E402


def per_instrument(midi: Path) -> Counter:
    pm = pretty_midi.PrettyMIDI(str(midi))
    return Counter({("Drums" if i.is_drum else i.name or pretty_midi.program_to_instrument_name(i.program)): len(i.notes)
                    for i in pm.instruments})


def main() -> None:
    from app.core.muscriptor_client import transcribe_muscriptor, transcribe_muscriptor_ref

    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    args = ap.parse_args()
    audio = Path(args.audio).resolve()
    out = ROOT / "data/processed/muscriptor_compare" / audio.stem
    out.mkdir(parents=True, exist_ok=True)

    runs = {"ours_fast": lambda: transcribe_muscriptor(audio, fast=True, dynamics=False),
            "ours_exact": lambda: transcribe_muscriptor(audio, fast=False, dynamics=False),
            "official": lambda: transcribe_muscriptor_ref(audio)}
    midis = {}
    for name, run in runs.items():
        print(f"Running {name}…", flush=True)
        midi = run()
        midis[name] = out / f"{name}.mid"
        shutil.copy(midi, midis[name])
        if name == "official":
            shutil.copy(midi.with_name(f"{audio.stem}.official.mid"), out / "official.raw.mid")

    counts = {n: per_instrument(m) for n, m in midis.items()}
    names = sorted(set().union(*counts.values()), key=lambda k: -counts["official"][k])
    print(f"\nNotes per instrument ({out}):")
    print(f"  {'instrument':28s}" + "".join(f"{n:>12s}" for n in midis))
    for k in names:
        print(f"  {k[:28]:28s}" + "".join(f"{counts[n][k]:>12d}" for n in midis))

    ref_p, ref_d, _ = load(midis["official"], 0.0, float("inf"))
    print("\nAgreement with the official server (F1, 1.000 = the same notes):")
    for n in ("ours_fast", "ours_exact"):
        p, d, _ = load(midis[n], 0.0, float("inf"))
        print(f"  {n:12s} pitched {f1(matches(ref_p, p), len(ref_p), len(p))[2]:.3f}"
              f"   drums {f1(matches(ref_d, d), len(ref_d), len(d))[2]:.3f}")


if __name__ == "__main__":
    main()
