"""
Web package for SuperMusic.

Exposes the FastAPI `app` for ASGI servers and test clients.
"""

from .app import app  # re-export for `uvicorn supermusic.web.app:app`

__all__ = ["app"]
