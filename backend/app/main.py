from __future__ import annotations

import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Import your routers
from app.routes import csv as csv_routes
from app.routes import midi as midi_routes
from app.routes import stems as stems_routes
from app.routes import tracks as tracks_routes
from app.routes import upload as upload_routes
from app.routes import visualization as visualization_routes
from app.routes import auth as auth_routes
from app.routes import websocket as websocket_routes
from app.routes import batch as batch_routes
from app.routes import export as export_routes
from app.routes import map as map_routes
from app.middleware.rate_limit import limiter, RATE_LIMITS
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.middleware.error_handler import (
    validation_exception_handler,
    http_exception_handler,
    general_exception_handler
)

# ------------------------------------------------------------------------------
# FastAPI App
# ------------------------------------------------------------------------------

app = FastAPI(
    title="SuperMusic API",
    version="0.1.0",
    description="Backend API for SuperMusic – audio download, metadata enrichment, stem separation, transcription, visualization."
)

# Add rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add error handlers
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# ------------------------------------------------------------------------------
# CORS Middleware (allow frontend to call API from any origin during dev)
# ------------------------------------------------------------------------------

origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------------------
# Health Check Route
# ------------------------------------------------------------------------------

@app.get("/healthz")
def healthz():
    """
    Simple health check endpoint.
    """
    return {"ok": True, "status": "healthy"}

# ------------------------------------------------------------------------------
# Include Routers
# ------------------------------------------------------------------------------

# CSV / metadata endpoints
app.include_router(csv_routes.router)

# MIDI transcription endpoints
app.include_router(midi_routes.router)

# Stem separation endpoints
app.include_router(stems_routes.router)

# Track download endpoints
app.include_router(tracks_routes.router)

# File upload endpoints
app.include_router(upload_routes.router, tags=["upload"])

# Visualization endpoints
app.include_router(visualization_routes.router, tags=["visualization"])

# Authentication endpoints
app.include_router(auth_routes.router, tags=["auth"])

# WebSocket endpoints
app.include_router(websocket_routes.router, tags=["websocket"])

# Batch processing endpoints
app.include_router(batch_routes.router, tags=["batch"])

# Export endpoints
app.include_router(export_routes.router, tags=["export"])

# Taste map endpoints
app.include_router(map_routes.router)


@app.on_event("startup")
def _warm_map() -> None:
    import threading

    threading.Thread(target=map_routes.warm_up, daemon=True).start()

# ------------------------------------------------------------------------------
# Static file serving for artifacts
# ------------------------------------------------------------------------------

ARTIFACT_DIR = Path(os.getenv("SUPERMUSIC_ARTIFACT_DIR", Path(os.getenv("TMP", "/tmp")) / "supermusic" / "artifacts"))
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/artifacts", StaticFiles(directory=str(ARTIFACT_DIR)), name="artifacts")

# ------------------------------------------------------------------------------
# Root Route
# ------------------------------------------------------------------------------

@app.get("/")
def root():
    """
    Default root endpoint.
    """
    return {
        "message": "Welcome to the SuperMusic API",
        "docs": "/docs",
        "health": "/healthz"
    }
