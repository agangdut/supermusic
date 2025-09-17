"""
Utility package for SuperMusic.

Exposes common helpers for:
- file operations (atomic writes, JSON, listing audio files)
- logging (consistent project-wide loggers)
- plotting (quick Plotly helpers)
"""

from .file_ops import (
    ensure_dir,
    list_audio_files,
    read_json,
    write_json,
    sha256sum,
    atomic_write_bytes,
    atomic_write_text,
    safe_stem,
)
from .logging import get_logger, setup_logging
from .plotting import (
    scatter2d,
    scatter3d,
    save_plotly_html,
)

__all__ = [
    # file_ops
    "ensure_dir",
    "list_audio_files",
    "read_json",
    "write_json",
    "sha256sum",
    "atomic_write_bytes",
    "atomic_write_text",
    "safe_stem",
    # logging
    "get_logger",
    "setup_logging",
    # plotting
    "scatter2d",
    "scatter3d",
    "save_plotly_html",
]
