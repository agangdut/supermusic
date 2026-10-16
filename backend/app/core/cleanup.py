"""
Deleting old uploads and results, so the disk doesn't fill up.

Uploaded songs, stems, MIDI files and job records older than SM_KEEP_DAYS (7)
are removed once a day. Kept: shared maps, the libraries behind people's own
maps, and everything in the database except old job records.
"""
from __future__ import annotations

import os
import shutil
import threading
import time
from pathlib import Path
from typing import Set

from app.core import store


def keep_days() -> float:
    try:
        return float(os.getenv("SM_KEEP_DAYS", "7") or 7)
    except ValueError:
        return 7.0


def _in_use() -> Set[Path]:
    """Files people's own maps still point at."""
    try:
        rows = store.connect().execute("SELECT library_csv FROM users WHERE library_csv IS NOT NULL").fetchall()
    except Exception:
        return set()
    return {Path(r["library_csv"]).resolve() for r in rows if r["library_csv"]}


def sweep(now: float | None = None) -> int:
    """Delete what's older than keep_days(). Returns how many files and folders went."""
    from app.routes.upload import UPLOAD_DIR
    from app.utils.storage import _ARTIFACT_DIR

    days = keep_days()
    if days <= 0:
        return 0
    cutoff = (now or time.time()) - days * 86400
    keep = _in_use()
    removed = 0
    for root in (UPLOAD_DIR / "audio", UPLOAD_DIR / "csv", _ARTIFACT_DIR):
        if not root.is_dir():
            continue
        for entry in root.iterdir():
            try:
                if entry.stat().st_mtime > cutoff:
                    continue
                if entry.is_dir():
                    if any(p.resolve() in keep for p in entry.rglob("*")):
                        continue
                    shutil.rmtree(entry, ignore_errors=True)
                elif entry.resolve() not in keep:
                    entry.unlink(missing_ok=True)
                removed += 1
            except OSError:
                continue
    try:
        store.connect().execute("DELETE FROM jobs WHERE updated_at < ?", (cutoff,))
    except Exception:
        pass
    return removed


def start() -> None:
    """Sweep at startup and then once a day, in the background."""
    def loop() -> None:
        while True:
            try:
                sweep()
            except Exception:
                pass
            time.sleep(86400)

    threading.Thread(target=loop, daemon=True, name="cleanup").start()
