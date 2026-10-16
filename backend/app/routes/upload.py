from __future__ import annotations

import os
import re
import secrets
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, UploadFile, HTTPException, Depends
from app.core import jobs
from fastapi.responses import JSONResponse

from app.core.config import settings

router = APIRouter(prefix="/upload", tags=["upload"])

# Create upload directories
UPLOAD_DIR = Path(os.getenv("SUPERMUSIC_UPLOAD_DIR", settings.RAW_DIR / "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".opus"}
ALLOWED_CSV_EXTENSIONS = {".csv"}

MAX_UPLOAD_MB = int(os.getenv("SM_MAX_UPLOAD_MB", "100") or 100)
MAX_SONG_MINUTES = float(os.getenv("SM_MAX_SONG_MINUTES", "15") or 15)


def _save_upload(file: UploadFile, allowed_extensions: set[str], subdir: str = "") -> Path:
    """Save uploaded file and return path."""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File extension {ext} not allowed. Allowed: {', '.join(allowed_extensions)}"
        )
    
    # A random folder per upload: the file keeps its readable name ("Artist - Song.mp3"),
    # but nobody can guess where it is from the song's name
    upload_path = UPLOAD_DIR / subdir / secrets.token_urlsafe(12)
    upload_path.mkdir(parents=True, exist_ok=True)

    # Keep the name readable; only drop what a file system can't hold
    safe_name = Path(re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", Path(file.filename or "").name)).name.strip().strip(".")
    if not Path(safe_name).stem:
        safe_name = f"upload{ext}"
    file_path = upload_path / safe_name

    limit = MAX_UPLOAD_MB * 1024 * 1024
    written = 0
    with open(file_path, "wb") as f:
        while chunk := file.file.read(1024 * 1024):
            written += len(chunk)
            if written > limit:
                f.close()
                file_path.unlink(missing_ok=True)
                upload_path.rmdir()
                raise HTTPException(status_code=413, detail=f"That file is over {MAX_UPLOAD_MB} MB.")
            f.write(chunk)

    return file_path


def _check_length(path: Path) -> None:
    """Long recordings (a two-hour mix) would hold a worker for hours: turn them away."""
    try:
        import soundfile

        minutes = soundfile.info(str(path)).duration / 60
    except Exception:
        try:
            import librosa

            minutes = float(librosa.get_duration(path=str(path))) / 60
        except Exception:
            return  # can't tell; the job itself will say if the file is unreadable
    if minutes > MAX_SONG_MINUTES:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=413, detail=f"Songs can be up to {MAX_SONG_MINUTES:g} minutes long.")


@router.post("/audio", dependencies=[Depends(jobs.rate_limit("upload", 60))])
async def upload_audio(file: UploadFile = File(...)) -> JSONResponse:
    """
    Upload an audio file.
    Returns the server-side path where the file was saved.
    """
    try:
        saved_path = _save_upload(file, ALLOWED_AUDIO_EXTENSIONS, "audio")
        _check_length(saved_path)
        return JSONResponse({
            "success": True,
            "path": str(saved_path),
            "filename": saved_path.name,
            "size": saved_path.stat().st_size,
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.post("/csv", dependencies=[Depends(jobs.rate_limit("upload", 60))])
async def upload_csv(file: UploadFile = File(...)) -> JSONResponse:
    """
    Upload a CSV file.
    Returns the server-side path where the file was saved.
    """
    try:
        saved_path = _save_upload(file, ALLOWED_CSV_EXTENSIONS, "csv")
        return JSONResponse({
            "success": True,
            "path": str(saved_path),
            "filename": saved_path.name,
            "size": saved_path.stat().st_size,
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

