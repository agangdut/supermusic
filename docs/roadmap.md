# 🛣️ Roadmap

## ✅ Working today

Verified against the running Docker stack with real audio (October 2026):

- [x] `docker compose up --build` builds and starts the UI, API and Redis
- [x] Upload audio and CSV files
- [x] 🎹 Audio → MIDI (Basic Pitch)
- [x] 🥁 Stem separation into 4 stems (Demucs)
- [x] 🧾 CSV enrichment with BPM, key and duration
- [x] ⬇️ Download audio from a YouTube link (yt-dlp)
- [x] 🔐 Register, log in, and fetch your profile
- [x] Results saved to `./data` and downloadable from the UI
- [x] API test suite and CI on `master`

## 🧱 Needed for a complete product

Ordered by how much each one matters.

### 1. Keep data across restarts
Jobs and user accounts live in memory, so restarting the backend loses them. `backend/app/database.py` already defines a SQLite/SQLAlchemy model for jobs but nothing uses it yet.
- [ ] Save jobs in the database instead of the in-memory `job_store`
- [ ] Save users in the database instead of `users_db`

### 2. A real job queue
Jobs run inside the web server process. A few long Demucs jobs can tie it up, and a crash loses every running job. Redis is already in `docker-compose.yml` but unused.
- [ ] Run jobs in a worker (RQ, Celery or arq) backed by Redis
- [ ] Limit how many heavy jobs run at once
- [ ] Show real progress in the UI (the WebSocket at `/ws/jobs` exists; the UI still polls)

### 3. Sign-in that means something
- [ ] Login and sign-up pages in the UI
- [ ] Require a token on job and upload endpoints
- [ ] Each user sees only their own jobs and files
- [ ] Refuse to start with the default `JWT_SECRET_KEY` outside development

### 4. Screens for the features the API already has
The UI covers MIDI, stems and CSV. These work in the API but have no screen:
- [ ] Paste a YouTube link to download
- [ ] Build a 3D similarity map from your own tracks (`/visualization/umap`)
- [ ] Batch processing (`/batch/process`)
- [ ] "Download all" as a zip (`/export/*`)
- [ ] Play stems and MIDI in the browser

### 5. Safety and housekeeping
- [ ] Upload size limit
- [ ] Clean up old uploads and artifacts automatically
- [ ] Rate limits on the expensive endpoints (`slowapi` is installed and configured but not applied)
- [ ] Remove the stub Next.js API routes in `frontend/pages/api/` (the UI calls FastAPI directly)

### 6. Deploying it
- [ ] A production compose file with HTTPS (for example behind Caddy or nginx)
- [ ] Build the frontend with the public API URL instead of `localhost`
- [ ] Optional GPU image for much faster Demucs
- [ ] Container health checks and log collection

### 7. Quality
- [ ] Tests for UMAP, batch, export and the WebSocket (not yet verified end to end)
- [ ] Frontend tests
- [ ] Lint and format checks in CI (ruff, ESLint)

## 💡 Ideas from the first prototype

`legacy/` holds the August 2025 prototype. These parts were never brought into the web app:

- [ ] Mixtape segmenter: split hour-long DJ mixes into tracks, export CSV/CUE
- [ ] MusicBrainz genre lookup with ID3 tag write-back
- [ ] High-dimensional graph with thumbnail backgrounds
- [ ] Training data pairs for a custom transcriber
