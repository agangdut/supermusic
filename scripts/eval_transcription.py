"""
Measure how accurate SuperMusic's MIDI transcription is, using MAESTRO.

MAESTRO pairs real piano recordings with the exact MIDI the performer played,
so we can transcribe the audio and score the result note by note.

Run it inside the backend container (everything it needs is installed there):

    docker compose exec backend python scripts/eval_transcription.py --limit 20 --seconds 60

It reads audio straight out of data/raw/maestro/maestro-v3.0.0.zip (no need to
unzip 100 GB), and also tests each clip re-encoded as a 128 kbps MP3, since
that's what most people will upload.

Scores (mir_eval, standard for transcription research):
  note F1          a note counts if pitch matches and the onset is within 50 ms
  note+offset F1   ... and the note also ends at the right time
"""
from __future__ import annotations

import argparse
import csv
import random
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import mir_eval  # noqa: E402
import numpy as np  # noqa: E402
import pretty_midi  # noqa: E402


def notes_from_midi(path: Path, max_seconds: float):
    pm = pretty_midi.PrettyMIDI(str(path))
    notes = [n for inst in pm.instruments if not inst.is_drum for n in inst.notes if n.start < max_seconds]
    if not notes:
        return np.zeros((0, 2)), np.zeros(0)
    intervals = np.array([[n.start, min(n.end, max_seconds) if n.end > n.start else n.start + 0.01] for n in notes])
    intervals[:, 1] = np.maximum(intervals[:, 1], intervals[:, 0] + 0.01)
    pitches = np.array([pretty_midi.note_number_to_hz(n.pitch) for n in notes])
    return intervals, pitches


def score(ref_midi: Path, est_midi: Path, seconds: float) -> dict:
    ri, rp = notes_from_midi(ref_midi, seconds)
    ei, ep = notes_from_midi(est_midi, seconds)
    if len(ei) == 0:
        return {"note_p": 0, "note_r": 0, "note_f1": 0, "offset_f1": 0}
    p, r, f, _ = mir_eval.transcription.precision_recall_f1_overlap(ri, rp, ei, ep, offset_ratio=None)
    _, _, fo, _ = mir_eval.transcription.precision_recall_f1_overlap(ri, rp, ei, ep)
    return {"note_p": p, "note_r": r, "note_f1": f, "offset_f1": fo}


def clip(src: Path, dst: Path, seconds: float, mp3: bool) -> None:
    args = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-t", str(seconds), "-ac", "1"]
    args += ["-b:a", "128k", str(dst)] if mp3 else [str(dst)]
    subprocess.run(args, check=True)


def transcribe(model: str, audio: Path) -> Path:
    if model == "multi":
        from app.core.yourmt3_client import transcribe_multi

        return transcribe_multi(audio)
    if model == "piano":
        from app.core.piano_transcription import transcribe_piano

        return transcribe_piano(audio)
    from app.core.transcription import transcribe_to_midi

    return transcribe_to_midi(audio)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zip", default=str(ROOT / "data/raw/maestro/maestro-v3.0.0.zip"))
    ap.add_argument("--split", default="test", choices=["train", "validation", "test"])
    ap.add_argument("--limit", type=int, default=20, help="number of pieces")
    ap.add_argument("--seconds", type=float, default=60, help="seconds of each piece to use")
    ap.add_argument("--models", nargs="+", default=["basic", "piano"])
    ap.add_argument("--formats", nargs="+", default=["wav", "mp3"])
    ap.add_argument("--out", default=str(ROOT / "data/processed/eval"))
    args = ap.parse_args()

    zf = zipfile.ZipFile(args.zip)
    meta_name = next(n for n in zf.namelist() if n.endswith("maestro-v3.0.0.csv"))
    base = meta_name.rsplit("/", 1)[0]
    with zf.open(meta_name) as f:
        rows = [r for r in csv.DictReader(line.decode() for line in f) if r["split"] == args.split]
    random.Random(0).shuffle(rows)
    rows = rows[: args.limit]

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    # Under data/ so the YourMT3+ container (which shares that volume) can read the clips
    (ROOT / "data" / "interim").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / "data" / "interim") as tmp:
        tmp = Path(tmp)
        for i, row in enumerate(rows, 1):
            title = f'{row["canonical_composer"]}: {row["canonical_title"]}'
            wav = tmp / "full.wav"
            ref = tmp / "ref.midi"
            wav.write_bytes(zf.read(f'{base}/{row["audio_filename"]}'))
            ref.write_bytes(zf.read(f'{base}/{row["midi_filename"]}'))
            for fmt in args.formats:
                audio = tmp / f"clip.{fmt}"
                clip(wav, audio, args.seconds, mp3=(fmt == "mp3"))
                for model in args.models:
                    t = time.time()
                    try:
                        est = transcribe(model, audio)
                        s = score(ref, est, args.seconds)
                    except Exception as e:  # keep going; report the failure
                        s = {"note_p": 0, "note_r": 0, "note_f1": 0, "offset_f1": 0, "error": str(e)[:200]}
                    s.update(piece=title, model=model, format=fmt, secs=round(time.time() - t, 1))
                    results.append(s)
                    print(f"[{i}/{len(rows)}] {model:5s} {fmt}  F1 {s['note_f1']:.3f}  "
                          f"offset F1 {s['offset_f1']:.3f}  ({s['secs']}s)  {title[:50]}", flush=True)

    fields = ["piece", "model", "format", "note_p", "note_r", "note_f1", "offset_f1", "secs", "error"]
    with (out_dir / "results.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(results)

    lines = [
        f"# Transcription accuracy on MAESTRO ({args.split}, {len(rows)} pieces, first {int(args.seconds)}s)",
        "",
        "| Model | Audio | Note F1 | Precision | Recall | Note+offset F1 | Avg time |",
        "|---|---|---|---|---|---|---|",
    ]
    for model in args.models:
        for fmt in args.formats:
            rs = [r for r in results if r["model"] == model and r["format"] == fmt]
            if not rs:
                continue
            m = lambda k: np.mean([r[k] for r in rs])  # noqa: E731
            lines.append(f"| {model} | {fmt} | {m('note_f1'):.3f} | {m('note_p'):.3f} | {m('note_r'):.3f} "
                         f"| {m('offset_f1'):.3f} | {m('secs'):.1f}s |")
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
