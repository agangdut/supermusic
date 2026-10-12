from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse

from app.core.config import settings

router = APIRouter(prefix="/upload", tags=["upload"])

# Create upload directories
UPLOAD_DIR = Path(os.getenv("SUPERMUSIC_UPLOAD_DIR", settings.RAW_DIR / "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".opus"}
ALLOWED_CSV_EXTENSIONS = {".csv"}


def _save_upload(file: UploadFile, allowed_extensions: set[str], subdir: str = "") -> Path:
    """Save uploaded file and return path."""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File extension {ext} not allowed. Allowed: {', '.join(allowed_extensions)}"
        )
    
    upload_path = UPLOAD_DIR / subdir
    upload_path.mkdir(parents=True, exist_ok=True)
    
    # Keep the name readable ("Artist - Song.mp3"); only drop what a file system can't hold
    safe_name = Path(re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", Path(file.filename or "").name)).name.strip().strip(".")
    if not Path(safe_name).stem:
        safe_name = f"upload{ext}"

    file_path = upload_path / safe_name
    # Handle duplicates: name.mp3, name (2).mp3, name (3).mp3, ...
    stem = file_path.stem
    counter = 2
    while file_path.exists():
        file_path = upload_path / f"{stem} ({counter}){ext}"
        counter += 1
    
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    return file_path


@router.post("/audio")
async def upload_audio(file: UploadFile = File(...)) -> JSONResponse:
    """
    Upload an audio file.
    Returns the server-side path where the file was saved.
    """
    try:
        saved_path = _save_upload(file, ALLOWED_AUDIO_EXTENSIONS, "audio")
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


@router.post("/csv")
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

