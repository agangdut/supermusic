# Configuration

With Docker, put settings in a `.env` file next to `docker-compose.yml` (start from `.env.example`, or from `deploy/production.env.example` for a public site). Without Docker, set them as normal environment variables.

## Backend

| Variable | Default | What it does |
|---|---|---|
| `JWT_SECRET_KEY` | `change-me-in-production` | Signs login tokens. **Change it before anyone else can reach the API.** With `SM_ENV=production` the backend refuses to start without a random value of 32 characters or more (`openssl rand -hex 32`) |
| `SM_ENV` | _(empty)_ | `production` turns off the interactive API docs and refuses unsafe settings (default secret, `CORS_ORIGINS=*`). Set by `docker-compose.prod.yml` |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000` | Comma-separated sites allowed to call the API |
| `YOUTUBE_API_KEY` | _(empty)_ | Optional. Adds YouTube details during CSV enrichment |
| `LASTFM_API_KEY` | _(empty)_ | Optional, free from [last.fm/api](https://www.last.fm/api/account/create). Turns on **Import from Last.fm** (by username) and makes Music Map genres more accurate; without it MusicBrainz is used |
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
| `SM_FIG_DPI` | `140` | Resolution of chart images |
| `SM_PIANO_CHECKPOINT` | `data/models/piano_transcription.pth` | Piano model weights (downloaded on first use) |
| `SM_SOUNDFONT` | FluidR3 GM | Soundfont used for the piano MP3 preview |
| `SM_ADMINS` | _(empty)_ | Usernames (comma separated) that can open the admin page at `/admin`: reports from visitors and visitor stats |
| `SMTP_HOST` · `SMTP_PORT` · `SMTP_USER` · `SMTP_PASSWORD` | _(empty)_ · `587` | Any SMTP service (Resend, Postmark, Brevo, Mailgun, SES) for password reset emails. Port 465 uses TLS from the start, anything else STARTTLS. Without `SMTP_HOST`, development prints reset links to the log and production says reset isn't available |
| `MAIL_FROM` | _(empty)_ | Sender of those emails, e.g. `SuperMusic <hello@your-domain.com>`, on a domain your mail service verified |
| `SITE_URL` | `https://$SITE_DOMAIN`, else `http://localhost:3000` | The site's address, for links in emails |
| `SM_DB_PATH` | `data/supermusic.db` | The SQLite file holding accounts, shared song stats, votes and jobs. Back it up |

## Limits for a public site

These keep one person, or a burst of visitors, from filling the server. `docker-compose.prod.yml` sets the launch values shown in `deploy/production.env.example`.

| Variable | Default | What it does |
|---|---|---|
| `SM_HEAVY_WORKERS` | `1` | How many heavy jobs (stems, MIDI, piano covers, batches, downloads) run at once. The rest wait in line. Allow about 4 CPU cores and 6 GB of memory per worker |
| `SM_MAX_ACTIVE_JOBS` | `3` | Heavy jobs one person can have waiting or running at once (`0` = no limit) |
| `SM_JOBS_PER_HOUR` | `20` | Heavy jobs one person, or one address, can start per hour (`0` = no limit) |
| `SM_REQUIRE_LOGIN_FOR_JOBS` | `0` (`1` in production) | `1` = only signed-in people can start heavy jobs |
| `SM_MAX_UPLOAD_MB` | `100` | Largest single upload |
| `SM_MAX_SONG_MINUTES` | `15` | Longest song accepted for stems and MIDI |
| `SM_KEEP_DAYS` | `7` | Uploads, results and job records older than this are deleted once a day. Shared maps and the libraries behind people's own maps are kept. `0` keeps everything |
| `SM_ENABLE_DOWNLOADS` | `1` (`0` in production) | Downloading audio from YouTube, SoundCloud or Bandcamp links. Off on a public site: it's against YouTube's terms |
| `SM_RATE_LIMITS` | `1` | `0` turns every limit off. Only for tests |

Sign-ups, sign-ins, uploads, imports and map builds also have fixed per-hour limits per address.

## Model servers (MuScriptor, YourMT3+, GAME)

| Variable | Default | What it does |
|---|---|---|
| `YOURMT3_URL` | `http://yourmt3:8100` | Where the backend finds the Full band transcriber |
| `MUSCRIPTOR_URL` | `http://muscriptor:8200` | Where the backend finds MuScriptor, the default Full band transcriber |
| `HF_TOKEN` | (empty) | Hugging Face read token for MuScriptor's weights. Accept the licence on [muscriptor-medium](https://huggingface.co/MuScriptor/muscriptor-medium) first. Non-commercial use only (CC BY-NC 4.0) |
| `MUSCRIPTOR_MODEL` | `medium` | `small`, `medium` or `large` (large needs a GPU with more than 6 GB) |
| `MUSCRIPTOR_FAST` | `0` | `1` transcribes 4 five-second sections at once, about 30% faster, but it can cut held notes where sections join, so it's off by default |
| `CLAP_URL` | `http://clap:8300` | Where the backend finds the CLAP service that gives songs a "sound" description for the Music Map |
| `SM_MODAL_ENGINES` | _(empty)_ | Model servers to run on Modal instead of at the addresses above, e.g. `yourmt3,muscriptor,game,clap`. Set for you on Modal ([guide](deploy-modal.md)) |
| `CLAP_MODEL` | `laion/clap-htsat-unfused` | CLAP checkpoint. `laion/larger_clap_music` returned the same songs for every search in testing, so it isn't recommended |
| `GAME_URL` | `http://game:8300` | Where the backend finds the GAME singing transcriber. If it isn't reachable, Full band and Auto use MuScriptor's own voice track |
| `GAME_MODEL` | `medium` | `small`, `medium` or `large` GAME weights (non-commercial licence, downloaded on first use) |

The `muscriptor`, `yourmt3` and `game` containers run on CPU unless you add `docker-compose.gpu.yml` (NVIDIA only). Their weights download once into `data/models/` (YourMT3+'s is 562 MB). If a service isn't reachable, the backend falls back: Auto goes MuScriptor → YourMT3+ → Stems/General, and the Lead vocal uses the band model's own voice track without GAME. When GAME is on the GPU it also does the backend's voice separation (Demucs), which is several times faster than on the backend's CPU. To make the GPU the default on your machine, copy `docker-compose.gpu.yml` to `docker-compose.override.yml`; Compose loads that automatically, and git ignores it.

## Frontend

These are fixed when the frontend is **built**, so rebuild after changing them (`docker compose build frontend`).

| Variable | Default | What it does |
|---|---|---|
| `NEXT_PUBLIC_API_BASE` | `http://localhost:8000` | Where the browser sends API calls. The public site uses `/api` (same address as the site, set by `docker-compose.prod.yml`) |
| `API_INTERNAL_BASE` | `NEXT_PUBLIC_API_BASE` | Where the website's server finds the API when it draws a shared map's link preview. `http://backend:8000` in production. Set when the website starts, not when it's built |
| `NEXT_PUBLIC_ARTIFACT_BASE` | `<API base>/artifacts` | Where result files are downloaded from |
| `NEXT_PUBLIC_SPOTIFY_CLIENT_ID` | _(empty)_ | Optional. Turns on Map Radio's **Save to Spotify** button. With Docker, set `SPOTIFY_CLIENT_ID` in `.env` instead. See [Setting up "Save to Spotify"](music-map.md#setting-up-save-to-spotify) |

## Ports

| Service | Port |
|---|---|
| Frontend | 3000 |
| Backend | 8000 |
| YourMT3+ | 8100 (inside Docker only) |
| MuScriptor | 8200 (inside Docker only) |
| GAME | 8300 (inside Docker only) |

Change the left-hand number in `docker-compose.yml` (for example `"8080:8000"`) if a port is taken. On a public site only Caddy is reachable, on ports 80 and 443.
