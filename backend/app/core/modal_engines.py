"""
Run the model servers (YourMT3+, MuScriptor, GAME, CLAP) on Modal's GPUs.

Locally and with docker compose, the backend talks to each model server over
HTTP and they share the data/ folder, so a request names a file path
("audio_path") and a folder for the result ("out_dir"). On Modal each model
server runs in its own GPU container with its own disk, so this module ships
the audio there with the request and brings the result files back into the
local out_dir. The clients (yourmt3_client.py and friends) call `post` instead
of HTTP when `enabled(engine)` says so; nothing else changes.

Turned on by SM_MODAL_ENGINES, a comma-separated list such as
"yourmt3,muscriptor,game,clap" (see deploy/modal_app.py and docs/deploy-modal.md).
Outside Modal the backend also needs MODAL_TOKEN_ID and MODAL_TOKEN_SECRET.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Iterator, Optional

APP = os.getenv("SM_MODAL_APP", "supermusic")
CLASSES = {"yourmt3": "YourMT3", "muscriptor": "MuScriptor", "game": "Game", "clap": "Clap"}


def enabled(engine: str) -> bool:
    names = {n.strip().lower() for n in os.getenv("SM_MODAL_ENGINES", "").split(",")}
    return engine in names


def _engine(engine: str):
    import modal

    return modal.Cls.from_name(APP, CLASSES[engine])()


def _pack(body: dict) -> tuple[dict, Optional[tuple[str, bytes]]]:
    """Take the local audio file out of the request so it can travel with it."""
    body = dict(body)
    audio = None
    if body.get("audio_path"):
        p = Path(body.pop("audio_path"))
        audio = (p.name, p.read_bytes())
    body.pop("out_dir", None)
    return body, audio


def _unpack(res: dict, local_out: Optional[str]) -> dict:
    """Write the result files into the local out_dir and point the reply's paths at them."""
    remote_out = res.get("out_dir")
    if local_out:
        base = Path(local_out)
        for rel, data in res.get("files", {}).items():
            dest = base / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)

    def fix(v):
        if isinstance(v, str) and remote_out and local_out and v.startswith(remote_out):
            return str(Path(local_out)) + v[len(remote_out):]
        if isinstance(v, dict):
            return {k: fix(x) for k, x in v.items()}
        if isinstance(v, list):
            return [fix(x) for x in v]
        return v

    return fix(res.get("reply", {}))


def post(engine: str, path: str, body: dict) -> dict:
    """POST to the engine on Modal, the way the client would over HTTP. Raises RuntimeError like the clients do."""
    payload, audio = _pack(body)
    try:
        res = _engine(engine).call.remote(path, payload, audio)
    except Exception as e:  # a failure inside the engine, or Modal unreachable
        raise RuntimeError(f"{engine} on Modal failed: {e}") from e
    if res.get("error"):
        raise RuntimeError(res["error"])
    return _unpack(res, body.get("out_dir"))


def post_raw(engine: str, path: str, data: bytes, content_type: str) -> dict:
    """POST raw bytes (CLAP's /embed/audio) or JSON and return the JSON reply."""
    try:
        res = _engine(engine).raw.remote(path, data, content_type)
    except Exception as e:
        raise RuntimeError(f"{engine} on Modal failed: {e}") from e
    if res.get("error"):
        raise RuntimeError(res["error"])
    return res["reply"]


def run_job(engine: str, body: dict, on_status: Callable[[dict], None]) -> dict:
    """MuScriptor's long jobs: start one on Modal and pass each progress update to on_status."""
    payload, audio = _pack(body)
    final = None
    try:
        updates: Iterator[dict] = _engine(engine).job.remote_gen(payload, audio)
        for st in updates:
            if "files" in st or st.get("error"):
                final = st
            else:
                on_status(st)
    except Exception as e:
        raise RuntimeError(f"{engine} on Modal failed: {e}") from e
    if not final:
        raise RuntimeError(f"{engine} on Modal stopped without a result")
    if final.get("error"):
        raise RuntimeError(final["error"])
    return _unpack(final, body.get("out_dir"))
