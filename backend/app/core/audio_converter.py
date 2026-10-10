from __future__ import annotations

from pathlib import Path
from typing import Optional
import subprocess
import shutil

from app.core.config import settings


def convert_audio_format(
    input_path: str | Path,
    output_path: str | Path | None = None,
    output_format: str = "mp3",
    bitrate: str = "192k"
) -> Path:
    """
    Convert audio file to different format using ffmpeg.
    
    Args:
        input_path: Path to input audio file
        output_path: Path to save converted file (default: same name, new extension)
        output_format: Target format (mp3, wav, flac, m4a, ogg)
        bitrate: Audio bitrate (e.g., "192k", "320k")
    
    Returns:
        Path to converted audio file
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found. Install ffmpeg to enable audio conversion.")
    
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    
    if output_path is None:
        output_path = input_path.parent / f"{input_path.stem}.{output_format}"
    else:
        output_path = Path(output_path)
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Build ffmpeg command
    cmd = [
        ffmpeg,
        "-i", str(input_path),
        "-b:a", bitrate,
        "-y",  # Overwrite output file
        str(output_path)
    ]
    
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg conversion failed: {proc.stdout}")
    
    if not output_path.exists():
        raise RuntimeError("Conversion completed but output file not found")
    
    return output_path

