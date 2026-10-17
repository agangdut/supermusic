"""Bake the sample library's Music Map into a static JSON file for the GitHub Pages demo.

The Pages demo has no backend, so the frontend reads this file instead of calling
/map/build. Only pandas, numpy, scikit-learn and umap-learn are needed; the audio and
transcription libraries the app package imports are stubbed out because the map never
touches them.

    python scripts/build_demo_map.py frontend/public/demo/sample-map.json
"""
import importlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

HEAVY = ["matplotlib", "matplotlib.pyplot", "librosa", "librosa.display", "soundfile", "pydub",
         "demucs", "torch", "torchaudio", "yt_dlp", "basic_pitch", "pretty_midi",
         "piano_transcription_inference", "transformers", "mir_eval"]
for name in HEAVY:
    try:
        importlib.import_module(name)
    except Exception:
        sys.modules[name] = MagicMock()

import pandas as pd  # noqa: E402
from app.core.music_map import MapOptions, build_map  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "frontend/public/demo/sample-map.json")
df = pd.read_csv(ROOT / "backend/app/sample_data/sample_library.csv")
result = build_map(df, MapOptions())
result["meta"]["source"] = "sample"
result["meta"]["community_corrected"] = 0
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(result, default=str))
print(f"Wrote {out} ({len(result.get('tracks', []))} tracks)")
