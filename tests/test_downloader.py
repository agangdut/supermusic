"""
Unit tests for the supermusic.core.downloader module.
"""

import pytest
from supermusic.core import downloader

def test_download_audio_prints_message(capsys):
    """
    Check that download_audio prints a message and returns None.
    """
    url = "https://example.com/audio.mp3"
    result = downloader.download_audio(url)

    # It should return None for now (until real logic implemented)
    assert result is None

    # Check printed output contains the URL
    captured = capsys.readouterr()
    assert url in captured.out
