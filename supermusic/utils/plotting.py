"""
Plotly helpers for SuperMusic.
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.io as pio


def scatter2d(
    df: pd.DataFrame,
    x: str,
    y: str,
    color: Optional[str] = None,
    hover_data: Optional[list[str]] = None,
    title: str = "Scatter 2D",
):
    """
    Quick 2D scatter using Plotly Express.
    """
    fig = px.scatter(
        df,
        x=x,
        y=y,
        color=color,
        hover_data=hover_data,
        title=title,
    )
    return fig


def scatter3d(
    df: pd.DataFrame,
    x: str,
    y: str,
    z: str,
    color: Optional[str] = None,
    hover_data: Optional[list[str]] = None,
    title: str = "Scatter 3D",
):
    """
    Quick 3D scatter using Plotly Express.
    """
    fig = px.scatter_3d(
        df,
        x=x,
        y=y,
        z=z,
        color=color,
        hover_data=hover_data,
        title=title,
    )
    return fig


def save_plotly_html(fig, path: str | Path, auto_open: bool = False) -> Path:
    """
    Save a Plotly figure to a standalone HTML file.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pio.write_html(fig, file=path, auto_open=auto_open, include_plotlyjs="cdn")
    return path
