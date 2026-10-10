"""
Download songs from a playlist CSV as MP3s, by searching YouTube for each one.

Works with Spotify exports (Exportify: "Track Name", "Artist Name(s)") and
with SuperMusic's own CSVs (title, artist, youtube_url). When a row has a
YouTube link it is used directly; otherwise the top YouTube result for
"<artist> - <title> audio" is downloaded.

    docker compose exec backend python scripts/download_songs.py data/raw/csv/Liked_Songs.csv --limit 10

Songs land in data/raw/songs/ as "<artist> - <title>.mp3"; ones already there
are skipped, so it's safe to run again.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TITLE_COLS = ("Track Name", "track_name", "title", "Title", "name")
ARTIST_COLS = ("Artist Name(s)", "artist_name", "artist", "Artist", "artists")
URL_COLS = ("youtube_url", "YouTube URL", "url")


def _pick(row: dict, cols) -> str:
    for c in cols:
        if row.get(c, "").strip():
            return row[c].strip()
    return ""


def read_songs(csv_path: Path) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        songs = []
        for row in csv.DictReader(f):
            title = _pick(row, TITLE_COLS)
            artist = _pick(row, ARTIST_COLS).split(";")[0].strip()  # Spotify exports separate artists with ;
            url = _pick(row, URL_COLS)
            if not re.match(r"https?://(www\.)?(youtube\.com/watch\?v=[\w-]{11}|youtu\.be/[\w-]{11})", url):
                url = ""  # placeholder or missing: search instead
            if title:
                songs.append({"title": title, "artist": artist, "url": url})
        return songs


def safe_name(s: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", s).strip()[:120]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "raw" / "songs")
    ap.add_argument("--limit", type=int, default=10, help="how many songs (0 = all)")
    args = ap.parse_args()

    from yt_dlp import YoutubeDL

    songs = read_songs(args.csv)
    if args.limit:
        songs = songs[: args.limit]
    args.out.mkdir(parents=True, exist_ok=True)

    ok, failed = 0, []
    for i, s in enumerate(songs, 1):
        name = safe_name(f"{s['artist']} - {s['title']}" if s["artist"] else s["title"])
        if (args.out / f"{name}.mp3").exists():
            print(f"[{i}/{len(songs)}] already have {name}")
            ok += 1
            continue
        target = s["url"] or f"ytsearch1:{s['artist']} - {s['title']} audio"
        print(f"[{i}/{len(songs)}] {name}", flush=True)
        opts = {
            "format": "bestaudio/best",
            "outtmpl": str(args.out / f"{name}.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
        }
        try:
            with YoutubeDL(opts) as ydl:
                ydl.download([target])
            ok += 1
        except Exception as e:  # keep going; report at the end
            failed.append(f"{name}: {e}")

    print(f"\n{ok} of {len(songs)} songs in {args.out}")
    for f in failed:
        print("  failed:", f)
    sys.exit(1 if failed and not ok else 0)


if __name__ == "__main__":
    main()
