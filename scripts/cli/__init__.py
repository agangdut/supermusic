"""
CLI package for SuperMusic.

This file makes the cli directory a Python package and can hold
shared CLI utilities or configuration used across multiple commands.
"""

# Optionally define a version string for CLI tools
__version__ = "0.1.0"

# Optionally import the main entry point so it’s easier to call
from .main import cli

__all__ = ["cli"]
