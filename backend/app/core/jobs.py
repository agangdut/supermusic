"""
Waiting in line for the heavy jobs (stems, MIDI, piano covers, batches).

Each of those keeps a CPU (or the GPU) busy for minutes, so only SM_HEAVY_WORKERS
of them run at the same time (1 by default). The rest wait in line and see how
many jobs are ahead of them. Without this, ten people pressing the button at once
would all slow to a crawl, or run the server out of memory.

Two limits per person (a signed-in account, or a browser id / IP when signed out):
  SM_MAX_ACTIVE_JOBS  jobs waiting or running at once (3)
  SM_JOBS_PER_HOUR    jobs started in the last hour (20)
SM_REQUIRE_LOGIN_FOR_JOBS=1 turns heavy jobs off for signed-out visitors.

rate_limit() caps lighter endpoints that still cost something (sign-ups, uploads,
imports) per visitor's address.

While the site is being updated (deploy/update.sh), the data/updating file exists:
new jobs are turned away with "try again in a minute" and busy() tells the script
how many are still going, so the server only restarts once they've all finished.
"""
from __future__ import annotations

import asyncio
import os
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Awaitable, Callable, Deque, Dict, List, Optional

from fastapi import BackgroundTasks, Depends, HTTPException, Request

from app.middleware.auth import current_username
from app.models.job import Job, JobStatus


def _int(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, "") or default))
    except ValueError:
        return default


HEAVY_WORKERS = max(1, _int("SM_HEAVY_WORKERS", 1))
MAX_ACTIVE = _int("SM_MAX_ACTIVE_JOBS", 3)
PER_HOUR = _int("SM_JOBS_PER_HOUR", 20)


def limits_on() -> bool:
    """SM_RATE_LIMITS=0 turns every limit off (the tests do; don't on a public server)."""
    return os.getenv("SM_RATE_LIMITS", "1") != "0"


def login_required() -> bool:
    return os.getenv("SM_REQUIRE_LOGIN_FOR_JOBS", "0") == "1"


_lock = threading.Lock()
_line: List[Job] = []                       # waiting, oldest first
_active: Dict[str, set] = defaultdict(set)  # owner -> ids of their waiting or running jobs
_started: Dict[str, Deque[float]] = defaultdict(deque)
_slots: Optional[asyncio.Semaphore] = None


def _semaphore() -> asyncio.Semaphore:
    global _slots
    if _slots is None:
        _slots = asyncio.Semaphore(HEAVY_WORKERS)
    return _slots


def client_ip(request: Request) -> str:
    # Behind Caddy, uvicorn's --proxy-headers already puts the visitor's address here
    return request.client.host if request.client else "unknown"


def job_owner(request: Request, me: Optional[str] = Depends(current_username)) -> str:
    """Who is starting a heavy job, checked against the limits above (a FastAPI dependency)."""
    not_updating()
    if me:
        owner = f"user:{me}"
    elif login_required():
        raise HTTPException(status_code=401, detail="Sign in to run this. It's free, and keeps the line fair for everyone.")
    else:
        lid = (request.headers.get("x-listener-id") or "")[:64]
        owner = f"ip:{client_ip(request)}" + (f":{lid}" if lid else "")
    ip_key = f"ip:{client_ip(request)}"
    if not limits_on():
        return owner
    now = time.time()
    with _lock:
        if MAX_ACTIVE and len(_active[owner]) >= MAX_ACTIVE:
            raise HTTPException(status_code=429, detail=f"You already have {len(_active[owner])} jobs going. Wait for one to finish, then try again.")
        for key in {owner, ip_key}:
            hits = _started[key]
            while hits and hits[0] < now - 3600:
                hits.popleft()
            if PER_HOUR and len(hits) >= PER_HOUR:
                raise HTTPException(status_code=429, detail=f"That's {PER_HOUR} jobs in the last hour, the most for now. Try again a bit later.")
        for key in {owner, ip_key}:
            _started[key].append(now)
    return owner


def _update_line() -> None:
    for i, job in enumerate(_line):
        job.message = "Next in line…" if i == 0 else f"Waiting in line: {i} job{'s' if i != 1 else ''} ahead of yours"


def position(job_id: str) -> Optional[int]:
    """How many jobs are ahead of this one, or None when it isn't waiting."""
    with _lock:
        for i, job in enumerate(_line):
            if job.id == job_id:
                return i
    return None


def submit(bg: BackgroundTasks, job: Job, run: Callable[[Job], Awaitable[None]], owner: str) -> Job:
    """Put a heavy job in line. `run` does the work once a worker is free."""
    start_message = job.message
    with _lock:
        _active[owner].add(job.id)
        _line.append(job)
        job.mark_queued()
        _update_line()
    job._save()

    async def _go() -> None:
        try:
            async with _semaphore():
                with _lock:
                    if job in _line:
                        _line.remove(job)
                    _update_line()
                job.mark_running(start_message)
                await run(job)
        finally:
            with _lock:
                _active[owner].discard(job.id)
                if job in _line:
                    _line.remove(job)
            if job.status not in (JobStatus.done, JobStatus.error):
                job.mark_failed("The job stopped without a result.")

    bg.add_task(_go)
    return job


def rate_limit(name: str, per_hour: int, env: Optional[str] = None):
    """A dependency allowing `per_hour` calls per visitor's address (override with env var `env`)."""
    limit = _int(env, per_hour) if env else per_hour

    def check(request: Request) -> None:
        if not limit or not limits_on():
            return
        key = f"{name}:{client_ip(request)}"
        now = time.time()
        with _lock:
            hits = _started[key]
            while hits and hits[0] < now - 3600:
                hits.popleft()
            if len(hits) >= limit:
                raise HTTPException(status_code=429, detail="Too many tries in the last hour. Try again a bit later.")
            hits.append(now)

    return check


# ------------------------------------------------------------------------------
# Updates without stopping anyone's job (deploy/update.sh)
# ------------------------------------------------------------------------------
UPDATING_MESSAGE = "The site is updating. Try again in a minute or two."

_busy_counters: List[Callable[[], int]] = []


def _updating_file() -> Path:
    from app.core.config import settings

    return Path(settings.DATA_DIR) / "updating"


UPDATING_EXPIRES_S = 3 * 3600  # a pause left behind by a crashed update doesn't block jobs forever


def updating() -> bool:
    """True while an update waits for the running jobs to finish."""
    try:
        return time.time() - _updating_file().stat().st_mtime < UPDATING_EXPIRES_S
    except OSError:
        return False


def not_updating() -> None:
    """A dependency for anything that starts a job: refused while an update is waiting."""
    if updating():
        raise HTTPException(status_code=503, detail=UPDATING_MESSAGE)


def count_busy(counter: Callable[[], int]) -> None:
    """Register work kept outside the job store (e.g. Music Map imports) so busy() counts it."""
    _busy_counters.append(counter)


def busy() -> int:
    """Jobs waiting or running right now, in this server process."""
    from app.utils.storage import job_store

    n = sum(1 for j in list(dict.values(job_store)) if j.status in (JobStatus.queued, JobStatus.running))
    for counter in _busy_counters:
        try:
            n += int(counter())
        except Exception:
            pass
    return n
