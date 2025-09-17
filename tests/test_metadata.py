"""
Unit tests for the supermusic.core.metadata module.
"""

import pytest
from supermusic.core import metadata

def test_enrich_metadata_prints_message(capsys):
    """
    Check that enrich_metadata prints a message and returns None.
    """
    sample_data = {"title": "Test Song"}
    result = metadata.enrich_metadata(sample_data)

    # It should return None for now (until real logic implemented)
    assert result is None

    # Check printed output contains a keyword from the data
    captured = capsys.readouterr()
    assert "Test Song" in captured.out
