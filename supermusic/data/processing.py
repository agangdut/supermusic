"""
Data preprocessing utilities for SuperMusic.

This module provides simple, composable functions to:
- clean & standardize metadata tables (pandas DataFrames)
- normalize numeric feature columns
- split data into train/test sets
- (stub) extract basic audio features for later ML tasks
"""

from __future__ import annotations
from pathlib import Path
from typing import Iterable, Tuple, Optional, List

import numpy as np
import pandas as pd

# Optional imports for audio feature extraction.
# Keep them inside functions to avoid heavy imports during non-audio workflows.


# ---------------------------
# Metadata / tabular helpers
# ---------------------------

def preprocess_audio_metadata(
    df: pd.DataFrame,
    title_col: str = "title",
    artist_col: str = "artist",
    duration_col: str = "duration_sec",
    drop_dupes: bool = True,
) -> pd.DataFrame:
    """
    Basic cleanup for a metadata DataFrame:
    - trims whitespace in common text columns
    - coerces duration to numeric (seconds)
    - optionally drops duplicate rows

    Parameters
    ----------
    df : pd.DataFrame
        Input metadata table.
    title_col, artist_col, duration_col : str
        Column names to clean/coerce if present.
    drop_dupes : bool
        If True, drop exact duplicate rows.

    Returns
    -------
    pd.DataFrame
        Cleaned copy of df.
    """
    df = df.copy()

    for col in [title_col, artist_col]:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str, errors="ignore")
                .fillna("")
                .map(lambda x: x.strip() if isinstance(x, str) else x)
            )

    if duration_col in df.columns:
        df[duration_col] = pd.to_numeric(df[duration_col], errors="coerce")

    if drop_dupes:
        df = df.drop_duplicates().reset_index(drop=True)

    return df


def normalize_features(
    df: pd.DataFrame,
    columns: Optional[Iterable[str]] = None,
    with_mean: bool = True,
    with_std: bool = True,
) -> Tuple[pd.DataFrame, dict]:
    """
    Normalize selected numeric columns using (x - mean) / std (if enabled).
    Stores fitted stats in a dict so you can apply the same transform later.

    Parameters
    ----------
    df : pd.DataFrame
        Input table.
    columns : iterable[str] or None
        Which columns to normalize. Defaults to all numeric columns.
    with_mean, with_std : bool
        Control centering and scaling.

    Returns
    -------
    (pd.DataFrame, dict)
        Transformed DataFrame and a stats dict with 'mean_' and 'std_'.
    """
    df = df.copy()

    if columns is None:
        columns = df.select_dtypes(include=[np.number]).columns.tolist()

    means, stds = {}, {}
    for col in columns:
        col_values = pd.to_numeric(df[col], errors="coerce")
        mu = float(col_values.mean()) if with_mean else 0.0
        sigma = float(col_values.std(ddof=0)) if with_std else 1.0
        # Avoid division by zero
        if sigma == 0:
            sigma = 1.0

        means[col] = mu
        stds[col] = sigma

        df[col] = (col_values - mu) / sigma if (with_mean or with_std) else col_values

    stats = {"mean_": means, "std_": stds, "columns": list(columns)}
    return df, stats


def apply_normalization(df: pd.DataFrame, stats: dict) -> pd.DataFrame:
    """
    Apply previously fitted normalization stats to a new DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        New data.
    stats : dict
        Dict returned by `normalize_features`.

    Returns
    -------
    pd.DataFrame
        Transformed DataFrame.
    """
    df = df.copy()
    columns: List[str] = stats.get("columns", [])
    means: dict = stats.get("mean_", {})
    stds: dict = stats.get("std_", {})

    for col in columns:
        if col not in df.columns:
            continue
        vals = pd.to_numeric(df[col], errors="coerce")
        mu = means.get(col, 0.0)
        sigma = stds.get(col, 1.0) or 1.0
        df[col] = (vals - mu) / sigma

    return df


def train_test_split_df(
    df: pd.DataFrame,
    test_size: float = 0.2,
    random_state: Optional[int] = 42,
    shuffle: bool = True,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Simple train/test split for DataFrames (without scikit-learn dependency).

    Parameters
    ----------
    df : pd.DataFrame
        Input table.
    test_size : float
        Fraction for test set (0 < test_size < 1).
    random_state : int | None
        Seed for reproducibility.
    shuffle : bool
        Whether to shuffle rows before splitting.

    Returns
    -------
    (train_df, test_df) : Tuple[pd.DataFrame, pd.DataFrame]
    """
    if not (0.0 < test_size < 1.0):
        raise ValueError("test_size must be between 0 and 1.")

    n = len(df)
    rng = np.random.default_rng(random_state)
    indices = np.arange(n)
    if shuffle:
        rng.shuffle(indices)

    split_idx = int(n * (1.0 - test_size))
    train_idx, test_idx = indices[:split_idx], indices[split_idx:]
    return df.iloc[train_idx].reset_index(drop=True), df.iloc[test_idx].reset_index(drop=True)


# ---------------------------
# Audio feature extraction
# ---------------------------

def extract_basic_features(
    audio_path: str | Path,
    sr: int = 22050,
) -> dict:
    """
    Extract a few lightweight audio features (duration, rms mean, tempo) as a stub.
    Expand this later with mel spectrograms, chroma, MFCCs, etc.

    Notes:
    - Imports librosa inside the function to avoid heavy import during non-audio workflows.
    - Handles basic errors gracefully and returns what it can.

    Returns
    -------
    dict
        Example:
        {
            "duration_sec": 123.4,
            "rms_mean": 0.0123,
            "tempo_est": 120.5
        }
    """
    audio_path = Path(audio_path)
    feats = {}

    try:
        import librosa  # local import to keep module import light

        y, _sr = librosa.load(audio_path.as_posix(), sr=sr, mono=True)
        feats["duration_sec"] = float(librosa.get_duration(y=y, sr=_sr))

        # RMS energy
        rms = librosa.feature.rms(y=y).squeeze()
        feats["rms_mean"] = float(np.mean(rms)) if rms.size else np.nan

        # Tempo (very rough)
        tempo, _ = librosa.beat.beat_track(y=y, sr=_sr)
        feats["tempo_est"] = float(tempo)

    except FileNotFoundError:
        feats["error"] = f"File not found: {audio_path}"
    except Exception as e:  # keep robust; refine exception handling as needed
        feats["error"] = f"Feature extraction failed: {e}"

    return feats
