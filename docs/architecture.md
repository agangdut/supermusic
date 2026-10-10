# 🧭 Architecture

SuperMusic is two services, plus Redis (which is running but not used yet).

```mermaid
flowchart TB
    subgraph Browser
        UI[Next.js pages<br/>/ and /upload]
    end

    subgraph backend["FastAPI backend (port 8000)"]
        R[Routes<br/>upload · midi · stems · csv · tracks<br/>visualization · batch · export · auth · ws]
        S[(Job store<br/>in memory)]
        C[Core pipelines<br/>transcription · separator · metadata<br/>csv_enrichment · downloader · visualization]
    end

    subgraph disk["./data (mounted volume)"]
        UP[raw/uploads]
        AR[artifacts]
    end

    UI -- "fetch JSON" --> R
    R <--> S
    R -- "background task" --> C
    C -- "basic-pitch · demucs · yt-dlp · librosa" --> AR
    R --> UP
    AR -- "/artifacts static files" --> UI
```

## A job, step by step

```mermaid
sequenceDiagram
    participant UI as Next.js UI
    participant API as FastAPI
    participant W as Background task
    participant FS as data/

    UI->>API: POST /upload/audio (file)
    API->>FS: save to raw/uploads/audio/
    API-->>UI: { path }
    UI->>API: POST /midi/convert { source_path }
    API->>W: start job
    API-->>UI: { id, status: "running" }
    W->>W: basic-pitch (ONNX)
    W->>FS: write artifacts/{id}_song.mid
    W->>API: status = "done"
    loop every 2s
        UI->>API: GET /midi/jobs/{id}
    end
    API-->>UI: { status: "done", result.artifacts }
    UI->>API: GET /artifacts/{id}_song.mid
```

## Where things live

| Folder | What's in it |
|---|---|
| `backend/app/main.py` | App setup: CORS, error handlers, routers, `/artifacts` mount |
| `backend/app/routes/` | One file per area. Each starts a job and exposes `/jobs/{id}` |
| `backend/app/core/` | The real work. Wraps the ML command-line tools and librosa |
| `backend/app/models/job.py` | The `Job` object every route returns |
| `backend/app/utils/storage.py` | In-memory job store and artifact saving |
| `backend/app/database.py` | SQLAlchemy setup, **not wired in yet** |
| `frontend/pages/` | `index.js` (landing + 3D demo) and `upload.js` (the workspace) |
| `frontend/hooks/useUploadJobs.js` | Upload, start job, poll, collect results |
| `frontend/lib/api.js` | Small client for every backend call |

## Tools under the hood

| Task | Tool | Notes |
|---|---|---|
| MIDI | `basic-pitch` CLI | Uses the ONNX model; the TFLite one fails with numpy 2 |
| Stems | `demucs -n htdemucs` | CPU-only torch in Docker to keep the image smaller |
| Download | `yt-dlp` | Needs updating as YouTube changes |
| Features | librosa | BPM, rough key, duration |
| Map | umap-learn + Plotly | |

## Docker images

- **backend**: `python:3.10-slim` + ffmpeg + CPU torch + `requirements.txt`. Runs `uvicorn app.main:app --app-dir backend`.
- **frontend**: `node:18-alpine`, `npm ci` then `next build`, served by `next start`.
- **redis**: `redis:7-alpine`, reserved for a future job queue.
