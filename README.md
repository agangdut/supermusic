# 🎧 SuperMusic — High-Dimensional Music Explorer

> Interactive tools to **visualize**, **enrich**, and **organize** music collections using embeddings, MusicBrainz metadata, and audio analysis.

<p align="center">
  <img src="https://img.shields.io/badge/python-3.9%2B-blue.svg" />
  <img src="https://img.shields.io/badge/plotly-interactive-ff69b4.svg" />
  <img src="https://img.shields.io/badge/UMAP-tSNE-success.svg" />
  <img src="https://img.shields.io/badge/MusicBrainz-API-purple.svg" />
</p>

---

## ✨ What is this?

**SuperMusic** is a toolkit for music data nerds and creators. It lets you:

- 📊 **Project high-dimensional features** (text or numeric) down to **2D/3D** with **UMAP** or **t-SNE** and explore them in an interactive **Plotly** scatter.
- 🧠 **Enrich tracks with MusicBrainz** (recording / release-group / artist) and derive **genres**.
- 🏷️ **Write genres back to MP3 ID3** tags (optional).
- ✂️ **Auto-segment 1-hour+ mixtapes** into musical sections using a novelty curve (MFCC/ΔMFCC/Chroma) and export **CSV/CUE**.
- 🖼️ **Thumbnails as backgrounds**: click/hover a point to swap the plot’s background to that track’s image.

---

## 🧩 Repo Structure (core tools)

| Script | What it does |
|---|---|
| `enrichedmetadata.py` | Read MP3s, look up **MusicBrainz**, pick **genre(s)** (prefers official MB genres → tags → RG/artist), optional **AcoustID** fallback, write ID3, export CSV. |
| `mixtape_segmenter.py` | Analyze long mix audio, find **transition boundaries**, export **segments.csv** and optional **.cue**, and a Plotly novelty plot. |
| `<your_visualizer_script>.py` | CLI to load a CSV, build text embeddings or scale numeric features, **UMAP/t-SNE** to 2D/3D, render an **interactive Plotly** HTML (`viz.html`). Supports custom axis names. |

> Replace `<your_visualizer_script>.py` with the filename you’re using for the projector (the script that outputs `viz.html`).

---

## ✅ What I’ve accomplished so far

- Built a **command-line visualizer** that:
  - accepts **text** (`SentenceTransformer`, e.g., `all-MiniLM-L6-v2`) or **numeric features**,
  - reduces with **UMAP/t-SNE** to **2D/3D**,
  - renders an **interactive Plotly** plot (fast **WebGL** for large sets),
  - hides axes and supports **custom axis titles** via `--dim-names "Mood,Energy,Style"`,
  - supports **thumbnail-as-background** swapping on click/hover.
- Implemented **MusicBrainz enrichment** to annotate tracks with **release-group** and **genres**, with a simple **on-disk cache** to be nice to the API.
- Shipped `enrichedmetadata.py` to **classify genre** from MB data and optionally **write back to ID3**.
- Prototyped `mixtape_segmenter.py` to **auto-detect sections** in long mixes and export **CUE/CSV** (+ optional Plotly preview).
- Added **sensible CLI defaults** and examples for reproducible runs.
- Validated on Windows dev env; tips included for **Chromaprint/fpcalc** and **ffmpeg** availability.

---

## 🚀 Quickstart

### 1) Install dependencies
```bash
pip install pandas numpy plotly scikit-learn umap-learn sentence-transformers \
            musicbrainzngs mutagen acoustid tqdm librosa scipy
# For fingerprinting & media I/O:
# macOS:  brew install chromaprint ffmpeg
# Ubuntu: sudo apt-get install chromaprint ffmpeg
# Windows: install fpcalc (Chromaprint) + ffmpeg and add both to PATH
