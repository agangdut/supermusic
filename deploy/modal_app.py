"""
SuperMusic on Modal (https://modal.com): the whole site, with the models on GPUs.

    pip install modal && modal setup            # once, signs this computer in
    modal secret create supermusic SITE_DOMAIN=<workspace>--supermusic.modal.run \\
        JWT_SECRET_KEY=$(openssl rand -hex 32) CONTACT_EMAIL=you@example.com
    CONTACT_EMAIL=you@example.com modal deploy deploy/modal_app.py

docs/deploy-modal.md explains every step and setting.

What runs where:

- `web`: one always-on CPU container with the API (FastAPI), the website
  (Next.js) and Caddy joining them on one address, like docker-compose.prod.yml.
  Stems, Basic Pitch, Piano and Pop2Piano run here. It is the only container
  that touches the `supermusic-data` volume (accounts database, uploads,
  results), so there is never more than one of it.
- `YourMT3`, `MuScriptor`, `Game`: the transcription engines, each on a GPU that
  starts when a job needs it and stops a couple of minutes after the last one.
  The backend sends them the audio and gets the MIDI back
  (backend/app/core/modal_engines.py). Their model weights are kept on the
  `supermusic-models` volume so they download only once.
- `Clap`: Music Map sound search, on a small CPU container that also stops when idle.
"""
from __future__ import annotations

import os
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[1]
APP_NAME = "supermusic"
GPU = os.getenv("SM_MODAL_GPU", "T4")  # T4 is the cheapest; L4 is about 1.5x faster

app = modal.App(APP_NAME)
data = modal.Volume.from_name("supermusic-data", create_if_missing=True, version=2)
models = modal.Volume.from_name("supermusic-models", create_if_missing=True, version=2)
secret = modal.Secret.from_name("supermusic")


# ---------------------------------------------------------------------------
# The site: API + website + Caddy in one container
# ---------------------------------------------------------------------------

web_image = (
    modal.Image.from_registry("node:20-bookworm-slim", add_python="3.10")
    .apt_install("ffmpeg", "fluidsynth", "fluid-soundfont-gm", "curl", "ca-certificates")
    .run_commands(
        "curl -fsSL https://github.com/caddyserver/caddy/releases/download/v2.8.4/caddy_2.8.4_linux_amd64.tar.gz"
        " | tar -xz -C /usr/local/bin caddy"
    )
    # CPU-only torch first, so demucs doesn't pull several GB of CUDA wheels
    .pip_install("torch", "torchaudio", index_url="https://download.pytorch.org/whl/cpu",
                 extra_index_url="https://pypi.org/simple")
    .pip_install_from_requirements(str(ROOT / "requirements.txt"))
    .pip_install("modal")
    # NEXT_PUBLIC_ values are baked into the website when it is built
    .env({
        "NEXT_PUBLIC_API_BASE": "/api",
        "NEXT_PUBLIC_CONTACT_EMAIL": os.getenv("CONTACT_EMAIL", ""),
        "NEXT_PUBLIC_SPOTIFY_CLIENT_ID": os.getenv("SPOTIFY_CLIENT_ID", ""),
        "NEXT_TELEMETRY_DISABLED": "1",
    })
    .add_local_dir(str(ROOT / "frontend"), "/srv/frontend", copy=True,
                   ignore=["node_modules", ".next", "out", "**/.env*"])
    .run_commands(
        "cd /srv/frontend && npm ci --no-audit --no-fund && npm run build"
        " && cp -r .next/static .next/standalone/.next/static && cp -r public .next/standalone/public"
    )
    .add_local_file(str(ROOT / "deploy" / "Caddyfile.modal"), "/etc/caddy/Caddyfile")
    .add_local_dir(str(ROOT / "backend"), "/app/backend", ignore=["tests", "**/__pycache__", "data"])
    .add_local_dir(str(ROOT / "scripts"), "/app/scripts", ignore=["**/__pycache__"])
)

# Defaults for the backend; anything in the "supermusic" secret overrides them.
WEB_DEFAULTS = {
    "SM_ENV": "production",
    "PYTHONPATH": "/app:/app/backend",
    "SM_DATA_DIR": "/app/data",
    "SM_RAW_DIR": "/app/data/raw",
    "SM_INTERIM_DIR": "/app/data/interim",
    "SM_PROCESSED_DIR": "/app/data/processed",
    "SUPERMUSIC_ARTIFACT_DIR": "/app/data/artifacts",
    "TORCH_HOME": "/app/data/models/torch",
    "SM_REQUIRE_LOGIN_FOR_JOBS": "1",
    "SM_ENABLE_DOWNLOADS": "0",
    "SM_HEAVY_WORKERS": "1",
    "SM_MAX_ACTIVE_JOBS": "3",
    "SM_JOBS_PER_HOUR": "20",
    "SM_MAX_UPLOAD_MB": "100",
    "SM_MAX_SONG_MINUTES": "15",
    "SM_KEEP_DAYS": "7",
    # The engines below. Leave MuScriptor and GAME (Lead vocal) out of this list on a
    # site that makes money: their licences are non-commercial.
    "SM_MODAL_ENGINES": "yourmt3,muscriptor,game,clap",
    "SM_MODAL_APP": APP_NAME,
}


@app.function(
    image=web_image,
    volumes={"/app/data": data},
    secrets=[secret],
    # Billed for what it reserves when idle (1 core, 2 GB) and what it uses during jobs (up to 8 cores, 16 GB)
    cpu=(1.0, 8.0),
    memory=(2048, 16384),
    # Exactly one: jobs in progress and the waiting line live in its memory, and only one
    # container may write the database on the volume
    min_containers=1,
    max_containers=1,
    timeout=600,
)
@modal.concurrent(max_inputs=500)
@modal.web_server(8080, startup_timeout=600, label=APP_NAME)
def web():
    import subprocess

    env = {**WEB_DEFAULTS, **os.environ}
    domain = env.get("SITE_DOMAIN", "").strip()
    if domain and not env.get("CORS_ORIGINS"):
        env["CORS_ORIGINS"] = f"https://{domain}"
    for d in ("raw", "interim", "processed", "artifacts", "models"):
        Path("/app/data", d).mkdir(parents=True, exist_ok=True)

    subprocess.Popen(
        ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "127.0.0.1", "--port", "8000",
         "--proxy-headers", "--forwarded-allow-ips", "*"],
        cwd="/app", env=env,
    )
    subprocess.Popen(
        ["node", "server.js"], cwd="/srv/frontend/.next/standalone",
        env={**env, "NODE_ENV": "production", "HOSTNAME": "127.0.0.1", "PORT": "3000",
             "API_INTERNAL_BASE": "http://127.0.0.1:8000"},
    )
    subprocess.Popen(["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"], env=env)


# ---------------------------------------------------------------------------
# The engines: each model server from services/, wrapped so the backend can send
# it audio and get the result files back (no shared disk on Modal)
# ---------------------------------------------------------------------------

def _start_server(port: int, wait_s: int = 1200):
    """Start services/<engine>/server.py and wait until it answers (it loads its model first)."""
    import subprocess
    import time
    import urllib.request

    proc = subprocess.Popen(["python", "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", str(port)],
                            cwd="/srv")
    deadline = time.time() + wait_s
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("the model server stopped while starting; see the logs above")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5):
                return proc
        except Exception:
            time.sleep(2)
    raise RuntimeError("the model server took too long to start")


def _http(port: int, method: str, path: str, data: bytes | None = None,
          content_type: str = "application/json", timeout: float = 3600) -> tuple[int, dict]:
    import json
    import urllib.error
    import urllib.request

    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method=method,
                                 headers={"Content-Type": content_type} if data is not None else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


def _workdir(payload: dict, audio: tuple[str, bytes] | None) -> tuple[Path, Path, dict]:
    import tempfile

    work = Path(tempfile.mkdtemp(prefix="job-", dir="/tmp"))
    out = work / "out"
    body = dict(payload, out_dir=str(out))
    if audio:
        name, blob = audio
        src = work / "in" / Path(name).name
        src.parent.mkdir(parents=True)
        src.write_bytes(blob)
        body["audio_path"] = str(src)
    return work, out, body


def _collect(work: Path, out: Path, reply: dict) -> dict:
    import shutil

    files = {str(f.relative_to(out)): f.read_bytes() for f in out.rglob("*") if f.is_file()} if out.exists() else {}
    shutil.rmtree(work, ignore_errors=True)
    return {"reply": reply, "files": files, "out_dir": str(out)}


def _call(port: int, path: str, payload: dict, audio: tuple[str, bytes] | None) -> dict:
    work, out, body = _workdir(payload, audio)
    import json

    status, reply = _http(port, "POST", path, json.dumps(body).encode())
    if status >= 400:
        return {"error": reply.get("detail") or f"error {status}"}
    return _collect(work, out, reply)


def _raw(port: int, path: str, data: bytes, content_type: str) -> dict:
    status, reply = _http(port, "POST", path, data, content_type, timeout=300)
    if status >= 400:
        return {"error": reply.get("detail") or f"error {status}"}
    return {"reply": reply}


def _torch_image(*pip: str) -> modal.Image:
    return (
        modal.Image.from_registry("pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime")
        .apt_install("ffmpeg", "libsndfile1", "git")
        .pip_install(*pip)
        .env({"HF_HOME": "/app/data/models/hf", "WANDB_MODE": "disabled"})
    )


ENGINE = dict(volumes={"/app/data/models": models}, secrets=[secret], timeout=3 * 3600,
              scaledown_window=120, max_containers=2)

yourmt3_image = (
    _torch_image("lightning==2.5.0", "transformers==4.40.2", "einops", "deprecated", "librosa", "mido",
                 "pretty_midi", "mir_eval", "matplotlib", "soundfile", "scipy", "scikit-learn", "pyyaml",
                 "requests", "tqdm", "torchmetrics", "smart-open", "torchaudio==2.6.0", "pytorch_lightning==2.5.0",
                 "wandb", "fastapi", "uvicorn[standard]")
    .add_local_dir(str(ROOT / "services" / "yourmt3"), "/srv", copy=True, ignore=["**/__pycache__"])
    .run_commands("ln -sfn /app/data/models/yourmt3/logs /srv/amt/logs")
)


@app.cls(image=yourmt3_image, gpu=GPU, **ENGINE)
class YourMT3:
    port = 8100

    @modal.enter()
    def start(self):
        self.proc = _start_server(self.port)

    @modal.method()
    def call(self, path: str, payload: dict, audio=None) -> dict:
        return _call(self.port, path, payload, audio)


muscriptor_image = (
    _torch_image("muscriptor==0.3.0", "pretty_midi", "fastapi", "uvicorn[standard]")
    .env({"MUSCRIPTOR_MODEL": os.getenv("MUSCRIPTOR_MODEL", "medium")})
    .add_local_file(str(ROOT / "services" / "muscriptor" / "server.py"), "/srv/server.py")
)


@app.cls(image=muscriptor_image, gpu=GPU, **ENGINE)
class MuScriptor:
    port = 8200

    @modal.enter()
    def start(self):
        self.proc = _start_server(self.port)

    @modal.method()
    def call(self, path: str, payload: dict, audio=None) -> dict:
        return _call(self.port, path, payload, audio)

    @modal.method()
    def job(self, payload: dict, audio=None):
        """Start a MuScriptor job and yield its progress, then the result."""
        import json
        import time

        work, out, body = _workdir(payload, audio)
        status, started = _http(self.port, "POST", "/jobs", json.dumps(body).encode())
        if status >= 400:
            yield {"error": started.get("detail") or f"error {status}"}
            return
        while True:
            status, st = _http(self.port, "GET", f"/jobs/{started['id']}")
            if status >= 400 or st.get("status") == "error":
                yield {"error": st.get("error") or st.get("detail") or "MuScriptor failed"}
                return
            if st.get("status") == "done":
                yield _collect(work, out, st)
                return
            yield st
            time.sleep(2)


game_image = (
    _torch_image("click", "colorednoise", "einops>=0.7.0", "h5py", "librosa", "lightning", "loguru", "matplotlib",
                 "mido", "numpy<2.0.0", "omegaconf", "pydantic>=2.11,<3.0", "resampy", "scipy>=1.10.0", "sympy",
                 "torchmetrics", "tqdm", "pretty_midi", "fastapi", "uvicorn[standard]", "demucs>=4.1", "soundfile")
    .run_commands(
        "git clone https://github.com/openvpi/GAME /opt/game"
        " && git -C /opt/game checkout f4239345f0fed21890d362c74a35fd857724aa82 && rm -rf /opt/game/.git"
    )
    .env({"TORCH_HOME": "/app/data/models/torch"})
    .add_local_file(str(ROOT / "services" / "game" / "server.py"), "/srv/server.py")
)


@app.cls(image=game_image, gpu=GPU, **ENGINE)
class Game:
    port = 8300

    @modal.enter()
    def start(self):
        self.proc = _start_server(self.port)

    @modal.method()
    def call(self, path: str, payload: dict, audio=None) -> dict:
        return _call(self.port, path, payload, audio)


clap_image = (
    _torch_image("transformers>=4.38,<5", "librosa", "soundfile", "fastapi", "uvicorn[standard]")
    .env({"CLAP_MODEL": os.getenv("CLAP_MODEL", "laion/clap-htsat-unfused")})
    .add_local_file(str(ROOT / "services" / "clap" / "server.py"), "/srv/server.py")
)


@app.cls(image=clap_image, cpu=2.0, memory=4096, **{**ENGINE, "scaledown_window": 300, "max_containers": 1})
@modal.concurrent(max_inputs=4)
class Clap:
    port = 8300

    @modal.enter()
    def start(self):
        self.proc = _start_server(self.port)

    @modal.method()
    def raw(self, path: str, data: bytes, content_type: str) -> dict:
        return _raw(self.port, path, data, content_type)
