"""
CLI commands for SuperMusic.

This module defines individual Click commands that can be registered
in main.py.
"""

import click
from supermusic.core import downloader, separator, transcription, metadata

@click.command()
@click.argument("url")
def download(url):
    """Download audio from a URL and enrich metadata."""
    downloader.download_audio(url)
    click.echo("Download complete.")

@click.command()
@click.argument("file")
def separate(file):
    """Separate stems from an audio file."""
    separator.separate_stems(file)
    click.echo("Separation complete.")

@click.command()
@click.argument("file")
def transcribe(file):
    """Transcribe audio to MIDI/notes."""
    transcription.transcribe_audio(file)
    click.echo("Transcription complete.")

@click.command()
@click.argument("data", type=str)
def enrich(data):
    """Enrich metadata (demo)."""
    metadata.enrich_metadata({"title": data})
    click.echo("Metadata enrichment complete.")
