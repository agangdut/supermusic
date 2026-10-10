# SuperMusic

SuperMusic is a web app and Python pipeline for downloading, processing, enriching and visualizing music. It covers audio download, stem separation, MIDI transcription, CSV and metadata enrichment, and interactive UMAP/Plotly views.

## Layout

```
backend/     FastAPI app (routes, jobs, auth, websocket, batch, export)
frontend/    Next.js UI
scripts/     CLI, deploy scripts, research notebooks
supermusic/  Small Jinja web app
utils/       Shared helpers (file ops, logging, plotting)
data/        Dataset helpers; large data stays git-ignored
docs/        Usage, API and architecture notes
legacy/      Earlier standalone prototypes (see legacy/README.md)
```

## Run it

With Docker:

```bash
docker compose up --build
```

The API is on http://localhost:8000 and the UI on http://localhost:3000.

Without Docker:

```bash
pip install -r requirements.txt
uvicorn app.main:app --app-dir backend --reload
```

```bash
cd frontend && npm install && npm run dev
```

## More

- [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md): what the backend implements
- [FRONTEND_INTEGRATION.md](FRONTEND_INTEGRATION.md): how the UI talks to the API
- [docs/usage.md](docs/usage.md) and [docs/api.md](docs/api.md)

## License

MIT. See [LICENSE](LICENSE).
