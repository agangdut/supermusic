"""
Live progress for long-running jobs.

Pipeline code calls `report("Separating the voice…")` at each step without
knowing about jobs; the job runner binds a reporter for the duration of the
work with `reporting(job)`. Works across `run_in_executor` because
`run_with_context` copies the context into the worker thread.
"""
from __future__ import annotations

import contextvars
import functools
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Callable, Optional

_current: contextvars.ContextVar[Optional[Any]] = contextvars.ContextVar("progress_job", default=None)


def report(stage: str) -> None:
    """Record the step a job is on (no-op outside a job)."""
    job = _current.get()
    if job is None:
        return
    now = datetime.utcnow()
    log = list(getattr(job, "stages", None) or [])
    if log and log[-1].get("ended_at") is None:
        log[-1]["ended_at"] = now.isoformat()
    log.append({"label": stage, "started_at": now.isoformat(), "ended_at": None})
    job.stages = log
    job.stage = stage
    job.message = stage
    job.updated_at = now


@contextmanager
def reporting(job):
    token = _current.set(job)
    try:
        yield
    finally:
        _current.reset(token)


def run_with_context(fn: Callable, *args, **kwargs) -> Callable[[], Any]:
    """Wrap `fn` so it runs in an executor thread with the current reporter."""
    ctx = contextvars.copy_context()
    return functools.partial(ctx.run, fn, *args, **kwargs)


# Rough seconds of work per second of audio, measured on an RTX 2060 + Ryzen
# CPU (Docker). Used only to draw an estimated progress bar.
SPEED = {
    "basic": 0.05, "piano": 0.5, "multi": 0.12, "muscriptor": 0.3, "stems": 1.1, "cover": 0.6,
    "separate_vocals": 0.45, "detect": 0.0, "auto": 0.5,
}
FIXED = {"detect": 15.0, "multi": 5.0, "muscriptor": 20.0, "basic": 3.0, "piano": 5.0, "stems": 10.0, "cover": 15.0}


def estimate_seconds(mode: str, duration_s: Optional[float], vocal_split: bool = False) -> Optional[float]:
    if not duration_s:
        return None
    t = SPEED.get(mode, 0.5) * duration_s + FIXED.get(mode, 5.0)
    if mode == "auto":
        t = FIXED["detect"] + SPEED["multi"] * duration_s + FIXED["multi"]
    if vocal_split:
        t += SPEED["separate_vocals"] * duration_s
    return round(t, 1)


def friendly_error(err: str) -> str:
    """One sentence a user can act on, for the most common failures."""
    e = err.lower()
    if "yourmt3" in e and ("isn't running" in e or "connection refused" in e or "urlopen" in e):
        return "The Full band engine isn't running. Start it with: docker compose up -d yourmt3, then try again."
    if "out of memory" in e or "cuda error" in e or "memoryerror" in e or "killed" in e:
        return "The computer ran out of memory on this song. Try a shorter clip, or the General mode."
    if "muscriptor" in e and ("isn't running" in e or "connection refused" in e or "urlopen" in e):
        return "The MuScriptor engine isn't running. Start it with: docker compose up -d muscriptor, then try again."
    if "muscriptor" in e and ("hugging" in e or "gated" in e or "licen" in e or "load its model" in e):
        return "MuScriptor needs a Hugging Face token: accept its licence on huggingface.co/MuScriptor/muscriptor-medium and set HF_TOKEN in .env."
    if "not found" in e and ("audio" in e or "csv" in e or "no such file" in e):
        return "The uploaded file is gone (the server may have been reset). Upload it again."
    if "demucs" in e:
        return "Separating the song into parts failed. Try again, or use Full band, which doesn't need it."
    if "basic-pitch" in e or "basic pitch" in e:
        return "The General transcriber failed on this file. Try Full band instead."
    if "no notes" in e:
        return "No notes were found. Is the file silent or mostly speech?"
    if "format" in e or "decode" in e or "ffmpeg" in e:
        return "This audio file couldn't be read. Try converting it to MP3 or WAV first."
    return "Something went wrong. Try again, or pick a different mode."
