# 📚 SuperMusic API Reference

This page documents the main public functions and endpoints of the SuperMusic project.

---

## CLI Commands
| Command                      | Description                                |
|------------------------------|--------------------------------------------|
| `supermusic download <url>`  | Download audio and metadata from a URL.    |
| `supermusic separate <file>` | Separate stems from a local audio file.    |
| `supermusic transcribe`      | Transcribe audio to MIDI / notes.          |
| `supermusic visualize`       | Create UMAP/Plotly visualizations.         |

---

## Python Modules
### `supermusic.core.downloader`
- `download_audio(url: str) -> Path`: downloads and saves audio.
- `fetch_metadata(url: str) -> dict`: enriches audio with metadata.

### `supermusic.core.separator`
- `separate_stems(audio_path: Path, model: str) -> dict`: separates into stems.

### `supermusic.core.transcription`
- `transcribe_audio(audio_path: Path) -> Path`: outputs MIDI or JSON.

### `supermusic.core.visualization`
- `plot_umap(features: pd.DataFrame) -> plotly.Figure`: interactive plot.

---

## Web API (FastAPI/Flask)
| Endpoint           | Method | Description                           |
|--------------------|--------|---------------------------------------|
| `/`                | GET    | Main dashboard.                      |
| `/upload`          | POST   | Upload an audio file.                |
| `/metadata/<id>`   | GET    | Retrieve enriched metadata.          |
| `/visualization`   | GET    | Render an interactive Plotly plot.   |

---

*This API reference will grow as you add features.*  
