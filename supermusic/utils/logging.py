"""
Logging helpers for SuperMusic.
"""

from __future__ import annotations
import logging
import os
from typing import Optional

# Rely on central config if available; fall back gracefully.
try:
    from supermusic.core import config as _cfg  # type: ignore
    DEFAULT_LEVEL = getattr(_cfg, "LOG_LEVEL", "INFO")
except Exception:
    DEFAULT_LEVEL = os.environ.get("SUPERMUSIC_LOG_LEVEL", "INFO")


_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: Optional[str] = None, propagate_uvicorn: bool = False) -> None:
    """
    Initialize root logging configuration once.

    Parameters
    ----------
    level : str | None
        Log level name, e.g., "DEBUG", "INFO". Defaults to config/env.
    propagate_uvicorn : bool
        If True, uvicorn/access loggers propagate to root (useful when running FastAPI).
    """
    lvl = (level or DEFAULT_LEVEL).upper()
    if not logging.getLogger().handlers:
        logging.basicConfig(level=lvl, format=_FORMAT, datefmt=_DATEFMT)
    else:
        logging.getLogger().setLevel(lvl)

    # Tidy uvicorn loggers unless propagation requested
    if not propagate_uvicorn:
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            logging.getLogger(name).propagate = False


def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger. Call `setup_logging()` once at app start.
    """
    return logging.getLogger(name)
