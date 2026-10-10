"""
Build a piano-cover training set: pop songs paired with the piano part a
human played for them, as aligned MIDI.

Pop2Piano's authors published the YouTube IDs of 5,989 (piano cover, original
song) pairs but not the data. This rebuilds it the way they did:

  1. download both videos as audio (yt-dlp),
  2. transcribe the piano cover to MIDI with our Piano model (MAESTRO-trained),
  3. find the key difference and transpose the MIDI to the song's key,
  4. line the cover up with the song in time (chroma DTW) and warp the MIDI,
  5. score how well they match, so bad pairs can be filtered out.

Each pair lands in data/datasets/covers/<song id>__<cover id>/ with
song.mp3, cover.mp3, cover.mid (raw transcription), aligned.mid (on the
song's timeline, in its key) and meta.json. A manifest.csv sums it all up.
Finished pairs are skipped (failed ones are retried), so you can stop it and
run it again to grow the set.

    docker compose exec backend python scripts/build_cover_dataset.py --limit 20

Your own pairs work too: a CSV with columns piano_ids,pop_ids (YouTube IDs
or full URLs), passed with --pairs.

Alignment is approximate: on a test with a known answer, half the notes
landed within about 0.15 s of the right time (the Pop2Piano authors'
synctoolbox method did no better and was 5x slower). Pairs whose harmony
doesn't follow the song get "poor match" and should be left out of training.

Budget: about 8 MB of audio per pair (~50 GB for all 5,989) and, on CPU,
around a minute per pair, mostly the piano transcription. A GPU is much faster.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import shutil
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import numpy as np  # noqa: E402

PAIRS_URL = "https://raw.githubusercontent.com/sweetcocoa/pop2piano/main/train_dataset.csv"
SR = 22050
MAX_SECONDS = 600
MIN_MATCH = 0.45              # chroma similarity below this: probably not the same song


def youtube_id(s: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|^)([\w-]{11})(?:\b|$)", s.strip())
    if not m:
        raise ValueError(f"not a YouTube ID or URL: {s!r}")
    return m.group(1)


def read_pairs(source: str) -> list[tuple[str, str]]:
    if re.match(r"https?://", source):
        text = urllib.request.urlopen(source, timeout=60).read().decode("utf-8")
    else:
        text = Path(source).read_text(encoding="utf-8-sig")
    rows = csv.DictReader(io.StringIO(text))
    return [(youtube_id(r["piano_ids"]), youtube_id(r["pop_ids"])) for r in rows]


def download(video_id: str, out: Path) -> Path:
    from yt_dlp import YoutubeDL

    if out.exists():
        return out
    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(out.with_suffix(".%(ext)s")),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "match_filter": lambda info, *_: "too long" if (info.get("duration") or 0) > MAX_SECONDS else None,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "160"}],
    }
    with YoutubeDL(opts) as ydl:
        ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    if not out.exists():
        raise RuntimeError("unavailable or longer than 10 minutes")
    return out


HOP = 1024  # ~46 ms per alignment frame


def _chroma(y):
    import librosa

    c = librosa.feature.chroma_cqt(y=y, sr=SR, hop_length=HOP)
    return c / (np.linalg.norm(c, axis=0, keepdims=True) + 1e-9)


def key_shift(song_c, cover_c) -> int:
    """Semitones to move the cover by so its overall harmony matches the song (-6..+5)."""
    s, c = song_c.mean(axis=1), cover_c.mean(axis=1)
    scores = {k: float(np.dot(s, np.roll(c, k))) for k in range(-6, 6)}
    return max(scores, key=scores.get)


def align(song: Path, cover: Path, midi_in: Path, midi_out: Path) -> dict:
    """Transpose and time-warp the cover's MIDI onto the song. Returns alignment stats."""
    import librosa
    import pretty_midi

    y_song, _ = librosa.load(str(song), sr=SR, mono=True)
    y_cover, _ = librosa.load(str(cover), sr=SR, mono=True)
    song_c, cover_c = _chroma(y_song), _chroma(y_cover)
    shift = key_shift(song_c, cover_c)
    cover_c = np.roll(cover_c, shift, axis=0)

    # Steps of (1,1), (1,2), (2,1): tempo may drift between half and double speed,
    # but the path can't stall, which would pile many notes onto one instant
    _, path = librosa.sequence.dtw(
        X=cover_c, Y=song_c, metric="cosine",
        step_sizes_sigma=np.array([[1, 1], [1, 2], [2, 1]]),
        weights_add=np.zeros(3), weights_mul=np.array([1.0, 1.5, 1.5]),
    )
    path = path[::-1]
    frame_t = HOP / SR
    # cover time -> song time, smoothed over ~1 s so the warp follows tempo, not frame jitter
    cov_t, song_t = path[:, 0] * frame_t, path[:, 1] * frame_t
    k = max(1, int(1.0 / frame_t))
    song_s = np.convolve(np.pad(song_t, k, mode="edge"), np.ones(2 * k + 1) / (2 * k + 1), mode="valid")
    cov_u, idx = np.unique(cov_t, return_index=True)
    song_u = np.maximum.accumulate(song_s[idx])
    warp = lambda t: float(np.interp(t, cov_u, song_u))  # noqa: E731

    pm = pretty_midi.PrettyMIDI(str(midi_in))
    for inst in pm.instruments:
        for n in inst.notes:
            n.start, n.end = warp(n.start), warp(n.end)
            n.pitch = int(np.clip(n.pitch + shift, 21, 108))
        inst.notes = [n for n in inst.notes if n.end - n.start > 0.02]
        for cc in inst.control_changes:
            cc.time = warp(cc.time)
    pm.write(str(midi_out))

    # How well the warped piano part follows the song's harmony
    roll = pretty_midi.PrettyMIDI(str(midi_out)).get_chroma(fs=1 / frame_t)
    n = min(roll.shape[1], song_c.shape[1])
    roll, sc = roll[:, :n], song_c[:, :n]
    active = roll.sum(axis=0) > 0
    roll = roll[:, active] / (np.linalg.norm(roll[:, active], axis=0) + 1e-9)
    match = float((roll * sc[:, active]).sum(axis=0).mean()) if active.any() else 0.0
    return {
        "key_shift": shift,
        "match": round(match, 3),
        "song_seconds": round(len(y_song) / SR, 1),
        "cover_seconds": round(len(y_cover) / SR, 1),
    }


def build_pair(piano_id: str, pop_id: str, out_root: Path) -> dict:
    from app.core.piano_transcription import transcribe_piano
    from app.core.playability import playability_report

    d = out_root / f"{pop_id}__{piano_id}"
    meta_path = d / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        if not meta["status"].startswith("failed"):  # failures (often a network hiccup) are retried
            return meta
    d.mkdir(parents=True, exist_ok=True)
    meta = {"pop_id": pop_id, "piano_id": piano_id}
    t = time.time()
    try:
        song = download(pop_id, d / "song.mp3")
        cover = download(piano_id, d / "cover.mp3")
        midi = transcribe_piano(cover, out_dir=d / "tmp")
        (d / "cover.mid").write_bytes(midi.read_bytes())
        shutil.rmtree(d / "tmp", ignore_errors=True)
        meta.update(align(song, cover, d / "cover.mid", d / "aligned.mid"))
        meta["playable_pct"] = playability_report(d / "aligned.mid")["playable_pct"]
        meta["status"] = "ok" if meta["match"] >= MIN_MATCH else "poor match"
    except Exception as e:  # keep going; the reason is recorded
        meta["status"] = f"failed: {str(e).splitlines()[0][:200]}"
    meta["seconds"] = round(time.time() - t, 1)
    meta_path.write_text(json.dumps(meta, indent=2))
    return meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pairs", default=PAIRS_URL, help="CSV (path or URL) with piano_ids,pop_ids")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "datasets" / "covers")
    ap.add_argument("--limit", type=int, default=20, help="pairs to process this run (0 = all)")
    ap.add_argument("--start", type=int, default=0, help="skip this many pairs first")
    args = ap.parse_args()

    pairs = read_pairs(args.pairs)[args.start:]
    if args.limit:
        pairs = pairs[: args.limit]
    args.out.mkdir(parents=True, exist_ok=True)
    print(f"{len(pairs)} pairs -> {args.out}")

    rows = []
    for i, (piano_id, pop_id) in enumerate(pairs, 1):
        m = build_pair(piano_id, pop_id, args.out)
        rows.append(m)
        print(f"[{i}/{len(pairs)}] {pop_id} + {piano_id}: {m['status']}"
              + (f" (match {m['match']}, key {m['key_shift']:+d}, playable {m['playable_pct']}%)" if "match" in m else ""),
              flush=True)

    # Manifest over everything built so far, not just this run
    all_meta = [json.loads(p.read_text()) for p in sorted(args.out.glob("*/meta.json"))]
    cols = ["pop_id", "piano_id", "status", "match", "key_shift", "playable_pct", "song_seconds", "cover_seconds", "seconds"]
    with open(args.out / "manifest.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_meta)
    ok = sum(m["status"] == "ok" for m in all_meta)
    print(f"\n{ok} usable pairs of {len(all_meta)} tried so far. Manifest: {args.out / 'manifest.csv'}")


if __name__ == "__main__":
    main()
