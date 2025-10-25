from __future__ import annotations

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import your routers (add more as you create them)
from app.routes import csv as csv_routes
# from app.routes import audio as audio_routes
# from app.routes import midi as midi_routes

# ------------------------------------------------------------------------------
# FastAPI App
# ------------------------------------------------------------------------------

app = FastAPI(
    title="SuperMusic API",
    version="0.1.0",
    description="Backend API for SuperMusic – audio download, metadata enrichment, stem separation, transcription, visualization."
)

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
app.include_router(csv_routes.router, prefix="/csv", tags=["csv"])

# If/when you add audio & midi routers:
# app.include_router(audio_routes.router, prefix="/audio", tags=["audio"])
# app.include_router(midi_routes.router,  prefix="/midi",  tags=["midi"])

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
