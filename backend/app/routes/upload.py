from __future__ import annotations

import os
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
    
    # Generate safe filename
    safe_name = "".join(c for c in (file.filename or "file") if c.isalnum() or c in "._-")
    if not safe_name:
        safe_name = f"upload{ext}"
    
    file_path = upload_path / safe_name
    # Handle duplicates
    counter = 1
    while file_path.exists():
        stem = file_path.stem
        file_path = upload_path / f"{stem}_{counter}{ext}"
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

