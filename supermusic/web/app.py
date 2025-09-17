"""
ASGI application for SuperMusic (FastAPI).
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routes import router as web_router

# Create the FastAPI app
app = FastAPI(title="SuperMusic", version="0.1.0")

# Mount /static -> supermusic/web/static
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Include routes
app.include_router(web_router)
