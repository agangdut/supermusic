"""The community atlas, artists' "where does my track land", and the galaxy quiz."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from app.core import jobs
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.core import artist, atlas, checks, games, social
from app.middleware.auth import current_username, require_username
from app.routes.community import listener

router = APIRouter(tags=["atlas"])

MAX_UPLOAD = 40 * 1024 * 1024
AUDIO_SUFFIXES = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".opus"}


# ---- atlas -------------------------------------------------------------------------------

@router.get("/atlas")
async def get_atlas(request: Request) -> Response:
    """One map of every publicly listed library, plus artists' tracks placed on it."""
    tracks = [
        {"id": t["id"], "title": t["title"], "artist": t["artist"], "owner": t["owner"],
         "position": t["position"], "galaxy": t["galaxy"]} for t in artist.public_tracks()]
    raw, gz, tag = await run_in_threadpool(atlas.response_bytes, {"artist_tracks": tracks})
    zipped = "gzip" in request.headers.get("accept-encoding", "").lower()
    etag = f'"{tag}{"-gz" if zipped else ""}"'
    # The browser keeps its copy and asks "still this one?" each visit: unchanged, it
    # gets a tiny "304 Not Modified" instead of the whole atlas again
    headers = {"Vary": "Accept-Encoding", "ETag": etag, "Cache-Control": "no-cache"}
    if etag in request.headers.get("if-none-match", ""):
        return Response(status_code=304, headers=headers)
    if zipped:
        return Response(gz, media_type="application/json", headers={**headers, "Content-Encoding": "gzip"})
    return Response(raw, media_type="application/json", headers=headers)


class MineRequest(BaseModel):
    csv_path: Optional[str] = None
    sample: bool = False
    share_id: Optional[str] = None
    account: bool = Field(False, description="the library saved on your account")


@router.post("/atlas/mine")
async def atlas_mine(req: MineRequest, me: Optional[str] = Depends(current_username)) -> dict:
    """Which atlas stars are songs from this library."""
    from app.routes.map import _library

    if req.account:
        p = (social.user_row(me) or {}).get("library_csv") if me else None
        if not p or not Path(p).is_file():
            raise HTTPException(status_code=404, detail="Import your library on the map first.")
        df = pd.read_csv(p)
    else:
        df = pd.read_csv(_library(req))
    return {"ids": await run_in_threadpool(atlas.mine, df), "songs": len(df)}


@router.get("/atlas/song")
async def atlas_song(song_key: str) -> dict:
    """The public maps a song is on, and the notes pinned to it."""
    return {"maps": atlas.song_maps([song_key]).get(song_key, []), "pins": atlas.pins([song_key])}


@router.get("/atlas/pins")
async def atlas_pins(limit: int = 300) -> dict:
    return {"pins": atlas.pins(limit=max(1, min(limit, 1000)))}


class PinRequest(BaseModel):
    song_key: str = Field(..., min_length=1, max_length=400)
    text: str = Field(..., min_length=1, max_length=atlas.PIN_LENGTH)
    title: Optional[str] = None


@router.post("/atlas/pins", dependencies=[Depends(jobs.rate_limit("pins", 60))])
async def add_pin(req: PinRequest, voter: Optional[str] = Depends(listener),
                  me: Optional[str] = Depends(current_username)) -> dict:
    """Pin a note to a song on the atlas."""
    if not voter:
        raise HTTPException(status_code=400, detail="Sign in or send an X-Listener-Id header to pin notes.")
    try:
        pin = atlas.add_pin(req.song_key, req.text, voter)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if me:
        social.log(me, "pinned", None, {"song_key": req.song_key, "title": req.title, "text": pin["text"]})
    return pin


@router.delete("/atlas/pins/{pin_id}")
async def delete_pin(pin_id: int, voter: Optional[str] = Depends(listener)) -> dict:
    if not voter or not atlas.delete_pin(pin_id, voter):
        raise HTTPException(status_code=403, detail="You can only remove your own notes.")
    return {"deleted": pin_id}


# ---- artists -------------------------------------------------------------------------------

@router.post("/artist/land", dependencies=[Depends(jobs.rate_limit("artist", 10))])
async def land_track(file: UploadFile = File(...), title: str = Form(..., min_length=1, max_length=120),
                     artist_name: Optional[str] = Form(None, max_length=120),
                     genre: Optional[str] = Form(None, max_length=200), public: bool = Form(False),
                     me: Optional[str] = Depends(current_username)) -> dict:
    """Upload a song and see where it lands on the community atlas. The audio isn't kept."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in AUDIO_SUFFIXES:
        raise HTTPException(status_code=400, detail="Upload an audio file (MP3, WAV, FLAC, OGG, M4A).")
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="That file is over 40 MB.")
    try:
        result = await run_in_threadpool(artist.land, data, suffix, title=title, artist=artist_name, genre=genre,
                                         owner=me, public=public)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if me and result["public"]:
        social.log(me, "artist_track", None, {"id": result["id"], "title": title, "galaxy": result["galaxy"]["name"]})
    return result


@router.get("/artist/tracks/{track_id}")
async def get_track(track_id: str, me: Optional[str] = Depends(current_username)) -> dict:
    t = artist.get(track_id)
    if not t or (not t["public"] and t["owner"] != me and t["owner"] is not None):
        raise HTTPException(status_code=404, detail="No such track.")
    return t


class TrackUpdate(BaseModel):
    public: bool


@router.post("/artist/tracks/{track_id}")
async def update_track(track_id: str, req: TrackUpdate, me: str = Depends(require_username)) -> dict:
    if not artist.set_public(track_id, me, req.public):
        raise HTTPException(status_code=403, detail="Only the artist who uploaded it can change it.")
    return artist.get(track_id)


@router.delete("/artist/tracks/{track_id}")
async def delete_track(track_id: str, me: str = Depends(require_username)) -> dict:
    if not artist.delete(track_id, me):
        raise HTTPException(status_code=403, detail="Only the artist who uploaded it can remove it.")
    return {"deleted": track_id}


# ---- games ---------------------------------------------------------------------------------

@router.get("/games/quiz")
async def quiz_question(voter: Optional[str] = Depends(listener)) -> dict:
    if not voter:
        raise HTTPException(status_code=400, detail="Sign in or send an X-Listener-Id header to play.")
    try:
        return await run_in_threadpool(games.question, voter)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/games/quiz/check")
async def quiz_check(voter: Optional[str] = Depends(listener)) -> dict:
    """A bonus "help check" question between quiz rounds (not scored); answering it is a song-stat vote."""
    import random
    import secrets

    return {"question": await run_in_threadpool(checks.quiz_check, voter, random.Random(secrets.randbits(64)))}


class AnswerRequest(BaseModel):
    id: str
    choice: str


@router.post("/games/quiz/answer")
async def quiz_answer(req: AnswerRequest, voter: Optional[str] = Depends(listener)) -> dict:
    try:
        return games.answer(voter or "", req.id, req.choice)
    except LookupError as e:
        raise HTTPException(status_code=410, detail=str(e))


class FinishRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=40)


@router.post("/games/quiz/finish")
async def quiz_finish(req: FinishRequest, voter: Optional[str] = Depends(listener),
                      me: Optional[str] = Depends(current_username)) -> dict:
    name = req.name
    if me and not name:
        name = social.display_names([me]).get(me, me)
    try:
        return games.finish(voter or "", name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
