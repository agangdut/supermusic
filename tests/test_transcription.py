"""
Unit tests for the supermusic.core.transcription module.
"""

import pytest
from supermusic.core import transcription

def test_transcribe_audio_prints_message(capsys):
    """
    Check that transcribe_audio prints a message and returns None.
    """
    audio_path = "test_audio.mp3"
    result = transcription.transcribe_audio(audio_path)

    # It should return None for now (until real logic implemented)
    assert result is None

    # Check printed output contains the file name
    captured = capsys.readouterr()
    assert audio_path in captured.out
