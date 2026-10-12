"""
Route handlers for the SuperMusic FastAPI app.
"""

from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates

# Resolve the templates directory relative to this file
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """
    Render the dashboard landing page.
    """
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "title": "SuperMusic Dashboard"},
    )


@router.get("/healthz", response_class=PlainTextResponse)
async def healthcheck():
    """
    Lightweight health endpoint for CI/CD or uptime checks.
    """
    return "ok"


@router.post("/upload", response_class=JSONResponse)
async def upload_audio(file: UploadFile = File(...)):
    """
    Accept a file upload and return basic info (demo stub).
    Extend this to store to disk, queue processing, etc.
    """
    # For now, don't persist—just read a small chunk to prove it works.
    chunk = await file.read(1024)
    size_hint = len(chunk)
    return JSONResponse(
        {
            "filename": file.filename,
            "content_type": file.content_type,
            "preview_bytes": size_hint,
            "message": "Upload received (demo).",
        }
    )


@router.get("/metadata/{track_id}", response_class=JSONResponse)
async def get_metadata(track_id: str):
    """
    Return mock metadata for a given track id (demo stub).
    Replace with a real lookup once your pipeline is wired.
    """
    mock: Dict[str, Any] = {
        "id": track_id,
        "title": "Demo Track",
        "artist": "Unknown Artist",
        "duration_sec": 123.4,
    }
    return JSONResponse(mock)


@router.get("/visualization", response_class=HTMLResponse)
async def visualization(request: Request):
    """
    Render a placeholder visualization page.
    (You can replace this with a Plotly embed later.)
    """
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "title": "SuperMusic Dashboard",
        },
    )
