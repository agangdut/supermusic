# Generate a High Dimensional Graph from Youtube Music History Data

## Pip Requirements
Package                  Version
------------------------ -----------
cachetools               5.5.2
certifi                  2025.8.3
charset-normalizer       3.4.3
colorama                 0.4.6
filelock                 3.19.1
fsspec                   2025.7.0
google-api-core          2.25.1
google-api-python-client 2.179.0
google-auth              2.40.3
google-auth-httplib2     0.2.0
googleapis-common-protos 1.70.0
httplib2                 0.22.0
huggingface-hub          0.34.4
idna                     3.10
Jinja2                   3.1.6
joblib                   1.5.1
llvmlite                 0.44.0
MarkupSafe               3.0.2
mpmath                   1.3.0
narwhals                 2.1.2
networkx                 3.5
numba                    0.61.2
numpy                    2.2.6
packaging                25.0
pandas                   2.3.2
pillow                   11.3.0
pip                      25.2
plotly                   6.3.0
proto-plus               1.26.1
protobuf                 6.32.0
pyasn1                   0.6.1
pyasn1_modules           0.4.2
pynndescent              0.5.13
pyparsing                3.2.3
python-dateutil          2.9.0.post0
pytz                     2025.2
PyYAML                   6.0.2
regex                    2025.7.34
requests                 2.32.5
rsa                      4.9.1
safetensors              0.6.2
scikit-learn             1.7.1
scipy                    1.16.1
sentence-transformers    5.1.0
setuptools               80.9.0
six                      1.17.0
sympy                    1.14.0
threadpoolctl            3.6.0
tokenizers               0.21.4
torch                    2.8.0
tqdm                     4.67.1
transformers             4.55.3
typing_extensions        4.14.1
tzdata                   2025.2
umap-learn               0.5.9.post2
uritemplate              4.2.0
urllib3                  2.5.0
yt-dlp                   2025.8.20

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
