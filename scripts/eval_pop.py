"""
How accurate is each MIDI mode on real pop songs? Scored on MulTTiPop clips
built by scripts/build_pop_benchmark.py.

    docker compose exec backend python scripts/eval_pop.py --split dev
    docker compose exec backend python scripts/eval_pop.py --methods multi muscriptor --limit 20
    docker compose exec backend python scripts/eval_pop.py --limit 40 --tag experiments \
        --methods muscriptor muscriptor_fast muscriptor_beam muscriptor_stems
    docker compose exec backend python scripts/eval_pop.py --limit 40 --tag vocals \
        --methods muscriptor_vocal muscriptor_game

If a run stops part way, run the same command again: finished clips are skipped.

Scores (a note counts if it starts within 50 ms of a real one):
  pitched F1   every non-drum note, right pitch; which instrument played it isn't checked
  drums F1     drum hits, grouped into kick / snare / hi-hat / tom / cymbal
  overall F1   both together (the MulTTiPop paper's "harmonic-percussive" score)
  vocal F1     the sung melody only: the song's vocal track against our "Lead vocal" track
               (or any voice track), on clips whose reference has a vocal part
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

import mir_eval  # noqa: E402
import numpy as np  # noqa: E402
import pretty_midi  # noqa: E402

from app.core.progress import reporting  # noqa: E402
from eval_musicnet import transcribe as _transcribe  # noqa: E402

TOL = 0.05


class LiveStatus:
    """Stands in for a web job so the engines' progress messages show in the terminal,
    e.g. "MuScriptor: section 3 of 5" or "waiting for another song to finish"."""

    def __setattr__(self, key, value):
        if key == "message" and value != getattr(self, "message", None):
            print(f"\r    {str(value)[:110]:<110}", end="", flush=True)
        object.__setattr__(self, key, value)


_raw: dict = {}


def transcribe(method: str, audio: Path) -> Path:
    from app.core.muscriptor_client import transcribe_muscriptor

    if method == "muscriptor":
        return transcribe_muscriptor(audio, dynamics=False)
    if method == "muscriptor_fast":  # 4 sections at a time
        return transcribe_muscriptor(audio, fast=True, dynamics=False)
    if method == "muscriptor_beam":  # searches 3 alternatives per step
        return transcribe_muscriptor(audio, beam_size=3, dynamics=False)
    if method == "muscriptor_stems":  # Demucs first, MuScriptor per stem
        from app.core.smart_transcription import transcribe_muscriptor_stems

        return transcribe_muscriptor_stems(audio)[0]
    if method in ("muscriptor_vocal", "muscriptor_game"):  # Lead vocal from MuScriptor's voice / from GAME
        from app.core.vocals import lead_vocal_track, sung_lead_vocal

        if _raw.get("audio") != audio:  # both vocal methods start from the same MuScriptor run
            _raw.update(audio=audio, midi=transcribe_muscriptor(audio, dynamics=False))
        raw = _raw["midi"]
        return (sung_lead_vocal(raw, audio) if method == "muscriptor_game" else lead_vocal_track(raw))[0]
    return _transcribe(method, audio)


def drum_group(pitch: int) -> int:
    if pitch in (35, 36):
        return 0  # kick
    if pitch in (37, 38, 39, 40):
        return 1  # snare / clap
    if pitch in (42, 44, 46):
        return 2  # hi-hat
    if pitch in (41, 43, 45, 47, 48, 50):
        return 3  # toms
    return 4      # cymbals and the rest


VOCAL_WORDS = ("vocal", "voice", "sing", "melody", "lead", "vox")


def is_vocal(inst) -> bool:
    """Choir/voice programs (52-54) or a track named like a vocal part."""
    return not inst.is_drum and (52 <= inst.program <= 54 or any(w in inst.name.lower() for w in VOCAL_WORDS))


def load(midi: Path, shift: float, seconds: float):
    """(pitched notes, drum hits, vocal notes) as [(onset, pitch)], shifted onto the clip's clock."""
    pm = pretty_midi.PrettyMIDI(str(midi))
    pitched, drums, vocal = [], [], []
    for inst in pm.instruments:
        for n in inst.notes:
            t = n.start - shift
            if 0 <= t < seconds:
                (drums if inst.is_drum else pitched).append((t, drum_group(n.pitch) if inst.is_drum else n.pitch))
                if is_vocal(inst):
                    vocal.append((t, n.pitch))
    return pitched, drums, vocal


def matches(ref, est) -> int:
    """How many estimated notes pair up with a reference note (same pitch/group, onset within 50 ms)."""
    if not ref or not est:
        return 0
    ri = np.array([[t, t + 0.1] for t, _ in ref])
    ei = np.array([[t, t + 0.1] for t, _ in est])
    # pitch class trick: equal "pitches" in Hz only when the labels are equal
    rp = np.array([pretty_midi.note_number_to_hz(p) for _, p in ref])
    ep = np.array([pretty_midi.note_number_to_hz(p) for _, p in est])
    return len(mir_eval.transcription.match_notes(ri, rp, ei, ep, onset_tolerance=TOL, offset_ratio=None))


def f1(tp: int, n_ref: int, n_est: int):
    p = tp / n_est if n_est else 0.0
    r = tp / n_ref if n_ref else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test"], default="dev")
    ap.add_argument("--root", default=str(ROOT / "data/raw/multtipop"))
    ap.add_argument("--methods", nargs="+", default=["general", "multi", "muscriptor", "stems"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--tag", default="", help="added to the result file names, so experiments don't overwrite each other")
    ap.add_argument("--out", default=str(ROOT / "data/processed/eval"))
    args = ap.parse_args()

    index = json.loads((Path(args.root) / args.split / "index.json").read_text())
    if args.limit:
        index = index[: args.limit]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    name = f"pop_{args.split}{'_' + args.tag if args.tag else ''}"
    csv_path = out / f"{name}_results.csv"
    # Each result is saved as soon as it's scored, so a crashed or stopped run picks up where it left off.
    # Delete the CSV (or use a new --tag) to start over.
    rows = []
    if csv_path.exists():
        with csv_path.open(newline="") as f:
            rows = [{k: (v if k in ("id", "song", "method", "error") else float(v or 0)) for k, v in r.items()}
                    for r in csv.DictReader(f)]
        rows = [r for r in rows if not r["error"]]  # failed clips get another go
        if rows:
            print(f"Resuming: {len(rows)} results already in {csv_path.name}", flush=True)
    done = {(r["id"], r["method"]) for r in rows}
    fields = ["id", "song", "method", "ref_pitched", "est_pitched", "tp_pitched", "ref_drums", "est_drums", "tp_drums",
              "ref_vocal", "est_vocal", "tp_vocal", "pitched_f1", "secs", "error"]

    def save():
        tmp = csv_path.with_suffix(".tmp")
        with tmp.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", restval=0)
            w.writeheader()
            w.writerows(rows)
        tmp.replace(csv_path)

    for i, clip in enumerate(index, 1):
        ref_p, ref_d, ref_v = load(ROOT / clip["midi"], clip["midi_offset"], clip["seconds"])
        for method in args.methods:
            if (clip["id"], method) in done:
                continue
            t = time.time()
            err = ""
            try:
                with reporting(LiveStatus()):
                    midi = transcribe(method, ROOT / clip["audio"])
                est_p, est_d, est_v = load(Path(midi), 0.0, clip["seconds"])
            except Exception as e:
                est_p, est_d, est_v, err = [], [], [], str(e)[:200]
            tp_p, tp_d = matches(ref_p, est_p), matches(ref_d, est_d)
            if not ref_v:  # no vocal part in the reference: leave this clip out of the vocal score
                est_v = []
            rows.append({"id": clip["id"], "song": f'{clip["artist"]} - {clip["name"]}', "method": method,
                         "ref_pitched": len(ref_p), "est_pitched": len(est_p), "tp_pitched": tp_p,
                         "ref_drums": len(ref_d), "est_drums": len(est_d), "tp_drums": tp_d,
                         "ref_vocal": len(ref_v), "est_vocal": len(est_v), "tp_vocal": matches(ref_v, est_v),
                         "pitched_f1": round(f1(tp_p, len(ref_p), len(est_p))[2], 3),
                         "secs": round(time.time() - t, 1), "error": err})
            line = (f"[{i}/{len(index)}] {method:10s} pitched F1 {rows[-1]['pitched_f1']:.3f} "
                    f"({rows[-1]['secs']}s) {rows[-1]['song'][:50]} {err}")
            print(f"\r{line:<114}", flush=True)  # padded to cover the live status line
            save()

    ids = {c["id"] for c in index}
    rows = [r for r in rows if r["id"] in ids]  # a smaller --limit than last time scores only those clips

    # Totals over all clips (every note counts once), like the paper
    lines = [f"# MulTTiPop {args.split} ({len(index)} pop clips, {sum(c['seconds'] for c in index) / 60:.1f} min)", "",
             "| Method | Pitched P | Pitched R | Pitched F1 | Drums F1 | Overall F1 | Vocal F1 | Failed clips | Avg time |",
             "|---|---|---|---|---|---|---|---|---|"]
    for m in args.methods:
        rs = [r for r in rows if r["method"] == m]
        s = {k: sum(r[k] for r in rs) for k in ("ref_pitched", "est_pitched", "tp_pitched", "ref_drums", "est_drums", "tp_drums",
                                     "ref_vocal", "est_vocal", "tp_vocal")}
        pp, pr, pf = f1(s["tp_pitched"], s["ref_pitched"], s["est_pitched"])
        df = f1(s["tp_drums"], s["ref_drums"], s["est_drums"])[2]
        of = f1(s["tp_pitched"] + s["tp_drums"], s["ref_pitched"] + s["ref_drums"], s["est_pitched"] + s["est_drums"])[2]
        vf = f1(s["tp_vocal"], s["ref_vocal"], s["est_vocal"])[2]
        lines.append(f"| {m} | {pp:.3f} | {pr:.3f} | {pf:.3f} | {df:.3f} | {of:.3f} | {vf:.3f} | "
                     f"{sum(bool(r['error']) for r in rs)} | {np.mean([r['secs'] for r in rs]):.1f}s |")
    (out / f"{name}_summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
