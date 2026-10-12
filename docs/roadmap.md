# 🛣️ Roadmap

## ✅ Working today

Verified against the running Docker stack with real audio (October 2026):

- [x] `docker compose up --build` builds and starts the UI, API, Redis and the three model servers (MuScriptor, YourMT3+, GAME)
- [x] Upload audio and CSV files
- [x] 🎹 Audio → MIDI in seven modes. **Full band** (MuScriptor) is the default for mixes and the most accurate on real pop; **Piano** for solo piano ([accuracy](transcription-accuracy.md))
- [x] 🎤 Lead vocal track, with GAME transcribing the singing when its service is running
- [x] 🖐️ Playable by two hands, Piano cover (Pop2Piano), and a piano MP3 preview for every MIDI job
- [x] 🎯 Melody match score against the separated voice
- [x] 🥁 Stem separation into 4 or 6 stems (Demucs), and transcribing just the stems you pick
- [x] 🧾 CSV enrichment with BPM, key and duration
- [x] ⬇️ Download audio from a YouTube link (yt-dlp, API only)
- [x] 🌌 Music Map: taste clusters, hidden connections and recommendations from a CSV or Spotify / Apple Music exports, with broad genres from listener tags
- [x] Live job progress (stage and time left) in the UI, with Lost / Try again when a job disappears
- [x] 🔐 Register, log in, and fetch your profile (API only)
- [x] Results saved to `./data` and downloadable from the UI
- [x] API test suite and CI on `master`

## 🎹 MIDI accuracy, next steps

- [x] Run the GAME vocal benchmark: GAME won (vocal F1 0.147 → 0.254) and is on by default
- [x] Compare our MuScriptor with the official server: same accuracy, its timing fix didn't help (see transcription-accuracy.md)
- [ ] Run the MuScriptor experiments: fast mode, beam search, per-stem (`muscriptor_fast`, `muscriptor_beam`, `muscriptor_stems`)
- [ ] Test MuScriptor on solo piano (MAESTRO) and classical (MusicNet); if it matches the Piano model, Auto gets simpler
- [ ] Add AMT-APC next to Pop2Piano as a second Piano cover engine
- [ ] Only then fine-tune, using cover pairs from `scripts/build_cover_dataset.py` ([training data survey](training-data.md))

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
- [ ] Push progress over the WebSocket at `/ws/jobs` instead of polling every 2 seconds

### 3. Sign-in that means something
- [ ] Login and sign-up pages in the UI
- [ ] Require a token on job and upload endpoints
- [ ] Each user sees only their own jobs and files
- [ ] Refuse to start with the default `JWT_SECRET_KEY` outside development

### 4. Screens for the features the API already has
The UI covers MIDI, stems, CSV and the Music Map. These work in the API but have no screen:
- [ ] Paste a YouTube link to download
- [ ] Build a similarity map from the audio itself (`/visualization/umap`), not just CSV columns
- [ ] Batch processing (`/batch/process`)
- [ ] "Download all" as a zip (`/export/*`)
- [ ] Play stems in the browser (MIDI already has a piano preview)

### 5. Safety and housekeeping
- [ ] Upload size limit
- [ ] Clean up old uploads and artifacts automatically
- [ ] Rate limits on the expensive endpoints (`slowapi` is installed and configured but not applied)
- [x] Remove the stub Next.js API routes in `frontend/pages/api/` (the UI calls FastAPI directly)

### 6. Deploying it
- [ ] A production compose file with HTTPS (for example behind Caddy or nginx)
- [ ] Build the frontend with the public API URL instead of `localhost`
- [ ] Optional GPU image for much faster Demucs (the model servers already have one)
- [ ] Container health checks and log collection

### 7. Quality
- [ ] Tests for UMAP, batch, export and the WebSocket (not yet verified end to end)
- [ ] Frontend tests
- [ ] Lint and format checks in CI (ruff, ESLint)

## 🌌 Music Map, next steps

- [ ] Add a CLAP vector per song as an optional "sound" feature with its own slider: CLAP grouped songs by genre more than twice as well as the current features (39% vs 16%), MERT came second ([experiment](music-map.md#research-would-a-music-model-map-better))
- [ ] Search your library with words ("sad slow piano ballad") using CLAP's text side

- [ ] Recommend songs **outside** your library (e.g. MusicBrainz, Spotify or Last.fm "similar tracks", placed on your map)
- [ ] Import listening history straight from the Spotify or Last.fm API (file exports already work)
- [ ] Save maps and watch your taste drift over time
- [ ] Turn a hidden connection or a cluster into a playlist with one click
- [ ] Play a 30-second preview when you click a star

## 💡 Ideas from the first prototype

`legacy/` holds the August 2025 prototype. These parts were never brought into the web app:

- [ ] Mixtape segmenter: split hour-long DJ mixes into tracks, export CSV/CUE
- [ ] ID3 tag write-back (the MusicBrainz genre lookup now lives in the Music Map)
- [ ] High-dimensional graph with thumbnail backgrounds
- [x] Training data pairs for a custom transcriber (now `scripts/build_cover_dataset.py`)
