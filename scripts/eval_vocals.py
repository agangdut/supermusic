"""
Do voices get mistaken for instruments, and does separating them first help?

Mixes MAESTRO piano clips (every note known) with real isolated vocals
(Demucs output from songs), then compares:

  direct        YourMT3+ on the whole mix
  vocal-aware   split vocals off first, YourMT3+ on the accompaniment,
                vocals transcribed into their own Lead vocal track

and reports:
  piano F1          how well the piano part survives the voice
  phantom notes/min notes on tracks that shouldn't exist (not piano, not
                    a voice/vocal track): the voice turned into "instruments"

    docker compose exec backend python scripts/eval_vocals.py --vocals sung.wav rap.wav
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
import mir_eval  # noqa: E402
import numpy as np  # noqa: E402
import pretty_midi  # noqa: E402
import soundfile as sf  # noqa: E402

from eval_transcription import notes_from_midi  # noqa: E402

SR = 44100
VOICE = ("sing", "voice", "vocal")


def split_tracks(midi: Path, tmp: Path):
    pm = pretty_midi.PrettyMIDI(str(midi))
    piano = [i for i in pm.instruments if "piano" in i.name.lower() and not i.is_drum]
    phantom = [i for i in pm.instruments if i not in piano and not i.is_drum
               and not any(w in i.name.lower() for w in VOICE)]
    out = pretty_midi.PrettyMIDI()
    out.instruments = piano
    path = tmp / f"{midi.stem}_piano_only.mid"
    out.write(str(path))
    return path, sum(len(i.notes) for i in phantom)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", default=str(ROOT / "data/raw/maestro/maestro-v3.0.0.zip"))
    ap.add_argument("--vocals", nargs="+", required=True)
    ap.add_argument("--labels", nargs="*", help="names for the vocal files")
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--out", default=str(ROOT / "data/processed/eval"))
    args = ap.parse_args()

    from app.core.vocals import transcribe_vocal_aware
    from app.core.yourmt3_client import transcribe_multi

    zf = zipfile.ZipFile(args.zip)
    meta = next(x for x in zf.namelist() if x.endswith("maestro-v3.0.0.csv"))
    base = meta.rsplit("/", 1)[0]
    with zf.open(meta) as f:
        rows = [r for r in csv.DictReader(line.decode() for line in f) if r["split"] == "test"]
    random.Random(2).shuffle(rows)
    rows = rows[: args.limit]
    n = int(args.seconds * SR)
    labels = args.labels or [Path(v).parent.name for v in args.vocals]

    results = []
    (ROOT / "data" / "interim").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / "data" / "interim") as tmp:
        tmp = Path(tmp)
        for vpath, vlabel in zip(args.vocals, labels):
            voice, _ = librosa.load(vpath, sr=SR, mono=True, offset=30, duration=args.seconds)
            voice = np.pad(voice, (0, max(0, n - len(voice))))
            for i, row in enumerate(rows, 1):
                ref = tmp / "ref.midi"
                ref.write_bytes(zf.read(f'{base}/{row["midi_filename"]}'))
                (tmp / "full.wav").write_bytes(zf.read(f'{base}/{row["audio_filename"]}'))
                piano, _ = librosa.load(tmp / "full.wav", sr=SR, mono=True, duration=args.seconds)
                piano = np.pad(piano, (0, max(0, n - len(piano))))
                gain = np.sqrt(np.mean(piano**2) / (np.mean(voice**2) or 1))
                mix = piano + gain * voice
                mix = mix / (np.abs(mix).max() or 1) * 0.95
                audio = tmp / f"mix_{i}.wav"
                sf.write(audio, mix, SR)
                ri, rp = notes_from_midi(ref, args.seconds)
                for method in ["direct", "vocal-aware"]:
                    midi = transcribe_multi(audio) if method == "direct" else transcribe_vocal_aware(audio, transcribe_multi)[0]
                    piano_midi, phantom = split_tracks(Path(midi), tmp)
                    ei, ep = notes_from_midi(piano_midi, args.seconds)
                    f1 = mir_eval.transcription.precision_recall_f1_overlap(ri, rp, ei, ep, offset_ratio=None)[2] if len(ei) else 0.0
                    results.append({"vocal": vlabel, "method": method, "piano_f1": f1,
                                    "phantom_per_min": phantom / (args.seconds / 60)})
                    print(f"[{vlabel} {i}/{len(rows)}] {method:11s} piano F1 {f1:.3f}  phantom/min {phantom / (args.seconds / 60):.0f}", flush=True)

    lines = [f"# Piano + vocals ({len(rows)} MAESTRO clips × {len(args.vocals)} voices, {int(args.seconds)}s, voice at 0 dB)", "",
             "| Voice | Method | Piano F1 | Phantom instrument notes / min |", "|---|---|---|---|"]
    for v in labels:
        for m in ["direct", "vocal-aware"]:
            rs = [r for r in results if r["vocal"] == v and r["method"] == m]
            lines.append(f"| {v} | {m} | {np.mean([r['piano_f1'] for r in rs]):.3f} | {np.mean([r['phantom_per_min'] for r in rs]):.0f} |")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "vocals_summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
