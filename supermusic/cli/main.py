"""
Main entry point for the SuperMusic CLI.
"""

import click
from .commands import download, separate, transcribe, enrich

@click.group()
def cli():
    """SuperMusic CLI – download, process, and visualize music data."""
    pass

# Register commands from commands.py
cli.add_command(download)
cli.add_command(separate)
cli.add_command(transcribe)
cli.add_command(enrich)

if __name__ == "__main__":
    cli()
