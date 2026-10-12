> **Legacy.** This is the README from the first SuperMusic prototype (August 2025), kept with the code it describes in `legacy/supermusic/`. Its commands and screenshots are out of date, and its "All Rights Reserved" note no longer applies: the whole repository is now under the [MIT licence](../LICENSE). The current app lives in `backend/` and `frontend/`; see the root README. Parts of this code (download, metadata, transcription) were ported into `backend/app/core/`. The mixtape segmenter, audio pairs, transcriber training, high-dimensional graph and desktop UI have not been ported yet.

# 🎧 SuperMusic — High-Dimensional Music Explorer

> Interactive tools to **visualize**, **enrich**, and **organize** music collections using embeddings, MusicBrainz metadata, and audio analysis.

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" />
  <img src="https://img.shields.io/badge/plotly-interactive-ff69b4.svg" />
  <img src="https://img.shields.io/badge/UMAP-tSNE-success.svg" />
  <img src="https://img.shields.io/badge/MusicBrainz-API-purple.svg" />
  <img src="https://img.shields.io/badge/Separation-Demucs%2FSpleeter-informational.svg" />
  <img src="https://img.shields.io/badge/Transcription-BasicPitch%2FPrettyMIDI-informational.svg" />
  
</p>

![CI](https://github.com/agangdut/supermusic/actions/workflows/ci.yml/badge.svg)

---

## 📚 Table of Contents

- [✨ What is this?](#-what-is-this)
- [🖼️ Screenshots](#️-screenshots)
- [🧩 Repo Structure](#-repo-structure)
- [🚀 Quickstart](#-quickstart)
  - [1) Create a virtual env & install](#1-create-a-virtual-env--install)
  - [2) System tools (media & fingerprinting)](#2-system-tools-media--fingerprinting)
  - [3) Configure API keys](#3-configure-api-keys-optional-but-useful)
- [🛠️ Core Tools (CLI)](#️-core-tools-cli)
  - [`link2mp3.py` — YouTube → MP3](#link2mp3py--youtube--mp3)
  - [`metadata.py` — YouTube metadata enricher](#metadatapy--youtube-metadata-enricher)
  - [`enrichedmetadata.py` — MusicBrainz + ID3 writeback](#enrichedmetadatapy--musicbrainz--id3-writeback)
  - [`mixtape_segmenter.py` — Auto-segment long mixes](#mixtape_segmenterpy--auto-segment-long-mixes)
  - [`highdgraph.py` — Embeddings → UMAP/t-SNE → Plotly](#highdgraphpy--embeddings--umaptsne--plotly)
  - [`supermusic.cli` (optional Typer CLI)](#supermusiccli-optional-typer-cli)
- [🧪 Using the `justfile` (optional)](#-using-the-justfile-optional)
- [⚙️ Config & Environment](#️-config--environment)
- [🧷 Tips & Troubleshooting](#-tips--troubleshooting)
- [🗺️ Roadmap](#️-roadmap)
- [📜 License](#-license)
- [🙏 Acknowledgements](#-acknowledgements)

---

## ✨ What is this?

**SuperMusic** is a toolkit for music nerds, DJs, and creators. It lets you:

- 📊 **Project high-dimensional features** (text or numeric) to **2D/3D** with **UMAP/t-SNE** and explore them in an interactive **Plotly** graph (WebGL for large sets).
- 🧠 **Enrich tracks with MusicBrainz** (recording / release-group / artist) and derive **genres**.
- 🏷️ **Write genres back to MP3 ID3** tags (optional).
- ✂️ **Auto-segment 1-hour+ mixtapes** into musical sections (MFCC/ΔMFCC/Chroma novelty curve), export **CSV/CUE**, and preview in Plotly.
- 🖼️ **Thumbnail-as-background**: click/hover a point to swap the plot’s background to that track’s image.

---

## 🖼️ Screenshots

> Replace the placeholders below with your actual images and keep them in `docs/img/`.

<p align="center">
  <img src="docs/img/visualizer.png" alt="SuperMusic Visualizer (UMAP 3D + Plotly)" width="75%"/>
</p>

<p align="center">
  <img src="docs/img/segmenter.png" alt="Mixtape Segmenter Novelty Curve and Sections" width="75%"/>
</p>

<p align="center">
  <img src="docs/img/report.png" alt="Interactive HTML Report Export" width="75%"/>
</p>

---

## 🧩 Repo Structure
```
.
├── pyproject.toml
├── README.md
├── .pre-commit-config.yaml
├── .github/
│   └── workflows/
│       └── ci.yml
├── src/
│   └── supermusic/
│       ├── core/          # feature extraction, segmentation, etc.
│       ├── io/            # csv/json/audio I/O helpers
│       ├── reporting/     # Plotly/HTML exports
│       ├── ui_desktop/    # (optional) desktop GUI
│       ├── scripts/       # small helpers (batch, etc.)
│       └── cli.py         # Typer/Click commands (optional)
├── scripts/               # one-off dev scripts (not packaged)
└── data/                  # (gitignored)
    ├── raw/               # immutable inputs (downloads, original audio)
    ├── external/          # user MP3s, third-party stems
    ├── interim/           # temp/intermediate (e.g., separated/)
    └── processed/         # final CSV/MIDI/HTML bundles
```

> Keep datasets and large outputs in `data/` (git-ignored). See **.gitignore**.

---

## 🚀 Quickstart

### 1) Create a virtual env & install

**Windows (PowerShell)**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip wheel
pip install -e ".[dev]"
```

**macOS/Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip wheel
pip install -e ".[dev]"
```

### 2) System tools (media & fingerprinting)

ffmpeg – media I/O

    macOS: brew install ffmpeg

    Ubuntu: sudo apt-get install ffmpeg

    Windows: download ffmpeg and add to PATH

Chromaprint (fpcalc) – for AcoustID (optional)

    macOS: brew install chromaprint

    Ubuntu: sudo apt-get install chromaprint

    Windows: install fpcalc and add to PATH

### 3) Configure API keys (optional but useful)

Set these as environment variables:

    YOUTUBE_API_KEY – for metadata.py (YouTube Data API v3)

    ACOUSTID_API_KEY – for AcoustID fingerprint lookups

    SUPER_MUSIC_DATA – override default ./data root if you store datasets elsewhere

🛠️ Core Tools (CLI)

    All examples assume you’re in the repo root with the venv active. Paths use data/….

link2mp3.py — YouTube → MP3

    Input: a URL or a CSV with a “Video ID” column

    Output: high-quality VBR MP3 with embedded thumbnail + ID3 fields

    Typical flags:

        --url <youtube-url> (mutually exclusive with --csv)

        --csv <csv-path> (expects column Video ID)

        --out <dir> output folder (default: data/external/mp3music)

        --template "<Artist> - <Title>" filename pattern (optional)

        --no-embed-thumb disable cover art embedding (optional)

python link2mp3.py --url "https://youtu.be/XXXXXXXX"
### or batch from CSV
python link2mp3.py --csv data/raw/my_videos.csv --out data/external/mp3music

metadata.py — YouTube metadata enricher

    Adds channel/title/publish date, category, views/likes/comments, duration, tags/chapters, thumbnails

    Guesses Genre/Year from topics/keywords/text

    Flags:

        --input <csv> input with at least Video ID

        --output <csv> output path

### Requires YOUTUBE_API_KEY
python metadata.py --input data/raw/music.csv --output data/processed/metadata.csv

enrichedmetadata.py — MusicBrainz + ID3 writeback

    Looks up recording/release-group/artist, derives genres (prefers MB genres → tags), optional AcoustID fallback

    Optionally writes ID3 genre & year back to MP3s

    Flags:

        --mp3-root <dir> root folder of MP3s

        --out <csv> output CSV path

        --write-id3 write tags back to files (optional)

python enrichedmetadata.py \
  --mp3-root data/external/mp3music \
  --out data/processed/enriched.csv \
  --write-id3

mixtape_segmenter.py — Auto-segment long mixes

    Detects structural boundaries via novelty curve and exports CSV/CUE (+ Plotly HTML)

    Known flags (wired from your CLI):

        --out-csv OUT_CSV

        --out-cue OUT_CUE

        --plot-html PLOT_HTML

        --sr SR (sample rate)

        --hop HOP (hop length)

        --min-seconds MIN_SECONDS (min segment length)

        --expected-k EXPECTED_K (approx number of segments)

        --sigma-seconds SIGMA_SECONDS (novelty smoothing)

        --prominence PROMINENCE (peak picking prominence)

python mixtape_segmenter.py "data/raw/my_mix.wav" \
  --out-csv data/processed/segments.csv \
  --out-cue data/processed/segments.cue \
  --plot-html data/processed/segments.html \
  --sr 44100 --hop 512 \
  --min-seconds 30 \
  --expected-k 15 \
  --sigma-seconds 1.2 \
  --prominence 0.08

highdgraph.py — Embeddings → UMAP/t-SNE → Plotly

    Loads CSV; builds text embeddings (SentenceTransformers) or scales numeric features; renders interactive Plotly plot

    Flags:

        --input <csv>

        --out <html>

        --method {umap,tsne}

        --dim {2,3}

        --text-col <colname> (if embedding text)

        --num-cols <col1,col2,...> (if numeric)

        --dim-names "Mood,Energy,Style" (axis titles)

        --thumb-col <colname> (optional background swap source)

python highdgraph.py \
  --input data/processed/enriched.csv \
  --text-col "title" \
  --method umap \
  --dim 3 \
  --out data/processed/viz.html \
  --dim-names "Mood,Energy,Style" \
  --thumb-col "thumbnail_url"

supermusic.cli (optional Typer CLI)

    If you expose a Typer/Click app in src/supermusic/cli.py, typical commands might be:

# Analyze one track and write an HTML report
python -m supermusic.cli analyze "data/raw/song.wav" --out "artifacts/song_report.html"

# Separate stems (Demucs default)
python -m supermusic.cli separate --engine demucs "data/raw/song.wav"

# Transcribe (e.g., vocals → MIDI)
python -m supermusic.cli transcribe "data/interim/separated/song/vocals.wav"

# End-to-end: report
python -m supermusic.cli report --track "data/raw/song.wav" --out "artifacts/report.html"

🧪 Using the justfile (optional)

If you installed just

:

just setup                   # create venv & install deps
just lint                    # ruff check + format
just test                    # pytest -q
just run path="data/raw/song.wav"
just separate path="data/raw/song.wav" engine=demucs
just transcribe path="data/interim/separated/song/vocals.wav"
just report path="data/raw/song.wav" out="artifacts/song_report.html"
just batch-separate "data/raw" demucs

    On Windows, recipes run in PowerShell and work without manual venv activation because they call the venv’s python directly.

⚙️ Config & Environment

    Data root: set SUPER_MUSIC_DATA to relocate data/ anywhere (e.g., another drive)

    Separation extras: pip install -e ".[separation]" (Demucs, Spleeter, Open-Unmix)

    Transcription extras: pip install -e ".[transcription]" (Basic-Pitch, PrettyMIDI, note-seq)

Optional badges block (keep in README once installed):
<p align="center"> <img src="https://img.shields.io/badge/Demucs-installed-brightgreen.svg" /> <img src="https://img.shields.io/badge/BasicPitch-installed-brightgreen.svg" /> </p>
🧷 Tips & Troubleshooting

    “fpcalc not found” → Install Chromaprint and ensure fpcalc is on PATH.

    “ffmpeg not found” → Install ffmpeg and ensure it’s on PATH.

    Pre-commit missing → python -m pip install pre-commit && python -m pre_commit install.

    Git lock error (.git/index.lock) → close tools using the repo, then delete the lock:

        PowerShell: Remove-Item -Force .git\index.lock

    Large/sensitive data committed → add to .gitignore, run git rm -r --cached data/, then commit. (To purge history, use git filter-repo.)

🗺️ Roadmap

    Desktop GUI (PySide6 / customtkinter)

    One-click Separate → Transcribe → MIDI

    Rich export reports (interactive HTML bundles)

    Optional web viewer (FastAPI + Next.js)

📜 License

Superseded: the repository is now MIT licensed (see the root LICENSE).

Legal note: Separation/transcription of copyrighted tracks is fine for personal/research use; distribution of stems/MIDI may require rights.
🙏 Acknowledgements

    MusicBrainz, AcoustID/Chromaprint

    SentenceTransformers, UMAP-learn, Plotly

    ffmpeg and the open-source audio community
