"""
Core pipeline modules for SuperMusic.

This package contains the core functionality:
- downloader: fetches audio and metadata
- separator: separates stems from audio
- transcription: transcribes audio to MIDI/notes
- metadata: enriches metadata from external sources
- visualization: creates 3D visualizations
"""

from .downloader import download_audio
from .separator import separate_stems
from .transcription import transcribe_audio
from .metadata import enrich_metadata
from .visualization import plot_umap

__all__ = [
    "download_audio",
    "separate_stems",
    "transcribe_audio",
    "enrich_metadata",
    "plot_umap",
]
