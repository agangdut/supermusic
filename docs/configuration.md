# ⚙️ Configuration

With Docker, put settings in a `.env` file next to `docker-compose.yml` (start from `.env.example`). Without Docker, set them as normal environment variables.

## Backend

| Variable | Default | What it does |
|---|---|---|
| `JWT_SECRET_KEY` | `change-me-in-production` | Signs login tokens. **Change it before anyone else can reach the API.** |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:3001` | Comma-separated sites allowed to call the API |
| `YOUTUBE_API_KEY` | _(empty)_ | Optional. Adds YouTube details during CSV enrichment |
| `SUPERMUSIC_ARTIFACT_DIR` | `/app/data/artifacts` in Docker | Where finished files are written and served from |
| `SUPERMUSIC_UPLOAD_DIR` | `<raw dir>/uploads` | Where uploads are saved |
| `SM_DATA_DIR` | `data/` | Root data folder |
| `SM_RAW_DIR` · `SM_INTERIM_DIR` · `SM_PROCESSED_DIR` · `SM_SAMPLES_DIR` | under `data/` | Working folders for each stage |
| `SM_SR` | `22050` | Sample rate used for audio analysis |
| `SM_DEMUCS_BIN` | `demucs` | Demucs command |
| `SM_BASIC_PITCH_BIN` | `basic-pitch` | Basic Pitch command |
| `SM_BASIC_PITCH_SERIALIZATION` | `onnx` | Basic Pitch model format (`onnx`, `tf`, `tflite`, `coreml`) |
| `SM_BASIC_PITCH_ONSET` · `SM_BASIC_PITCH_FRAME` · `SM_BASIC_PITCH_MIN_NOTE_MS` | `0.6` · `0.3` · `58` | General model settings, tuned on MAESTRO (see [accuracy](transcription-accuracy.md)) |
| `SM_BASIC_PITCH_MELODIA` | `0` | `1` turns Basic Pitch's "melodia trick" back on. It adds notes where a pitch keeps ringing with no new press heard; on two piano covers these were mostly wrong (note F1 0.74 → 0.80 and 0.78 → 0.88 with it off) |
| `SM_YTDLP_FORMAT` | `bestaudio/best` | yt-dlp format selector |
| `SM_FIG_DPI` | `140` | Resolution of generated images |
| `DATABASE_URL` | `sqlite:///./data/supermusic.db` | Reserved for the database (not used yet) |

## YourMT3+ service

| Variable | Default | What it does |
|---|---|---|
| `YOURMT3_URL` | `http://yourmt3:8100` | Where the backend finds the Full band transcriber |
| `MUSCRIPTOR_URL` | `http://muscriptor:8200` | Where the backend finds the "Full band (new)" MuScriptor transcriber |
| `HF_TOKEN` | (empty) | Hugging Face read token for MuScriptor's weights. Accept the licence on [muscriptor-medium](https://huggingface.co/MuScriptor/muscriptor-medium) first. Non-commercial use only (CC BY-NC 4.0) |
| `MUSCRIPTOR_MODEL` | `medium` | `small`, `medium` or `large` (large needs more than the RTX 2060's 6 GB) |

The `yourmt3` container runs on CPU unless you add `docker-compose.gpu.yml` (NVIDIA only). Its 562 MB model downloads once into `data/models/yourmt3`. To make the GPU the default on your machine, copy `docker-compose.gpu.yml` to `docker-compose.override.yml`; Compose loads that automatically, and git ignores it.

## Frontend

These are fixed when the frontend is **built**, so rebuild after changing them (`docker compose build frontend`).

| Variable | Default | What it does |
|---|---|---|
| `NEXT_PUBLIC_API_BASE` | `http://localhost:8000` | Where the browser sends API calls |
| `NEXT_PUBLIC_ARTIFACT_BASE` | `<API base>/artifacts` | Where result files are downloaded from |

## Ports

| Service | Port |
|---|---|
| Frontend | 3000 |
| Backend | 8000 |
| Redis | 6379 |
| YourMT3+ | 8100 (inside Docker only) |

Change the left-hand number in `docker-compose.yml` (for example `"8080:8000"`) if a port is taken.
