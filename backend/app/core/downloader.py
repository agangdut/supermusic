from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from app.core.config import settings


def _which(bin_name: str) -> Optional[str]:
    """Return full path to binary if on PATH, else None."""
    return shutil.which(bin_name)


def _download_with_ytdlp(url: str, out_dir: Path) -> Tuple[Path, str]:
    """
    Download audio using yt-dlp if available.
    Returns (audio_path, log).
    """
    ytdlp = _which("yt-dlp") or _which("yt_dlp")
    if not ytdlp:
        raise RuntimeError(
            "yt-dlp not found. Install it with: pip install yt-dlp "
            "or download manually and place the file in data/raw."
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        ytdlp,
        "-f", settings.YTDLP_FORMAT,
        "-x", "--audio-format", "mp3",
        "--no-playlist",
        "-o", str(out_dir / settings.YTDLP_OUTTEMPLATE),
        url,
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp failed ({proc.returncode}):\n{proc.stdout}")

    # best effort: find the newest file in out_dir after download
    produced = max(out_dir.glob("*"), key=lambda p: p.stat().st_mtime, default=None)
    if not produced or not produced.exists():
        raise RuntimeError("yt-dlp completed but no file was found in the output directory.")

    # Some runs produce .webm/.m4a -> we asked for -x mp3; handle both.
    return produced, proc.stdout


def _copy_if_local_path(source: str, out_dir: Path) -> Optional[Path]:
    """
    If `source` is a local file path, copy it to out_dir and return new path.
    Otherwise return None (meaning it's likely a URL).
    """
    p = Path(source)
    if p.exists() and p.is_file():
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / p.name
        if str(p.resolve()) != str(dest.resolve()):
            shutil.copy2(str(p), str(dest))
        return dest
    return None


def download_audio(source: str, out_dir: Path | None = None) -> Path:
    """
    Download or copy audio to RAW_DIR.
    - If `source` is a local file, it's copied into RAW_DIR.
    - If `source` looks like a URL, tries yt-dlp.

    Returns the Path to the produced audio file.
    """
    out_dir = out_dir or settings.RAW_DIR

    # Local file?
    copied = _copy_if_local_path(source, out_dir)
    if copied:
        return copied

    # Otherwise assume URL
    audio_path, _ = _download_with_ytdlp(source, out_dir)
    return audio_path
