# supermusic/web/app.py
from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path
import tempfile, uuid, json, traceback

from yt_dlp import YoutubeDL

app = FastAPI(title="SuperMusic API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TMP_ROOT = Path(tempfile.gettempdir()) / "supermusic_uploads"
RESULTS_DIR = TMP_ROOT / "results"
TMP_ROOT.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/results", StaticFiles(directory=RESULTS_DIR), name="results")

def write_status(dirpath: Path, **data):
    dirpath.mkdir(parents=True, exist_ok=True)
    status_path = dirpath / "status.json"
    with status_path.open("w", encoding="utf-8") as f:
        json.dump(data, f)

def load_status(dirpath: Path):
    p = dirpath / "status.json"
    if not p.exists():
        return {"status": "unknown"}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "unknown"}

class YTReq(BaseModel):
    url: str
    api_key: str | None = None  # optional, not used by yt-dlp

@app.post("/download-youtube")
async def download_youtube(req: YTReq, background: BackgroundTasks):
    job_id = str(uuid.uuid4())
    outdir = RESULTS_DIR / "yt" / job_id
    write_status(outdir, status="pending", msg="queued")

    def job():
        try:
            write_status(outdir, status="downloading", msg="starting")
            # NOTE: Requires ffmpeg in PATH for MP3 postprocessing.
            # Install from https://www.gyan.dev/ffmpeg/builds/ and add to PATH on Windows.
            def progress_hook(d):
                # d['status'] in {'downloading','finished','error'}
                st = d.get("status")
                info = {
                    "status": "downloading" if st == "downloading" else ("postprocessing" if st == "finished" else st),
                    "downloaded_bytes": d.get("downloaded_bytes"),
                    "total_bytes": d.get("total_bytes") or d.get("total_bytes_estimate"),
                    "speed": d.get("speed"),
                    "eta": d.get("eta"),
                    "filename": d.get("filename"),
                    "msg": d.get("_default_template") or "",
                }
                write_status(outdir, **{k: v for k, v in info.items() if v is not None})

            ydl_opts = {
                "progress_hooks": [progress_hook],
                "format": "bestaudio/best",
                "outtmpl": str(outdir / "%(title)s.%(ext)s"),
                "noplaylist": True,
                "quiet": True,
                "nopart": False,  # leave .part files (so you see disk activity)
                "postprocessors": [
                    {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
                ],
                # YouTube throttling workarounds (optional):
                # "concurrent_fragment_downloads": 5,
                # "throttled_rate": 1024 * 1024,  # 1 MiB/s cap handling
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                },
                # If login/cookies needed, add:
                # "cookiefile": "cookies.txt",
            }

            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([req.url])

            # success
            write_status(outdir, status="done", msg="completed")
        except Exception as e:
            err = "".join(traceback.format_exception_only(type(e), e)).strip()
            write_status(outdir, status="error", msg=err)

    background.add_task(job)
    return {"ok": True, "job_id": job_id, "results_prefix": f"/results/yt/{job_id}/"}

@app.get("/jobs/{kind}/{job_id}")
async def job_results(kind: str, job_id: str):
    d = RESULTS_DIR / kind / job_id
    if not d.exists():
        return JSONResponse({"ok": False, "files": [], "status": "unknown"}, status_code=404)
    files = [
        {"name": p.name, "url": f"/results/{kind}/{job_id}/{p.name}", "size": p.stat().st_size}
        for p in d.iterdir() if p.is_file() and p.name != "status.json"
    ]
    st = load_status(d)
    return {"ok": True, "files": files, "status": st.get("status"), "progress": st}
