#!/usr/bin/env python3
"""
Audiopairs — build (MIDI, online audio/video) pairs from a Kaggle dataset
=======================================================================

Given a Kaggle dataset (e.g., lofi MIDI files), this script:
  1) Downloads & unzips the dataset via Kaggle API
  2) Finds candidate YouTube videos for each MIDI (using yt-dlp search)
  3) Downloads either audio (mp3) or full video to an output folder
  4) Writes a manifest (TSV + JSONL) mapping MIDI → media file → source URL

Requirements
------------
- kaggle (and credentials configured: %USERPROFILE%\.kaggle\kaggle.json on Windows)
- yt-dlp
- ffmpeg (in PATH) for audio extraction
- rapidfuzz (optional: better title matching)
- pandas, tqdm (optional: progress + tabular manifest)

Install:
    pip install kaggle yt-dlp rapidfuzz pandas tqdm
    # Windows FFmpeg (if needed): winget install --id Gyan.FFmpeg -e

Usage:
    python audiopairs.py \
      --kaggle zakarii/lofi-hip-hop-midi \
      --file-pattern "*.mid" \
      --out-dir D:/datasets/lofi_pairs_yt \
      --audio  \
      --yt-max 5 \
      --query-suffix "lofi hip hop"

Notes:
- Many MIDI sets have generic names (e.g., 1.mid). Provide a helpful --query-prefix/--query-suffix
  or a mapping CSV via --mapping-csv with columns [midi, query].
- Respect platform terms and copyright. Use downloaded media only if you have rights to do so.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Optional deps
try:
    from tqdm import tqdm
except Exception:  # pragma: no cover

    def tqdm(x, **kwargs):
        return x


try:
    import pandas as pd  # noqa

    HAS_PANDAS = True
except Exception:
    HAS_PANDAS = False

try:
    from rapidfuzz import fuzz, process

    HAS_RAPIDFUZZ = True
except Exception:
    HAS_RAPIDFUZZ = False

# Kaggle API
try:
    from kaggle.api.kaggle_api_extended import KaggleApi
except Exception as e:
    print(
        "[fatal] kaggle package missing. Install with: pip install kaggle",
        file=sys.stderr,
    )
    raise

# YouTube download/search
try:
    import yt_dlp
except Exception:
    print(
        "[fatal] yt-dlp package missing. Install with: pip install yt-dlp",
        file=sys.stderr,
    )
    raise


@dataclass
class PairRecord:
    midi_path: str
    media_path: str
    source_url: str
    title: str
    extractor: str
    id: str
    search_query: str


def authenticate_kaggle() -> KaggleApi:
    api = KaggleApi()
    api.authenticate()
    return api


def download_kaggle_dataset(api: KaggleApi, slug: str, dest: Path) -> Path:
    """Download & unzip the dataset into dest/<owner_dataset>/"""
    dest.mkdir(parents=True, exist_ok=True)
    print(f"[info] Downloading Kaggle dataset: {slug} → {dest}")
    api.dataset_download_files(slug, path=str(dest), unzip=True)
    # heuristically return the top-level directory (if one was created)
    root = dest
    # Some datasets unpack directly into dest; others create a subdir
    # We'll just return dest; later we glob recursively
    return root


def sanitize_query_name(p: Path) -> str:
    base = p.stem
    # include parent folder name if stem is too generic like "1"
    if re.fullmatch(r"\d+", base):
        base = f"{p.parent.name} {base}"
    base = base.replace("_", " ").replace("-", " ")
    base = re.sub(r"\s+", " ", base).strip()
    return base


def choose_best_entry(info: dict, target_name: str) -> dict:
    """Pick the most likely matching entry from a ytsearch result.
    If rapidfuzz is available, use fuzzy title scoring; else take first.
    """
    if info is None:
        return {}
    if "entries" not in info:
        return info
    entries = [e for e in info["entries"] if isinstance(e, dict)]
    if not entries:
        return {}
    if not HAS_RAPIDFUZZ:
        return entries[0]
    # fuzzy match on title
    titles = [(e.get("title") or "") for e in entries]
    best = process.extractOne(target_name, titles, scorer=fuzz.token_set_ratio)
    if best is None:
        return entries[0]
    idx = titles.index(best[0])
    return entries[idx]


def ensure_outdirs(base: Path) -> Tuple[Path, Path]:
    media_dir = base / "media"
    meta_dir = base / "meta"
    media_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    return media_dir, meta_dir


def download_media_for_query(
    query: str, out_media: Path, *, audio: bool, yt_max: int
) -> Tuple[Optional[Path], Optional[dict]]:
    """Search YouTube with yt-dlp and download either audio (mp3) or full video.
    Returns (path_to_file, info_dict) or (None, None) on failure.
    """
    search_q = f"ytsearch{max(1, yt_max)}:{query}"
    out_tmpl = str(out_media.with_suffix(".%(ext)s"))
    ydl_opts = {
        "default_search": None,  # we pass full ytsearchN:
        "quiet": True,
        "noprogress": True,
        "outtmpl": out_tmpl,
    }
    if audio:
        ydl_opts.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
            }
        )
    else:
        ydl_opts.update({"format": "bv*+ba/b"})

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(search_q, download=False)
            target_name = query
            entry = choose_best_entry(info, target_name)
            if not entry:
                return None, None
            url = entry.get("webpage_url") or entry.get("url")
            if not url:
                return None, None
            # re-extract to download this specific URL
            info2 = ydl.extract_info(url, download=True)
            # Determine produced file path
            if audio:
                # Postprocessor will create an .mp3 at out_media.with_suffix('.mp3')
                produced = out_media.with_suffix(".mp3")
                if produced.exists():
                    return produced, info2
            # Fallback: guess the filepath from info
            if "requested_downloads" in info2 and info2["requested_downloads"]:
                rp = Path(info2["requested_downloads"][0]["filepath"])
                return rp, info2
            if "filepath" in info2:
                return Path(info2["filepath"]), info2
            # As a last resort, find the newest file with our stub
            parent = out_media.parent
            candidates = sorted(
                parent.glob(out_media.stem + ".*"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if candidates:
                return candidates[0], info2
            return None, None
        except Exception as e:
            print(f"[warn] yt-dlp error for query '{query}': {e}")
            return None, None


def write_manifest(records: List[PairRecord], out_base: Path):
    out_base.mkdir(parents=True, exist_ok=True)
    # TSV
    tsv_path = out_base / "pairs.tsv"
    with open(tsv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(
            [
                "midi_path",
                "media_path",
                "source_url",
                "title",
                "extractor",
                "id",
                "search_query",
            ]
        )
        for r in records:
            w.writerow(
                [
                    r.midi_path,
                    r.media_path,
                    r.source_url,
                    r.title,
                    r.extractor,
                    r.id,
                    r.search_query,
                ]
            )
    # JSONL
    jsonl_path = out_base / "pairs.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
    print(f"[ok] Wrote manifest: {tsv_path}\n[ok] Wrote manifest: {jsonl_path}")


# ---------------------------
# MAESTRO helpers
# ---------------------------


def find_maestro_csv(root: Path) -> Optional[Path]:
    for pat in ["maestro-v*.csv", "maestro*.csv"]:
        cands = sorted(root.rglob(pat))
        if cands:
            return cands[0]
    return None


def build_pairs_from_maestro(
    maestro_dir: Path, out_base: Path, split: str = "train", copy_media: bool = False
) -> List[PairRecord]:
    csv_path = find_maestro_csv(maestro_dir)
    if csv_path is None:
        raise SystemExit(
            f"[fatal] Could not find MAESTRO metadata CSV under {maestro_dir}"
        )

    media_dir, meta_dir = ensure_outdirs(out_base)

    rows: List[Dict] = []
    if HAS_PANDAS:
        import pandas as pd  # type: ignore

        df = pd.read_csv(csv_path)
        if split != "all":
            df = df[df["split"] == split]
        rows = df.to_dict(orient="records")
    else:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                if split != "all" and r.get("split") != split:
                    continue
                rows.append(r)

    records: List[PairRecord] = []
    for r in tqdm(rows, desc=f"MAESTRO {split}"):
        audio_rel = r.get("audio_filename") or r.get("audio")
        midi_rel = r.get("midi_filename") or r.get("midi")
        if not audio_rel or not midi_rel:
            continue
        audio_path = maestro_dir / audio_rel
        midi_path = maestro_dir / midi_rel
        if not audio_path.exists() or not midi_path.exists():
            continue

        # copy or reference
        if copy_media:
            dest = media_dir / (Path(audio_rel).stem + Path(audio_rel).suffix)
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(audio_path, dest)
                media_path = dest
            except Exception:
                media_path = audio_path
        else:
            media_path = audio_path

        meta = {
            "dataset": "MAESTRO",
            "split": r.get("split"),
            "year": r.get("year"),
            "duration": r.get("duration"),
            "canonical_composer": r.get("canonical_composer"),
            "canonical_title": r.get("canonical_title"),
            "audio_filename": audio_rel,
            "midi_filename": midi_rel,
        }
        with open(
            meta_dir / (Path(media_path).stem + ".json"), "w", encoding="utf-8"
        ) as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        title = f"{meta.get('canonical_composer','')} - {meta.get('canonical_title','')}".strip()
        records.append(
            PairRecord(
                midi_path=str(midi_path),
                media_path=str(media_path),
                source_url="MAESTRO",
                title=title,
                extractor="local",
                id=Path(audio_rel).stem,
                search_query="",
            )
        )

    return records


# ---------------------------
# Main
# ---------------------------


def main():
    ap = argparse.ArgumentParser(
        description="Create (MIDI, media) pairs from a Kaggle dataset via YouTube OR from a local MAESTRO folder"
    )
    ap.add_argument(
        "--kaggle",
        required=False,
        help="Kaggle dataset slug, e.g. 'zakarii/lofi-hip-hop-midi'",
    )
    ap.add_argument(
        "--maestro-dir",
        required=False,
        help="Path to local MAESTRO root (contains maestro-v*.csv and audio/MIDI)",
    )
    ap.add_argument(
        "--maestro-split",
        default="train",
        choices=["train", "validation", "test", "all"],
        help="Which MAESTRO split to include",
    )
    ap.add_argument(
        "--maestro-copy",
        action="store_true",
        help="Copy MAESTRO audio into out-dir/media (otherwise reference in-place)",
    )
    ap.add_argument(
        "--out-dir", required=True, help="Output directory for media and manifests"
    )
    ap.add_argument(
        "--file-pattern",
        default="*.mid",
        help="Glob pattern to find MIDI files inside the dataset",
    )
    ap.add_argument(
        "--audio",
        action="store_true",
        help="Download audio (mp3) instead of full video",
    )
    ap.add_argument(
        "--video", action="store_true", help="Download full video instead of audio"
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum number of MIDI files to process (0 = all)",
    )
    ap.add_argument(
        "--yt-max",
        type=int,
        default=5,
        help="Number of YouTube search results to consider",
    )
    ap.add_argument(
        "--query-prefix", default="", help="Prefix to add to each search query"
    )
    ap.add_argument(
        "--query-suffix",
        default="lofi hip hop",
        help="Suffix to add to each search query",
    )
    ap.add_argument(
        "--mapping-csv",
        default=None,
        help="Optional CSV with columns [midi, query] to override queries",
    )
    ap.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip downloads if target media file already exists",
    )
    args = ap.parse_args()

    # MAESTRO mode: if provided, bypass Kaggle+YouTube and just build manifest from local MAESTRO
    if args.maestro_dir:
        out_base = Path(args.out_dir)
        records = build_pairs_from_maestro(
            Path(args.maestro_dir),
            out_base,
            split=args.maestro_split,
            copy_media=args.maestro_copy,
        )
        write_manifest(records, out_base)
        print(
            f"[ok] Completed from MAESTRO. Media in: {out_base / 'media'} | Metadata in: {out_base / 'meta'}"
        )
        return

    if not (args.audio ^ args.video):
        print("[fatal] Choose exactly one of --audio or --video", file=sys.stderr)
        sys.exit(2)

    out_base = Path(args.out_dir)
    media_dir, meta_dir = ensure_outdirs(out_base)

    # 1) Download the Kaggle dataset
    api = authenticate_kaggle()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        ds_root = download_kaggle_dataset(api, args.kaggle, tmp)

        # 2) Build list of MIDI files
        midi_files = sorted(ds_root.rglob(args.file_pattern))
        if args.limit > 0:
            midi_files = midi_files[: args.limit]
        if not midi_files:
            print(
                f"[fatal] No files matched pattern {args.file_pattern} under {ds_root}",
                file=sys.stderr,
            )
            sys.exit(2)

        # Optional mapping CSV (override queries)
        mapping: Dict[str, str] = {}
        if args.mapping_csv:
            mp = Path(args.mapping_csv)
            if not mp.exists():
                print(f"[warn] mapping CSV not found: {mp}")
            else:
                with open(mp, newline="", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        midi_key = Path(row["midi"]).name
                        mapping[midi_key] = row["query"]

        records: List[PairRecord] = []

        # 3) For each MIDI, search & download
        for midip in tqdm(midi_files, desc="Processing MIDIs"):
            # Build a search query
            midi_key = midip.name
            query = mapping.get(midi_key)
            if not query:
                base = sanitize_query_name(midip)
                parts = [args.query_prefix, base, args.query_suffix]
                query = " ".join([p for p in parts if p]).strip()

            # Choose output media filename stem under media_dir
            stem_safe = re.sub(r"[^\w\-]+", "_", midip.stem)[:80]
            out_stub = media_dir / stem_safe

            if args.skip_existing:
                mp3 = out_stub.with_suffix(".mp3")
                mp4 = out_stub.with_suffix(".mp4")
                if mp3.exists() or mp4.exists():
                    # Already have something, emit a record stub
                    media_path = str(mp3 if mp3.exists() else mp4)
                    records.append(
                        PairRecord(
                            midi_path=str(midip),
                            media_path=media_path,
                            source_url="",
                            title="",
                            extractor="",
                            id="",
                            search_query=query,
                        )
                    )
                    continue

            media_path, info = download_media_for_query(
                query, out_stub, audio=args.audio, yt_max=args.yt_max
            )
            if not media_path or not info:
                print(f"[warn] No media for {midip}")
                continue

            rec = PairRecord(
                midi_path=str(midip),
                media_path=str(media_path),
                source_url=info.get("webpage_url") or info.get("original_url") or "",
                title=info.get("title") or "",
                extractor=info.get("extractor") or "",
                id=info.get("id") or "",
                search_query=query,
            )
            records.append(rec)
            # Write per-item metadata JSON
            with yt_dlp.YoutubeDL({}) as ydl:
                info_clean = ydl.sanitize_info(info)
            with open(
                meta_dir / (Path(media_path).stem + ".json"), "w", encoding="utf-8"
            ) as f:
                json.dump(info_clean, f, ensure_ascii=False, indent=2)

    # 4) Save manifest
    write_manifest(records, out_base)
    print(f"[ok] Completed. Media in: {media_dir}\n     Metadata in: {meta_dir}")


if __name__ == "__main__":
    main()
