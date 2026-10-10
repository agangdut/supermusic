from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

import numpy as np
import pandas as pd

try:
    import librosa
    import librosa.display  # noqa: F401
except Exception as e:  # pragma: no cover
    librosa = None
    _librosa_error = e

try:
    import umap
except Exception as e:  # pragma: no cover
    umap = None
    _umap_error = e

try:
    import plotly.graph_objects as go
    import plotly.express as px
except Exception as e:  # pragma: no cover
    plotly = None
    _plotly_error = e

import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt  # noqa: E402

from app.core.config import settings


def _load(audio_path: str | Path) -> Tuple[np.ndarray, int]:
    if librosa is None:
        raise RuntimeError(
            f"librosa is not available: {_librosa_error}. "
            "Install it to enable visualizations."
        )
    y, sr = librosa.load(str(audio_path), sr=settings.SR, mono=True)
    return y, sr


def save_waveform_png(audio_path: str | Path, out_path: str | Path | None = None) -> Path:
    """
    Save a waveform image (PNG). Returns the output path.
    """
    y, sr = _load(audio_path)
    out_path = Path(out_path or (settings.STATIC_DIR / (Path(audio_path).stem + "_waveform.png")))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    plt.figure(figsize=(10, 3), dpi=settings.FIG_DPI)
    plt.plot(np.arange(len(y)) / sr, y)
    plt.xlabel("Time (s)")
    plt.ylabel("Amplitude")
    plt.title("Waveform")
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()
    return out_path


def save_melspectrogram_png(audio_path: str | Path, out_path: str | Path | None = None) -> Path:
    """
    Save a log-mel spectrogram image (PNG). Returns the output path.
    """
    y, sr = _load(audio_path)
    out_path = Path(out_path or (settings.STATIC_DIR / (Path(audio_path).stem + "_mel.png")))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    S = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=128)
    S_db = librosa.power_to_db(S, ref=np.max)

    plt.figure(figsize=(10, 3), dpi=settings.FIG_DPI)
    plt.imshow(S_db, origin="lower", aspect="auto")
    plt.colorbar(format="%+2.0f dB")
    plt.xlabel("Frames")
    plt.ylabel("Mel bins")
    plt.title("Log-Mel Spectrogram")
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()
    return out_path


def extract_audio_features_batch(audio_paths: List[str | Path]) -> pd.DataFrame:
    """
    Extract features from multiple audio files for UMAP visualization.
    Returns a DataFrame with features and metadata.
    """
    if librosa is None:
        raise RuntimeError(f"librosa is not available: {_librosa_error}")
    
    features_list = []
    
    for audio_path in audio_paths:
        try:
            y, sr = librosa.load(str(audio_path), sr=settings.SR, mono=True)
            
            # Extract various features
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            chroma = librosa.feature.chroma_cens(y=y, sr=sr).mean(axis=1)
            mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13).mean(axis=1)
            spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr).mean()
            spectral_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr).mean()
            zero_crossing_rate = librosa.feature.zero_crossing_rate(y).mean()
            
            features = {
                "path": str(audio_path),
                "tempo": float(tempo),
                "spectral_centroid": float(spectral_centroid),
                "spectral_rolloff": float(spectral_rolloff),
                "zero_crossing_rate": float(zero_crossing_rate),
            }
            
            # Add chroma features
            for i, val in enumerate(chroma):
                features[f"chroma_{i}"] = float(val)
            
            # Add MFCC features
            for i, val in enumerate(mfcc):
                features[f"mfcc_{i}"] = float(val)
            
            features_list.append(features)
        except Exception as e:
            print(f"Warning: Failed to extract features from {audio_path}: {e}")
    
    return pd.DataFrame(features_list)


def create_umap_visualization(
    df: pd.DataFrame,
    n_components: int = 3,
    n_neighbors: int = 15,
    min_dist: float = 0.1,
    metric: str = "euclidean"
) -> Dict[str, Any]:
    """
    Create UMAP visualization from feature DataFrame.
    Returns a dict with coordinates and metadata for Plotly.
    """
    if umap is None:
        raise RuntimeError(f"umap-learn is not available: {_umap_error}")
    
    # Select feature columns (exclude metadata)
    feature_cols = [c for c in df.columns if c not in ["path", "title", "artist", "id"]]
    X = df[feature_cols].values
    
    # Handle NaN values
    X = np.nan_to_num(X, nan=0.0)
    
    # Fit UMAP
    reducer = umap.UMAP(
        n_components=n_components,
        n_neighbors=n_neighbors,
        min_dist=min_dist,
        metric=metric,
        random_state=42
    )
    
    embedding = reducer.fit_transform(X)
    
    # Create result dict
    result = {
        "coordinates": embedding.tolist(),
        "metadata": []
    }
    
    # Add metadata for each point
    for idx, row in df.iterrows():
        result["metadata"].append({
            "path": row.get("path", ""),
            "title": row.get("title", ""),
            "artist": row.get("artist", ""),
            "id": row.get("id", str(idx)),
            "tempo": row.get("tempo"),
            "key": row.get("key"),
        })
    
    return result


def plot_umap(features: pd.DataFrame, **umap_kwargs) -> Any:
    """
    Create interactive Plotly figure from UMAP visualization.
    """
    if plotly is None:
        raise RuntimeError(f"plotly is not available: {_plotly_error}")
    
    vis_data = create_umap_visualization(features, **umap_kwargs)
    
    coords = np.array(vis_data["coordinates"])
    
    if coords.shape[1] == 3:
        # 3D scatter plot
        fig = go.Figure(data=go.Scatter3d(
            x=coords[:, 0],
            y=coords[:, 1],
            z=coords[:, 2],
            mode='markers',
            marker=dict(
                size=5,
                color=coords[:, 2],
                colorscale='Viridis',
                showscale=True
            ),
            text=[f"{m.get('title', '')} - {m.get('artist', '')}" for m in vis_data["metadata"]],
            hovertemplate='%{text}<extra></extra>'
        ))
        fig.update_layout(
            scene=dict(
                xaxis_title="UMAP 1",
                yaxis_title="UMAP 2",
                zaxis_title="UMAP 3"
            ),
            title="Music Similarity Visualization (UMAP 3D)"
        )
    else:
        # 2D scatter plot
        fig = go.Figure(data=go.Scatter(
            x=coords[:, 0],
            y=coords[:, 1],
            mode='markers',
            marker=dict(size=5),
            text=[f"{m.get('title', '')} - {m.get('artist', '')}" for m in vis_data["metadata"]],
            hovertemplate='%{text}<extra></extra>'
        ))
        fig.update_layout(
            xaxis_title="UMAP 1",
            yaxis_title="UMAP 2",
            title="Music Similarity Visualization (UMAP 2D)"
        )
    
    return fig
