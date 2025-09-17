"""
Configuration module for SuperMusic.

This module centralizes configuration values, default paths, and environment
variables so that the rest of the project can import settings from here.
"""

import os
from pathlib import Path

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Directory to store downloaded audio files
DOWNLOADS_DIR = BASE_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

# Directory to store temporary or processed files
TEMP_DIR = BASE_DIR / "temp"
TEMP_DIR.mkdir(exist_ok=True)

# Example of pulling an API key from the environment
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "your_default_key_here")

# Default audio format
DEFAULT_AUDIO_FORMAT = "mp3"

# Default model for stem separation
DEFAULT_SEPARATOR_MODEL = "demucs"

# Logging settings (if you want to standardize logging project-wide)
LOG_LEVEL = os.environ.get("SUPERMUSIC_LOG_LEVEL", "INFO")
