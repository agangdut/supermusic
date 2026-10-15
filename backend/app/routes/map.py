from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.core import community, map_share
from app.routes.community import client_ip, listener
from app.core.music_map import MapOptions, build_map, similar_tracks, estimate_build_seconds

router = APIRouter(prefix="/map", tags=["map"])

SAMPLE_CSV = Path(__file__).resolve().parents[1] / "sample_data" / "sample_library.csv"
MAX_TRACKS = 50_000  # a 23,000-song library draws in about half a minute on a 4-core CPU


class MapRequest(BaseModel):
    csv_path: Optional[str] = Field(None, description="Server path from /upload/csv. Leave empty with sample=true.")
    sample: bool = Field(False, description="Use the bundled sample library instead of an upload.")
    share_id: Optional[str] = Field(None, description="Use the library behind a shared map.")
    neighbors: int = Field(4, ge=1, le=15, description="Links drawn from each track to its closest matches.")
    clusters: Optional[int] = Field(None, ge=1, le=40, description="Fixed number of groups; empty picks one.")
    weights: Dict[str, float] = Field(
        default_factory=dict,
        description="How much each aspect shapes the map: key, tempo, genre, mood, artist, era, sound (0-2).",
    )


@router.post("/build")
async def build(req: MapRequest, voter: Optional[str] = Depends(listener)) -> dict:
    """Build a 3D taste map from a CSV of tracks. Fast enough to run inline.

    Song stats listeners agreed on (and your own corrections) replace the file's."""
    path = _library(req)
    try:
        df = pd.read_csv(path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Couldn't read that CSV: {e}")
    if len(df) > MAX_TRACKS:
        raise HTTPException(status_code=400, detail=f"Maps are limited to {MAX_TRACKS:,} tracks for now.")
    df, corrected = await run_in_threadpool(community.apply, df, voter)

    opts = MapOptions(
        neighbors=req.neighbors,
        clusters=req.clusters,
        weights={k: max(0.0, min(2.0, float(v))) for k, v in req.weights.items()},
    )
    try:
        result = await run_in_threadpool(build_map, df, opts)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    result["meta"]["source"] = "sample" if req.sample else "shared map" if req.share_id else path.name
    result["meta"]["community_corrected"] = corrected
    return result


def _library(req) -> Path:
    """The CSV a request is about: the sample, a shared map's songs, or an uploaded file."""
    if req.sample:
        return SAMPLE_CSV
    if getattr(req, "share_id", None):
        path = map_share.library_path(req.share_id)
        if not path:
            raise HTTPException(status_code=404, detail="This shared map has no song list to work from.")
        return path
    if not req.csv_path:
        raise HTTPException(status_code=400, detail="Send csv_path, share_id, or sample=true.")
    path = Path(req.csv_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"CSV file not found: {path}")
    return path


def warm_up() -> None:
    """UMAP compiles itself on first use (~10s, and another ~20s the first time it sees more
    than 4,096 songs, when it switches to its approximate neighbour search). Do both at
    startup, not on the first click."""
    try:
        build_map(pd.read_csv(SAMPLE_CSV), MapOptions())
        import numpy as np
        import umap

        x = np.random.default_rng(0).normal(size=(4200, 8)).astype(np.float32)
        umap.UMAP(n_components=3, n_epochs=5, random_state=42).fit_transform(x)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Import from Spotify / Apple Music exports
# ---------------------------------------------------------------------------

import threading  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402
from typing import List  # noqa: E402

from fastapi import File, Form, UploadFile  # noqa: E402

from app.core import library_import, sound  # noqa: E402
from app.core.config import settings  # noqa: E402

_imports: Dict[str, "ImportJob"] = {}

# Until a few songs have been timed: a new song costs a Deezer search, a preview download and
# analysis (~1-2 s) plus a MusicBrainz request for a new artist (1 s); a cached one costs ~nothing.
NEW_SONG_S = 0.5  # per song, with several lookups running at once
CACHED_SONG_S = 0.02
LISTEN_SONG_S = 1.5  # one preview fetched and run through CLAP (cached songs are near-instant)


class ImportJob:
    """An import's state, with progress and time left worked out from measured timings.

    The bar is time-based (time spent / (time spent + time left)) rather than "songs
    done / songs", because a cached song takes milliseconds and a new one a few seconds,
    and drawing a big map can take longer than all the cached lookups together."""

    def __init__(self, detected: List[dict], enrich: bool):
        self.id = uuid.uuid4().hex
        self.detected = detected
        self.enrich = enrich
        self.status = "running"
        self.error: Optional[str] = None
        self.warning: Optional[str] = None
        self.result: Optional[dict] = None
        self.songs = sum(d["songs"] for d in detected)
        self.started = time.monotonic()
        self.finished: Optional[float] = None
        self.step = "merge"
        self.draw_detail = ""
        self.lookup = {"needed": 0, "todo": 0, "cached": 0, "done": 0, "done_cached": 0,
                       "found": 0, "not_found": 0, "failed": 0, "skipped": 0}
        self.lookup_planned = not enrich
        self.new_times: List[float] = []
        self.cached_times: List[float] = []
        self.listen = {"todo": 0, "done": 0, "have": 0}
        self.listening = False
        self.skip_listen = False  # set by POST /import/{id}/skip-listen
        self.listen_times: List[float] = []
        self._listen_last = 0.0
        self.draw_started: Optional[float] = None
        self.draw_estimate = 0.0
        self.last_progress = 0

    # ---- called from the worker thread ---------------------------------------------
    def on_start(self, plan: dict) -> None:
        self.lookup.update(needed=plan["needed"], todo=plan["todo"], cached=plan["cached"],
                           skipped=plan["needed"] - plan["todo"])
        self.lookup_planned = True

    def on_song(self, r: dict) -> None:
        if r.get("gave_up"):
            self.lookup["skipped"] += r["skipped"]
            self.lookup["todo"] -= r["skipped"]
            self.warning = ("Couldn't reach the online music databases, so songs weren't looked up. "
                            "Check the internet connection and import again.")
            return
        lk = self.lookup
        lk["done"] += 1
        lk["done_cached"] += r["cached"]
        lk["failed" if r["error"] else "found" if r["found"] else "not_found"] += 1
        (self.cached_times if r["cached"] else self.new_times).append(r["seconds"])

    def start_listening(self) -> None:
        self.step = "listen"
        self.listening = True
        self._listen_last = time.monotonic()

    def on_listen(self, n: int, total: int) -> None:
        now = time.monotonic()
        self.listen_times.append(now - self._listen_last)
        self._listen_last = now
        self.listen.update(done=n, todo=total)

    def start_drawing(self, n: int) -> None:
        self.step = "draw"
        self.songs = n
        self.draw_started = time.monotonic()
        self.draw_estimate = estimate_build_seconds(n)

    # ---- time left -------------------------------------------------------------------
    @staticmethod
    def _avg(times: List[float], default: float) -> float:
        recent = times[-30:]
        # Blend in the default until there are a few measurements to go on
        return (sum(recent) + default * max(0, 3 - len(recent))) / max(len(recent), 3)

    def _lookup_left(self) -> float:
        lk = self.lookup
        new_left = max(lk["todo"] - lk["cached"] - (lk["done"] - lk["done_cached"]), 0)
        cached_left = max(lk["cached"] - lk["done_cached"], 0)
        return new_left * self._avg(self.new_times, NEW_SONG_S) + cached_left * self._avg(self.cached_times, CACHED_SONG_S)

    def time_left(self) -> Optional[float]:
        now = time.monotonic()
        if self.step == "draw":
            left = self.draw_estimate - (now - (self.draw_started or now))
            return max(left, 0.0)
        if self.enrich and not self.lookup_planned:
            return None  # still counting what needs looking up
        listen_left = 0.0
        if self.listening and not self.skip_listen:
            listen_left = max(self.listen["todo"] - self.listen["done"], 0) * self._avg(self.listen_times, LISTEN_SONG_S)
        lookup_left = self._lookup_left() if self.enrich and self.step != "listen" else 0.0
        return lookup_left + listen_left + estimate_build_seconds(self.songs)

    def view(self) -> dict:
        now = self.finished or time.monotonic()
        elapsed = now - self.started
        left = None if self.status != "running" else self.time_left()
        if self.status == "done":
            progress = 100
        elif left is None:
            progress = self.last_progress
        else:
            # Past the estimate while drawing: creep towards 99% instead of sitting still or lying
            progress = int(min(99, 100 * elapsed / max(elapsed + left, 1e-6)))
            if self.step == "draw" and left == 0:
                progress = 99
        progress = self.last_progress = max(progress, self.last_progress)

        lk = self.lookup
        steps = [{"key": "read", "label": "Read your files", "state": "done",
                  "detail": f"{sum(d['songs'] for d in self.detected):,} songs"}]
        if self.enrich:
            if self.step == "merge":
                state, detail = "active", "Checking which songs need looking up…"
            elif self.step == "lookup":
                state = "active"
                detail = f"{lk['done']:,} of {lk['todo']:,} songs"
            else:
                state = "done"
                detail = f"{lk['found']:,} found, {lk['not_found']:,} not found" + \
                         (f", {lk['failed']:,} failed" if lk["failed"] else "")
            steps.append({"key": "lookup", "label": "Look songs up online", "state": state, "detail": detail})
        if self.listening:
            ls = self.listen
            state = "active" if self.step == "listen" else "done"
            detail = f"{ls['done']:,} of {ls['todo']:,} songs" if state == "active" else \
                f"{ls['have']:,} songs have a sound description" + (" (skipped the rest)" if self.skip_listen else "")
            if state == "active" and self.skip_listen:
                detail = "Skipping…"
            steps.append({"key": "listen", "label": "Listen to previews", "state": state, "detail": detail,
                          "skippable": state == "active" and not self.skip_listen})
        draw_state = "done" if self.status == "done" else "active" if self.step == "draw" else "waiting"
        steps.append({"key": "draw", "label": "Draw your map", "state": draw_state,
                      "detail": self.draw_detail if draw_state == "active" else
                      f"{self.songs:,} songs" if draw_state == "done" else ""})

        active = next((s for s in steps if s["state"] == "active"), None)
        if self.status == "error":
            message = "Import failed"
        elif self.status == "done":
            message = "Done"
        elif self.step == "lookup":
            message = f"Looking up songs online… {lk['done']:,} of {lk['todo']:,}"
        elif self.step == "listen":
            message = f"Listening to previews… {self.listen['done']:,} of {self.listen['todo']:,}"
        elif self.step == "draw":
            message = "Drawing your map… almost done" if left == 0 else \
                f"Drawing your map: {self.draw_detail.lower()}…" if self.draw_detail else "Drawing your map…"
        else:
            message = active["detail"] if active else "Working…"
        return {
            "id": self.id, "status": self.status, "progress": progress, "message": message,
            "eta_s": None if left is None else round(left, 1), "elapsed_s": round(elapsed, 1),
            "steps": steps, "lookup": lk if self.enrich else None, "warning": self.warning,
            "detected": self.detected, "songs": self.songs, "error": self.error, "result": self.result,
        }


@router.post("/import")
async def import_library(
    files: List[UploadFile] = File(..., description="Spotify / Apple Music exports or CSVs; several at once is fine."),
    enrich: bool = Form(True, description="Look songs up online (genre from Last.fm/MusicBrainz tags, year from Deezer) and analyse 30 s previews for tempo/key/energy."),
    listen: bool = Form(True, description="Also run each preview through CLAP for a 'sound' description (the slow 'Listen to previews' step). Needs enrich and the CLAP service."),
    limit: int = Form(1500, ge=1, le=50_000),
    listen_limit: Optional[int] = Form(None, ge=1, le=50_000, description="Listen to at most this many previews (most-played songs first). Defaults to `limit`."),
    voter: Optional[str] = Depends(listener),
) -> dict:
    parsed, detected = [], []
    for f in files:
        data = await f.read()
        try:
            df, label = library_import.parse_file(f.filename or "upload", data)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Couldn't read {f.filename}: {e}")
        parsed.append(df)
        detected.append({"file": f.filename, "type": label, "songs": int(len(df))})

    job = ImportJob(detected, enrich)
    _imports[job.id] = job

    def work() -> None:
        try:
            df = library_import.merge(parsed)
            job.songs = int(len(df))
            found = None
            # Sound vectors need the CLAP service; without it the map uses tags and features only
            listening = listen and enrich and sound.available()
            if enrich:
                def on_start(plan):
                    job.on_start(plan)
                    job.step = "lookup"
                df, found = library_import.enrich(df, limit=limit, on_start=on_start, on_song=job.on_song)
            if listening:
                job.start_listening()
                try:
                    df, job.listen["have"] = sound.add_sound(df, limit=min(listen_limit or limit, limit), progress=job.on_listen,
                                                             stop=lambda: job.skip_listen)
                except RuntimeError as e:  # the service stopped mid-import: carry on without sound
                    job.warning = f"Songs weren't given a sound description: {e}"
            out = settings.PROCESSED_DIR / "library"
            out.mkdir(parents=True, exist_ok=True)
            csv_path = out / f"library_{job.id[:8]}.csv"
            df.to_csv(csv_path, index=False)
            # Listeners' corrections go on the drawing, not into the saved file, so taking
            # one back (or new agreement) shows up on the next Remap
            df, corrected = community.apply(df, voter)
            # Columns nobody filled in would otherwise look like (empty) data
            df = df.dropna(axis=1, how="all")
            job.start_drawing(len(df))

            def step(name):
                job.draw_detail = name

            result = build_map(df, MapOptions(), progress=step)
            result["meta"]["source"] = ", ".join(d["type"] for d in detected)
            result["meta"]["library_csv"] = str(csv_path)
            result["meta"]["community_corrected"] = corrected
            if found is not None:
                result["meta"]["matched_online"] = found
            job.result = result
            job.status = "done"
        except Exception as e:
            job.error = str(e)
            job.status = "error"
        finally:
            job.finished = time.monotonic()

    threading.Thread(target=work, daemon=True).start()
    return {k: v for k, v in job.view().items() if k != "result"}


@router.get("/import/{job_id}")
def import_status(job_id: str) -> dict:
    job = _imports.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="This import is no longer running (the server may have restarted). Please import again.")
    view = job.view()
    if view["status"] != "done":
        view.pop("result")
    return view


@router.post("/import/{job_id}/skip-listen")
def skip_listen(job_id: str) -> dict:
    """Stop the "Listen to previews" step early and draw the map with the songs heard so far."""
    job = _imports.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="This import is no longer running (the server may have restarted). Please import again.")
    job.skip_listen = True
    return {k: v for k, v in job.view().items() if k != "result"}


@router.get("/estimate")
def estimate(tracks: int) -> dict:
    """Roughly how long drawing a map of `tracks` songs takes on this machine."""
    return {"seconds": round(estimate_build_seconds(max(tracks, 1)), 1)}


# ---------------------------------------------------------------------------
# Describe-a-vibe search over the songs' sound vectors
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    csv_path: Optional[str] = Field(None, description="The map's library CSV (meta.library_csv or the uploaded path).")
    sample: bool = False
    share_id: Optional[str] = None
    query: str = Field(..., min_length=1, max_length=200, description='What it should sound like, e.g. "sad slow piano".')
    limit: int = Field(20, ge=1, le=100)


@router.post("/search")
async def search_sound(req: SearchRequest) -> dict:
    """Songs whose sound best matches a description. Needs a library imported with the CLAP service running."""
    path = _library(req)
    df = pd.read_csv(path).dropna(how="all").reset_index(drop=True)  # same rows, same ids as /build
    if sound.matrix(df) is None:
        raise HTTPException(status_code=400, detail="This library has no sound data yet. Import it again with the CLAP service running.")
    try:
        results = await run_in_threadpool(sound.search, df, req.query.strip(), req.limit)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"query": req.query, "results": results}


# ---------------------------------------------------------------------------
# "Songs you may like" for a clicked track
# ---------------------------------------------------------------------------

class LikeRequest(BaseModel):
    csv_path: Optional[str] = Field(None, description="The map's library CSV (meta.library_csv or the uploaded path).")
    sample: bool = False
    share_id: Optional[str] = None
    id: int = Field(..., ge=0, description="The clicked track's id from /build.")
    weights: Dict[str, float] = Field(default_factory=dict, description="The same slider weights used for the map.")
    limit: int = Field(8, ge=1, le=30)


@router.post("/like")
async def like(req: LikeRequest, voter: Optional[str] = Depends(listener)) -> dict:
    """Songs from the same library that someone who likes this track may like."""
    path = _library(req)
    df, _ = community.apply(pd.read_csv(path), voter)  # the same stats the map was drawn with
    opts = MapOptions(weights={k: max(0.0, min(2.0, float(v))) for k, v in req.weights.items()})
    try:
        return await run_in_threadpool(similar_tracks, df, req.id, opts, req.limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Sharing a map
# ---------------------------------------------------------------------------

class ShareRequest(BaseModel):
    map: Dict = Field(..., description="The map as /map/build or an import returned it.")
    title: str = Field(..., min_length=1, max_length=80)
    by: Optional[str] = Field(None, max_length=40, description="Name shown on the share; empty for anonymous.")
    listed: bool = Field(False, description="Show it on the public list of shared maps (/maps).")
    include_listening: bool = Field(True, description="Keep play counts, likes and the stats built on them.")
    weights: Dict[str, float] = Field(default_factory=dict, description="The slider weights the map was drawn with.")
    csv_path: Optional[str] = Field(None, description="The map's library CSV, so visitors can Remap and play radio.")
    sample: bool = False
    share_id: Optional[str] = Field(None, description="Re-sharing a shared map: copy its library.")


def _shareable_library(req: ShareRequest) -> Optional[Path]:
    """Only the sample, another share, or a file SuperMusic itself wrote can go into a share,
    so a crafted csv_path can't publish some other file from the server."""
    if req.sample:
        return SAMPLE_CSV
    if req.share_id:
        return map_share.library_path(req.share_id)
    if req.csv_path:
        path = Path(req.csv_path).resolve()
        if path.suffix.lower() == ".csv" and path.is_file() and any(path.is_relative_to(r) for r in _library_roots()):
            return path
    return None


def _library_roots() -> List[Path]:
    """Where SuperMusic writes CSVs: imports, uploads and CSV enrichment results."""
    from app.routes.upload import UPLOAD_DIR
    from app.utils.storage import _ARTIFACT_DIR

    return [p.resolve() for p in (settings.DATA_DIR, settings.PROCESSED_DIR, UPLOAD_DIR, _ARTIFACT_DIR)]


@router.post("/share")
async def share_map(req: ShareRequest) -> dict:
    """Save a snapshot of a map under a short link. Returns the id and a secret delete token."""
    tracks = req.map.get("tracks")
    if isinstance(tracks, list) and len(tracks) > MAX_TRACKS:
        raise HTTPException(status_code=400, detail=f"Maps are limited to {MAX_TRACKS:,} tracks.")
    result = dict(req.map)
    result["meta"] = {**(result.get("meta") or {}),
                      "weights": {k: max(0.0, min(2.0, float(v))) for k, v in req.weights.items()}}
    try:
        return await run_in_threadpool(
            map_share.create, result, title=req.title.strip(), by=(req.by or "").strip() or None,
            listed=req.listed, include_listening=req.include_listening, library=_shareable_library(req))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/shared")
async def shared_maps(limit: int = 50, sort: str = "top", voter: Optional[str] = Depends(listener)) -> dict:
    """Maps people chose to list publicly, with a picture, showcase stats and upvotes.
    sort=top (most upvoted first) or sort=new."""
    return {"maps": await run_in_threadpool(map_share.list_public, max(1, min(limit, 200)),
                                            "new" if sort == "new" else "top", voter)}


@router.get("/shared/{share_id}")
async def shared_map(share_id: str, voter: Optional[str] = Depends(listener)) -> dict:
    found = await run_in_threadpool(map_share.get, share_id)
    if not found:
        raise HTTPException(status_code=404, detail="This shared map doesn't exist, or its owner stopped sharing it.")
    found.update(map_share.votes([share_id], voter)[share_id])
    return found


@router.get("/shared/{share_id}/picture.png")
async def shared_map_picture(share_id: str):
    """A picture of the map, made when it was shared."""
    from fastapi.responses import FileResponse

    path = await run_in_threadpool(map_share.picture_path, share_id)
    if not path:
        raise HTTPException(status_code=404, detail="No picture for this map.")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


class MapVoteRequest(BaseModel):
    up: bool = Field(True, description="true to upvote, false to take the upvote back")


@router.post("/shared/{share_id}/vote")
async def vote_shared_map(share_id: str, req: MapVoteRequest, request: Request,
                          voter: Optional[str] = Depends(listener)) -> dict:
    """Upvote a shared map, once per listener (signed in, or this browser)."""
    if not voter:
        raise HTTPException(status_code=400, detail="Send an X-Listener-Id header or sign in to upvote.")
    try:
        return await run_in_threadpool(map_share.vote, share_id, voter, community.ip_hash(client_ip(request)), req.up)
    except LookupError:
        raise HTTPException(status_code=404, detail="This shared map doesn't exist, or its owner stopped sharing it.")
    except map_share.VoteError as e:
        raise HTTPException(status_code=429, detail=str(e))


class UnshareRequest(BaseModel):
    delete_token: str = Field(..., min_length=8, max_length=100)


@router.post("/shared/{share_id}/delete")
def unshare(share_id: str, req: UnshareRequest) -> dict:
    if not map_share.read_meta(share_id):
        raise HTTPException(status_code=404, detail="This shared map is already gone.")
    if not map_share.delete(share_id, req.delete_token):
        raise HTTPException(status_code=403, detail="Only the browser that shared this map can stop sharing it.")
    return {"deleted": share_id}


# ---------------------------------------------------------------------------
# Map Radio: previews to play, and YouTube ids to make a playlist from
# ---------------------------------------------------------------------------

from app.core import listen_links  # noqa: E402


@router.get("/preview")
async def song_preview(title: str, artist: str = "") -> dict:
    """A fresh 30-second preview link for one song, from Deezer."""
    try:
        return await run_in_threadpool(listen_links.preview, artist.strip(), title.strip())
    except Exception as e:  # Deezer down or unreachable
        raise HTTPException(status_code=502, detail=f"Couldn't reach Deezer for a preview: {e}")


class YoutubeSong(BaseModel):
    title: str
    artist: Optional[str] = None
    youtube_url: Optional[str] = None


class YoutubeRequest(BaseModel):
    songs: List[YoutubeSong] = Field(..., min_length=1, max_length=50)


@router.post("/youtube-ids")
async def youtube_ids(req: YoutubeRequest) -> dict:
    """A YouTube video id for each song (None when nothing was found), in the same order.
    Open them as a playlist with https://www.youtube.com/watch_videos?video_ids=a,b,c."""
    try:
        ids = await run_in_threadpool(listen_links.youtube_ids, [s.model_dump() for s in req.songs])
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"ids": ids}


# ---------------------------------------------------------------------------
# Listeners like you
# ---------------------------------------------------------------------------

class TasteMatchRequest(BaseModel):
    csv_path: Optional[str] = None
    sample: bool = False
    share_id: Optional[str] = None
    limit: int = Field(10, ge=1, le=50)


@router.post("/taste-match")
async def taste_match(req: TasteMatchRequest) -> dict:
    """Public shared maps closest to this library (by the artists both play), with songs to try from each."""
    from app.core import taste_match as tm

    df = pd.read_csv(_library(req))
    return {"matches": await run_in_threadpool(tm.matches, df, req.share_id, req.limit)}
