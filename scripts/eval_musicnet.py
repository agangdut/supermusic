"""
Multi-instrument accuracy on MusicNet's held-out test recordings.

MusicNet (Thickstun et al.) is 330 real classical recordings (string quartets,
wind ensembles, solo piano, ...) with every note labelled. Its 10 test pieces
weren't used to train Basic Pitch or YourMT3+, so this is a fair comparison.

    docker compose exec backend python scripts/eval_musicnet.py --seconds 60

Score: note F1 across all instruments (pitch + onset within 50 ms; which
instrument played it isn't checked).
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

import mir_eval  # noqa: E402
import numpy as np  # noqa: E402
import pretty_midi  # noqa: E402

from eval_transcription import notes_from_midi  # noqa: E402

LABEL_SR = 44100  # MusicNet label times are in samples at 44.1 kHz


def extract_test_split(archive: Path, dest: Path) -> Path:
    """Pull just test_data/ and test_labels/ out of the 11 GB archive (once)."""
    done = dest / ".extracted"
    if done.exists():
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r|gz") as tf:  # streaming: one pass, no index needed
        for member in tf:
            if "/test_data/" in member.name or "/test_labels/" in member.name:
                member.name = "/".join(member.name.split("/")[-2:])
                tf.extract(member, dest)
    done.touch()
    return dest


def reference_notes(label_csv: Path, seconds: float):
    intervals, pitches = [], []
    with label_csv.open() as f:
        for row in csv.DictReader(f):
            start, end = int(row["start_time"]) / LABEL_SR, int(row["end_time"]) / LABEL_SR
            if start >= seconds:
                continue
            intervals.append([start, max(min(end, seconds), start + 0.01)])
            pitches.append(pretty_midi.note_number_to_hz(int(row["note"])))
    return np.array(intervals).reshape(-1, 2), np.array(pitches)


def pitched_notes(midi: Path, seconds: float):
    """All non-drum notes in a (possibly multi-track) MIDI."""
    pm = pretty_midi.PrettyMIDI(str(midi))
    pm.instruments = [i for i in pm.instruments if not i.is_drum]
    tmp = midi.with_name(midi.stem + "_pitched.mid")
    pm.write(str(tmp))
    return notes_from_midi(tmp, seconds)


def transcribe(method: str, audio: Path) -> Path:
    if method == "general":
        from app.core.transcription import transcribe_to_midi

        return transcribe_to_midi(audio)
    if method == "stems":
        from app.core.smart_transcription import transcribe_stems

        return transcribe_stems(audio)[0]
    if method == "multi":
        from app.core.yourmt3_client import transcribe_multi

        return transcribe_multi(audio)
    if method == "auto":
        from app.core.smart_transcription import transcribe_auto

        return transcribe_auto(audio)[0]
    if method == "piano":
        from app.core.piano_transcription import transcribe_piano

        return transcribe_piano(audio)
    raise ValueError(method)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", default=str(ROOT / "data/raw/musicnet/musicnet.tar.gz"))
    ap.add_argument("--extract-to", default=str(ROOT / "data/raw/musicnet/test"))
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--methods", nargs="+", default=["general", "stems", "multi", "auto"])
    ap.add_argument("--out", default=str(ROOT / "data/processed/eval"))
    args = ap.parse_args()

    meta = {}
    meta_csv = ROOT / "data/raw/musicnet/musicnet_metadata.csv"
    if meta_csv.exists():
        with meta_csv.open() as f:
            meta = {r["id"]: r for r in csv.DictReader(f)}

    root = extract_test_split(Path(args.archive), Path(args.extract_to))
    wavs = sorted((root / "test_data").glob("*.wav"))
    results = []
    (ROOT / "data" / "interim").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / "data" / "interim") as tmp:
        tmp = Path(tmp)
        for i, wav in enumerate(wavs, 1):
            clip = tmp / f"{wav.stem}.wav"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-t", str(args.seconds), str(clip)], check=True)
            ri, rp = reference_notes(root / "test_labels" / f"{wav.stem}.csv", args.seconds)
            info = meta.get(wav.stem, {})
            label = f'{info.get("composer", "")}: {info.get("composition", wav.stem)} ({info.get("ensemble", "?")})'
            for method in args.methods:
                t = time.time()
                try:
                    ei, ep = pitched_notes(Path(transcribe(method, clip)), args.seconds)
                    if len(ei):
                        p, r, f1, _ = mir_eval.transcription.precision_recall_f1_overlap(ri, rp, ei, ep, offset_ratio=None)
                    else:
                        p = r = f1 = 0.0
                    err = ""
                except Exception as e:
                    p = r = f1 = 0.0
                    err = str(e)[:200]
                results.append({"piece": label, "ensemble": info.get("ensemble", ""), "method": method,
                                "note_p": p, "note_r": r, "note_f1": f1, "secs": round(time.time() - t, 1), "error": err})
                print(f"[{i}/{len(wavs)}] {method:7s} F1 {f1:.3f} P {p:.3f} R {r:.3f} ({results[-1]['secs']}s) {label[:60]} {err}", flush=True)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "musicnet_results.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0]))
        w.writeheader()
        w.writerows(results)
    lines = [f"# MusicNet test set ({len(wavs)} recordings, first {int(args.seconds)}s, all instruments)", "",
             "| Method | Precision | Recall | Note F1 | Avg time |", "|---|---|---|---|---|"]
    for m in args.methods:
        rs = [r for r in results if r["method"] == m]
        lines.append(f"| {m} | {np.mean([r['note_p'] for r in rs]):.3f} | {np.mean([r['note_r'] for r in rs]):.3f} "
                     f"| {np.mean([r['note_f1'] for r in rs]):.3f} | {np.mean([r['secs'] for r in rs]):.1f}s |")
    (out / "musicnet_summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
