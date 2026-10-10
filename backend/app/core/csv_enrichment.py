from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd

from app.core.metadata import enrich_track_record
from app.core.downloader import download_audio
from app.core.metadata_enrichment import enrich_with_external_apis


def enrich_csv_file(
    csv_path: str | Path,
    output_path: str | Path | None = None,
    strategy: str = "youtube+acousticbrainz",
    options: Dict[str, Any] | None = None
) -> Path:
    """
    Enrich a CSV file with metadata.
    
    Args:
        csv_path: Path to input CSV
        output_path: Path to save enriched CSV (default: adds _enriched suffix)
        strategy: Enrichment strategy identifier
        options: Additional options for enrichment
    
    Returns:
        Path to enriched CSV file
    """
    options = options or {}
    csv_path = Path(csv_path)
    
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    
    # Read CSV
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        raise ValueError(f"Failed to read CSV: {e}")
    
    if df.empty:
        raise ValueError("CSV file is empty")
    
    # Determine output path
    if output_path is None:
        output_path = csv_path.parent / f"{csv_path.stem}_enriched{csv_path.suffix}"
    else:
        output_path = Path(output_path)
    
    # Enrich each row
    enriched_rows = []
    total_rows = len(df)
    
    for idx, row in df.iterrows():
        row_dict = row.to_dict()
        
        # Try to enrich with audio features if we have a path/URL
        try:
            # Check if we need to download first
            audio_path = row_dict.get("local_path") or row_dict.get("audio_path")
            youtube_url = row_dict.get("youtube_url") or row_dict.get("url")
            
            if youtube_url and not audio_path:
                # Download audio first
                try:
                    audio_path = download_audio(str(youtube_url))
                    row_dict["local_path"] = str(audio_path)
                except Exception as e:
                    print(f"Warning: Failed to download {youtube_url}: {e}")
                    audio_path = None
            
            if audio_path:
                # Enrich with audio features
                features = enrich_track_record({"local_path": str(audio_path)})
                row_dict.update(features)
            
            # Enrich with external APIs
            if req.strategy in ["youtube+acousticbrainz", "youtube", "external"]:
                external_data = enrich_with_external_apis(row_dict)
                row_dict.update(external_data)
        except Exception as e:
            # Continue even if enrichment fails for a row
            print(f"Warning: Failed to enrich row {idx}: {e}")
        
        enriched_rows.append(row_dict)
    
    # Create enriched DataFrame
    enriched_df = pd.DataFrame(enriched_rows)
    
    # Save enriched CSV
    enriched_df.to_csv(output_path, index=False)
    
    return output_path

