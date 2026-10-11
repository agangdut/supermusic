"""
Client for the MuScriptor service (services/muscriptor), a multi-instrument
transcriber from 2026 trained on far more real recordings than YourMT3+.
Runs in its own container, on the GPU when there is one, and writes a
multi-track MIDI with an instrument per track.
"""
from __future__ import annotations

import json
import os
import shutil
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from app.core.config import settings

URL = os.getenv("MUSCRIPTOR_URL", "http://muscriptor:8200")


def available() -> bool:
    """Running, and able to load its model (already loaded, or has a Hugging Face token)."""
    try:
        with urllib.request.urlopen(f"{URL}/health", timeout=3) as r:
            h = json.loads(r.read())
            return bool(h.get("loaded") or h.get("token"))
    except Exception:
        return False


def _call(method: str, path: str, body: dict | None = None, timeout: float = 30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{URL}{path}", data=data, method=method,
                                 headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(json.loads(e.read() or b"{}").get("detail", f"MuScriptor error {e.code}"))
    except urllib.error.URLError:
        raise RuntimeError("The MuScriptor service isn't running. Start it with: docker compose up -d muscriptor")


def _fmt(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m} min {s:02d} s" if m else f"{s} s"


def transcribe_muscriptor(audio_path: str | Path, out_dir: Path | None = None) -> Path:
    """Run MuScriptor and show live progress: it works through the song in 5-second sections."""
    from app.core.progress import report_detail

    audio_path = Path(audio_path)
    out_dir = (out_dir or (settings.PROCESSED_DIR / "midi")) / uuid.uuid4().hex
    job = _call("POST", "/jobs", {"audio_path": str(audio_path.resolve()), "out_dir": str(out_dir)})
    deadline = time.time() + 3 * 3600
    while time.time() < deadline:
        st = _call("GET", f"/jobs/{job['id']}")
        if st["status"] == "done":
            break
        if st["status"] == "error":
            raise RuntimeError(st.get("error") or "MuScriptor failed")
        cpu = " on the CPU, which is slow" if st.get("device") == "cpu" else ""
        if not st.get("total"):
            doing = {"loading": "loading the model (the very first run also downloads it)",
                     "waiting": "waiting for another song to finish"}.get(st["status"], "getting the audio ready")
            report_detail(f"MuScriptor: {doing}{cpu}…")
        else:
            done, total = st["completed"], st["total"]
            left = st.get("remaining_s")
            eta = f", about {_fmt(left)} left" if left and done else ""
            report_detail(f"MuScriptor{cpu}: section {done} of {total} ({round(100 * done / total)}%){eta}",
                          fraction=done / total, remaining_s=left if done else None)
        time.sleep(2)
    else:
        raise RuntimeError("MuScriptor took more than 3 hours; giving up")
    midi = Path(st["midi_path"])
    final = out_dir / f"{audio_path.stem}.mid"
    if midi != final:
        shutil.move(str(midi), final)
    # MuScriptor writes every note equally loud; follow the song's loudness instead
    # (quiet verses, loud choruses, melody over accompaniment) and pedal the piano parts
    from app.core.humanize import humanize

    report_detail("Shaping the dynamics to follow the song…")
    humanize(final, audio_path)
    return final
