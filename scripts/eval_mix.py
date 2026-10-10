"""
How well do we recover a piano part from a full band mix?

Takes MAESTRO piano clips (where we know every note), mixes a band backing
track under them (drums, bass, guitar, from any stems you pass in), and
compares four ways of getting the piano notes back:

  general  Basic Pitch on the whole mix
  piano    the MAESTRO piano model on the whole mix
  stems    6-stem split, then the Piano track only
  auto     whatever Auto mode picks (its Piano track if it picks stems)

    docker compose exec backend python scripts/eval_mix.py \
        --backing /app/data/interim/.../drums.wav /app/data/interim/.../bass.wav

Only piano notes are in the reference, so for "general" and "piano" (which
also transcribe the band) precision is pessimistic; recall is the fair
number to compare there.
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

import librosa  # noqa: E402
import numpy as np  # noqa: E402
import pretty_midi  # noqa: E402
import soundfile as sf  # noqa: E402

from eval_transcription import score  # noqa: E402

SR = 44100


def piano_only(midi_path: Path, out: Path) -> Path:
    pm = pretty_midi.PrettyMIDI(str(midi_path))
    keep = [i for i in pm.instruments if i.name.lower() == "piano"]
    pm.instruments = keep
    pm.write(str(out))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", default=str(ROOT / "data/raw/maestro/maestro-v3.0.0.zip"))
    ap.add_argument("--backing", nargs="+", required=True, help="WAV stems to sum into a backing track")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--backing-db", type=float, default=0.0, help="backing loudness relative to the piano")
    ap.add_argument("--out", default=str(ROOT / "data/processed/eval"))
    args = ap.parse_args()

    from app.core.piano_transcription import transcribe_piano
    from app.core.smart_transcription import choose_model, stem_shares, transcribe_stems
    from app.core.transcription import transcribe_to_midi

    n = int(args.seconds * SR)
    backing = sum(librosa.load(p, sr=SR, mono=True)[0] for p in args.backing)
    backing = np.tile(backing, int(np.ceil(n / len(backing))))[:n]

    zf = zipfile.ZipFile(args.zip)
    meta = next(x for x in zf.namelist() if x.endswith("maestro-v3.0.0.csv"))
    base = meta.rsplit("/", 1)[0]
    with zf.open(meta) as f:
        rows = [r for r in csv.DictReader(line.decode() for line in f) if r["split"] == "test"]
    random.Random(1).shuffle(rows)
    rows = rows[: args.limit]

    results = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for i, row in enumerate(rows, 1):
            ref = tmp / "ref.midi"
            ref.write_bytes(zf.read(f'{base}/{row["midi_filename"]}'))
            (tmp / "full.wav").write_bytes(zf.read(f'{base}/{row["audio_filename"]}'))
            piano, _ = librosa.load(tmp / "full.wav", sr=SR, mono=True, duration=args.seconds)
            piano = np.pad(piano, (0, max(0, n - len(piano))))
            gain = np.sqrt(np.mean(piano**2) / (np.mean(backing**2) or 1)) * 10 ** (args.backing_db / 20)
            mix = piano + gain * backing
            mix = mix / (np.abs(mix).max() or 1) * 0.95
            audio = tmp / f"mix{i}.wav"
            sf.write(audio, mix, SR)

            stems_midi, info = transcribe_stems(audio)
            auto_choice, _ = choose_model(info["stem_shares"])
            outputs = {
                "general": transcribe_to_midi(audio),
                "piano": transcribe_piano(audio),
                "stems": piano_only(stems_midi, tmp / "stems_piano.mid"),
            }
            outputs["auto"] = outputs["stems"] if auto_choice == "stems" else outputs["piano" if auto_choice == "piano" else "general"]
            for method, midi in outputs.items():
                s = score(ref, midi, args.seconds)
                s.update(piece=row["canonical_title"], method=method, auto_choice=auto_choice)
                results.append(s)
                print(f"[{i}/{len(rows)}] {method:7s} P {s['note_p']:.3f} R {s['note_r']:.3f} F1 {s['note_f1']:.3f}"
                      f"  (auto picked {auto_choice}; piano share {info['stem_shares'].get('piano', 0):.2f})", flush=True)

    lines = [
        f"# Piano notes recovered from a band mix ({len(rows)} MAESTRO test clips, {int(args.seconds)}s, "
        f"backing at {args.backing_db:+.0f} dB)",
        "",
        "| Method | Precision | Recall | Note F1 |",
        "|---|---|---|---|",
    ]
    for m in ["general", "piano", "stems", "auto"]:
        rs = [r for r in results if r["method"] == m]
        lines.append(f"| {m} | {np.mean([r['note_p'] for r in rs]):.3f} | {np.mean([r['note_r'] for r in rs]):.3f} "
                     f"| {np.mean([r['note_f1'] for r in rs]):.3f} |")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "mix_summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
