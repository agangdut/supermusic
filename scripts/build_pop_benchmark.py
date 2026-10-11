"""
Build a pop-music test set from MulTTiPop (CMU, 2026).

MulTTiPop is 572 clips of real pop songs (374 songs, 3.5 hours) with every
instrument's notes, checked by people. It ships only the notes and the YouTube
video + start/end time of each clip, so this script fetches the notes from
Hugging Face and cuts the matching audio out of each YouTube video.

The authors ask that it's used for testing only, never for training, and that
only the clip itself is kept. The full video is deleted after cutting.

Run it inside the backend container (it needs YouTube access, which the
backend has):

    docker compose exec backend python scripts/build_pop_benchmark.py --split dev

Result: data/raw/multtipop/<split>/<id>/{aligned.mid, meta.json, audio.wav}
and data/raw/multtipop/<split>/index.json listing the clips that worked.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "gclef-cmu/multtipop"


def fetch_labels(dest: Path, split: str) -> Path:
    from huggingface_hub import snapshot_download

    snapshot_download(REPO, repo_type="dataset", local_dir=str(dest), allow_patterns=[f"{split}/*/*", "README.md"])
    return dest / split


def clip_audio(ytid: str, start: float, end: float, out: Path) -> None:
    """Download the video's audio once, cut [start, end] to a WAV, delete the rest."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["yt-dlp", "-q", "--no-playlist", "-f", "bestaudio/best", "-o", f"{tmp}/full.%(ext)s",
                        f"https://www.youtube.com/watch?v={ytid}"], check=True, capture_output=True, text=True)
        full = next(Path(tmp).glob("full.*"))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
                        "-i", str(full), "-ac", "1", "-ar", "44100", str(out)], check=True)


def midi_starts_at_clip(midi: Path, start: float, end: float) -> bool:
    """True if the MIDI's time 0 is the clip start; False if it uses the video's own clock."""
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(str(midi))
    last = max((n.end for i in pm.instruments for n in i.notes), default=0.0)
    return last <= (end - start) + 5.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test"], default="dev",
                    help="dev = 169 clips (61 min), test = 403 clips (152 min)")
    ap.add_argument("--limit", type=int, default=0, help="only the first N clips (0 = all)")
    ap.add_argument("--dest", default=str(ROOT / "data/raw/multtipop"))
    args = ap.parse_args()

    if not shutil.which("yt-dlp"):
        sys.exit("yt-dlp isn't installed here. Run this inside the backend container.")

    root = fetch_labels(Path(args.dest), args.split)
    clips = sorted(p for p in root.iterdir() if (p / "meta.json").exists())
    if args.limit:
        clips = clips[: args.limit]

    index, failed = [], []
    for i, clip in enumerate(clips, 1):
        meta = json.loads((clip / "meta.json").read_text())
        yt = meta["youtube"]
        ytid = yt.get("ytid") or yt.get("id")
        start, end = float(yt["start"]), float(yt["end"])
        wav = clip / "audio.wav"
        try:
            if not wav.exists():
                clip_audio(ytid, start, end, wav)
            entry = {
                "id": clip.name, "artist": meta.get("artist"), "name": meta.get("name"),
                "section": meta.get("section"), "audio": str(wav.relative_to(ROOT)),
                "midi": str((clip / "aligned.mid").relative_to(ROOT)),
                "start": start,
                # only clips that start well into the video can tell the two clocks apart
                "clip_clock": midi_starts_at_clip(clip / "aligned.mid", start, end) if start > 10 else None,
                "seconds": round(end - start, 2),
            }
            index.append(entry)
            print(f"[{i}/{len(clips)}] ok   {entry['artist']} - {entry['name']} ({entry['section']})", flush=True)
        except Exception as e:  # a removed or region-blocked video
            err = getattr(e, "stderr", "") or str(e)
            failed.append({"id": clip.name, "ytid": ytid, "error": str(err).strip()[-200:]})
            print(f"[{i}/{len(clips)}] FAIL {meta.get('artist')} - {meta.get('name')}: {failed[-1]['error']}", flush=True)

    # The dataset uses one clock throughout; take the majority and apply it to every clip
    votes = [e.pop("clip_clock") for e in index]
    clip_clock = sum(v is True for v in votes) >= sum(v is False for v in votes)
    for e in index:
        # seconds to subtract from MIDI times to line them up with audio.wav
        e["midi_offset"] = 0.0 if clip_clock else e["start"]
    (root / "index.json").write_text(json.dumps(index, indent=1))
    (root / "failed.json").write_text(json.dumps(failed, indent=1))
    print(f"\n{len(index)} clips ready, {len(failed)} unavailable. "
          f"MIDI time 0 = {'clip start' if clip_clock else 'video time'} "
          f"({sum(v is True for v in votes)} vs {sum(v is False for v in votes)} clips).")


if __name__ == "__main__":
    main()
