#!/usr/bin/env python3
import argparse, os, sys, csv, re
from typing import List
from yt_dlp import YoutubeDL

def human_rate_to_bytes(s: str) -> int:
    """Parse '200K', '1M', '4M' → bytes/sec (int)."""
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([KMG]?)\s*", s, flags=re.I)
    if not m:
        raise ValueError(f"Bad rate limit: {s}")
    num = float(m.group(1))
    unit = (m.group(2) or "").upper()
    mult = {"":1, "K":1024, "M":1024**2, "G":1024**3}[unit]
    return int(num * mult)

def urls_from_csv(path: str, id_col: str = "Video ID") -> List[str]:
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        urls = []
        for row in r:
            vid = (row.get(id_col) or "").strip()
            if vid:
                if vid.startswith("http"):
                    urls.append(vid)
                else:
                    urls.append(f"https://www.youtube.com/watch?v={vid}")
        return urls

def progress_hook(d):
    if d.get('status') == 'downloading':
        pct = d.get('_percent_str', '').strip()
        eta = d.get('_eta_str', '').strip()
        speed = d.get('_speed_str', '').strip()
        print(f"[downloading] {pct}  ETA {eta}  {speed}", end='\r', flush=True)
    elif d.get('status') == 'finished':
        print(f"\n[post] Downloaded, converting → {d.get('filename')}")

def main():
    ap = argparse.ArgumentParser(
        description="Download YouTube to MP3 (cover art + metadata), from a URL or CSV of IDs."
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", help="YouTube URL (video or playlist)")
    src.add_argument("--csv", help="CSV with a 'Video ID' column (or use --id-col)")

    ap.add_argument("--id-col", default="Video ID", help="Column name with IDs (default: 'Video ID')")
    ap.add_argument("--outdir", default="mp3music", help="Output folder (created if missing)")
    ap.add_argument("--template", default="%(title)s.%(ext)s",
                    help="yt-dlp output template (default: '%(title)s.%(ext)s')")
    ap.add_argument("--quality", default="0",
                    help="MP3 quality (ffmpeg -q:a value 0=best VBR … 9=worst)")

    ap.add_argument("--rate-limit", help="Limit download rate, e.g. 1M, 500K")
    ap.add_argument("--ffmpeg", dest="ffmpeg_path", help="Path to ffmpeg/bin (if not on PATH)")
    ap.add_argument("--restrict-filenames", action="store_true",
                    help="Use safe filenames (no spaces/special chars)")
    ap.add_argument("--parse-artist-title", action="store_true",
                    help="Try to split 'Artist - Title' into tags via parse-metadata")
    ap.add_argument("--no-thumbnail", action="store_true",
                    help="Disable embedding the thumbnail as cover art")
    ap.add_argument("--no-metadata", action="store_true",
                    help="Disable writing ID3/metadata tags")

    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    # Build URL list
    if args.url:
        urls = [args.url]
    else:
        urls = urls_from_csv(args.csv, args.id_col)
        if not urls:
            print("No URLs/IDs found in CSV.", file=sys.stderr)
            sys.exit(1)

    # yt-dlp options
    ydl_opts = {
        "paths": {"home": args.outdir},            # send outputs to outdir
        "outtmpl": {"default": args.template},     # filename template
        "format": "bestaudio/best",
        "quiet": False,
        "noplaylist": False,                       # allow playlists if URL is one
        "ignoreerrors": True,                      # continue on errors
        "retries": 5,
        "progress_hooks": [progress_hook],
        "prefer_ffmpeg": True,
        "postprocessors": [
            {  # extract & convert to mp3
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": args.quality,  # 0=best VBR
            },
        ],
    }

    # Add metadata and thumbnail post-processors
    if not args.no_metadata:
        ydl_opts["postprocessors"].append({"key": "FFmpegMetadata"})
    if not args.no_thumbnail:
        # Need writethumbnail + embed
        ydl_opts["writethumbnail"] = True
        ydl_opts["postprocessors"].append({"key": "EmbedThumbnail"})

    if args.ffmpeg_path:
        ydl_opts["ffmpeg_location"] = args.ffmpeg_path

    if args.restrict_filenames:
        ydl_opts["restrictfilenames"] = True

    if args.rate_limit:
        ydl_opts["ratelimit"] = human_rate_to_bytes(args.rate_limit)

    # Optional: map "Artist - Title" into proper tags
    # This copies the info-dict 'title' split into artist/title when it matches.
    if args.parse_artist_title:
        # Template form works for many official uploads
        ydl_opts["parse_metadata"] = [
            "title:%(artist)s - %(title)s"
        ]
        # Also try a regex if template fails (looser)
        ydl_opts.setdefault("parse_metadata", []).append(
            r"title:(?P<artist>.+?)\s*[-–]\s*(?P<title>.+)"
        )

    print(f"[info] Downloading {len(urls)} item(s) to: {os.path.abspath(args.outdir)}")
    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download(urls)
    except Exception as e:
        print(f"\n[error] {e}", file=sys.stderr)
        sys.exit(2)

    print("\n[done] All finished.")

if __name__ == "__main__":
    main()
