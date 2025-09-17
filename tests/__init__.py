"""
Test package for SuperMusic.

This file makes the tests directory a Python package so that imports work correctly.
You can also define common test fixtures or utilities here.
"""

# Optionally, set a global test marker or environment variable
import os

# Indicate we’re in a test environment (useful for conditional logic in your code)
os.environ.setdefault("SUPERMUSIC_ENV", "test")
