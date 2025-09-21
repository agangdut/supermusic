# supermusic/web/app.py
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from pathlib import Path
import shutil
import tempfile
import pandas as pd
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uuid
from fastapi import BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

RESULTS_DIR = TMP_ROOT / "results"; RESULTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/results", StaticFiles(directory=RESULTS_DIR), name="results")

# --- helper to sanitize names ---
def safe_name(s: str) -> str:
    return "".join(c for c in s if c.isalnum() or c in ("-", "_", ".", " ")).strip() or "track"

# ---- Per-track YouTube download (audio only) ----
class YTReq(BaseModel):
    url: str
    api_key: str | None = None  # not used by yt-dlp; keep for your testing/logging

@app.post("/download-youtube")
async def download_youtube(req: YTReq, background: BackgroundTasks):
    """
    Downloads a single YouTube URL's audio using yt-dlp and exposes a direct file URL.
    Returns {job_id, url} when done (simple background task).
    """
    job_id = str(uuid.uuid4())
    outdir = RESULTS_DIR / "yt" / job_id
    outdir.mkdir(parents=True, exist_ok=True)

    def job():
        from yt_dlp import YoutubeDL
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": str(outdir / "%(title)s.%(ext)s"),
            "quiet": True,
            "noplaylist": True,
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
            ],
        }
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([req.url])

    background.add_task(job)
    return {"ok": True, "job_id": job_id, "results_prefix": f"/results/yt/{job_id}/"}

# ---- Optional: quick list results for a job ----
@app.get("/jobs/{kind}/{job_id}")
async def job_results(kind: str, job_id: str):
    d = RESULTS_DIR / kind / job_id
    if not d.exists():
        return JSONResponse({"ok": False, "files": []}, status_code=404)
    files = [{"name": p.name, "url": f"/results/{kind}/{job_id}/{p.name}", "size": p.stat().st_size}
             for p in d.iterdir() if p.is_file()]
    return {"ok": True, "files": files}

RESULTS_DIR = TMP_ROOT / "results"; RESULTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/results", StaticFiles(directory=RESULTS_DIR), name="results")


from fastapi import BackgroundTasks

@app.post("/convert-midi")
async def convert_midi(background: BackgroundTasks, audio: List[UploadFile] = File(...)):
    paths = [_save_upload(f, TMP_ROOT/"convert_midi") for f in audio]
    outdir = RESULTS_DIR / "midi"; outdir.mkdir(exist_ok=True, parents=True)
    def job():
        # TODO replace with your real pipeline
        for p in paths: (outdir / (p.stem + ".mid")).write_bytes(b"MThd\x00\x00\x00\x06\x00\x01\x00\x01\x01\xE0")  # tiny placeholder
    background.add_task(job)
    return {"ok": True, "download_prefix": "/results/midi/"}


app = FastAPI(title="SuperMusic API")

# Allow your Next.js dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TMP_ROOT = Path(tempfile.gettempdir()) / "supermusic_uploads"
TMP_ROOT.mkdir(parents=True, exist_ok=True)

def _save_upload(f: UploadFile, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f.filename
    with out.open("wb") as w:
        shutil.copyfileobj(f.file, w)
    return out

@app.post("/convert-midi")
async def convert_midi(audio: List[UploadFile] = File(...)):
    """
    Stub: receive audio files and (later) call your transcription pipeline.
    """
    save_dir = TMP_ROOT / "convert_midi"
    paths = [ _save_upload(f, save_dir) for f in audio ]
    # TODO: call your real converter here
    # e.g., supermusic.core.transcription.convert_to_midi(paths)
    return {"ok": True, "received": [p.name for p in paths]}

@app.post("/separate-stems")
async def separate_stems(audio: List[UploadFile] = File(...)):
    """
    Stub: receive audio and (later) call Spleeter/Demucs.
    """
    save_dir = TMP_ROOT / "separate_stems"
    paths = [ _save_upload(f, save_dir) for f in audio ]
    # TODO: run demucs/spleeter here
    return {"ok": True, "received": [p.name for p in paths]}

@app.post("/enrich-csv")
async def enrich_csv(csv: UploadFile = File(...)):
    """
    Example: parse a YouTube Takeout-like CSV and return simple stats
    you already visualize on the frontend. Replace with your real enrichment.
    """
    save_dir = TMP_ROOT / "csv"
    path = _save_upload(csv, save_dir)

    try:
        df = pd.read_csv(path)
    except Exception:
        # Fallback if encoding or delimiter is unusual
        df = pd.read_csv(path, encoding="utf-8", sep=None, engine="python")

    # Heuristic: pick an artist/channel column if present
    for key in ["Artist", "artist", "Channel", "channel", "Creator", "creator"]:
        if key in df.columns:
            top = (
                df[key]
                .fillna("Unknown")
                .astype(str)
                .value_counts()
                .head(20)
                .reset_index()
            )
            top.columns = ["label", "count"]
            return {"ok": True, "stats": top.to_dict(orient="records")}

    # If no obvious key, just return column names
    return {"ok": True, "stats": [], "columns": df.columns.tolist()}
