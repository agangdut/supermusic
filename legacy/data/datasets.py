"""
Datasets module for SuperMusic.

Handles loading built-in or external datasets (Kaggle, Maestro, Lofi, etc.)
and preparing them for the pipeline.
"""

from pathlib import Path
import pandas as pd

# Default directory where datasets are stored
DATASETS_DIR = Path(__file__).resolve().parent / "files"
DATASETS_DIR.mkdir(exist_ok=True)

def list_available_datasets():
    """
    List the available datasets in the datasets directory.
    """
    return [p.name for p in DATASETS_DIR.glob("*") if p.is_file()]

def load_dataset(name: str) -> pd.DataFrame:
    """
    Load a dataset by name from the datasets directory.
    Currently supports CSV files.
    """
    file_path = DATASETS_DIR / name
    if not file_path.exists():
        raise FileNotFoundError(f"Dataset '{name}' not found in {DATASETS_DIR}")
    if file_path.suffix.lower() == ".csv":
        return pd.read_csv(file_path)
    else:
        raise ValueError(f"Unsupported dataset format: {file_path.suffix}")

def save_dataset(df: pd.DataFrame, name: str):
    """
    Save a DataFrame as a CSV in the datasets directory.
    """
    file_path = DATASETS_DIR / name
    df.to_csv(file_path, index=False)
    print(f"[datasets] Saved dataset to {file_path}")
