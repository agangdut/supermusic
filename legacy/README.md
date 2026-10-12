# Legacy code

Older code kept for reference. **None of it is used by the current app** (`backend/`, `frontend/`, `services/`), it isn't tested, and some of it no longer runs. Start from the [root README](../README.md) instead.

| Folder | What it was |
|---|---|
| `supermusic/` | The first prototype (August 2025): YouTube download, metadata enrichment, mixtape segmenter, audio pairs, transcriber training, high-dimensional graph, desktop UI. Its own README is [PROTOTYPE_README.md](PROTOTYPE_README.md) |
| `web/supermusic/` | A small FastAPI + Jinja web app from the second iteration, before the Next.js UI |
| `utils/`, `data/` | Helper modules (file, logging, plotting, dataset loading) that only the prototype used |
| `scripts/` | The old click CLI, early research notebooks, deploy scripts and a SQLite migration script |
| `justfile` | Task runner for the prototype |

Download, metadata and transcription were ported into `backend/app/core/`. What was never ported is listed at the bottom of the [roadmap](../docs/roadmap.md).
