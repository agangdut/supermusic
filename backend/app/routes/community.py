from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from app.core import community
from app.middleware.auth import security, verify_token

router = APIRouter(prefix="/community", tags=["community"])


def listener(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Optional[str]:
    """Who is asking: their account when signed in, otherwise the browser's random listener id
    (the X-Listener-Id header). None when neither is sent."""
    payload = verify_token(credentials)
    return community.voter_id(payload.get("sub") if payload else None, request.headers.get("x-listener-id"))


def client_ip(request: Request) -> Optional[str]:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else None)


@router.get("/song")
async def song(artist: str = "", title: str = "", voter: Optional[str] = Depends(listener)) -> dict:
    """A song's stats: what the lookup found, what listeners agreed on, and your own edits."""
    if not title.strip():
        raise HTTPException(status_code=400, detail="Send a title.")
    return await run_in_threadpool(community.song_view, artist, title, voter)


class VoteRequest(BaseModel):
    artist: str = Field("", max_length=300)
    title: str = Field(..., min_length=1, max_length=300)
    field: str = Field(..., description="bpm, key, year, genre, energy, danceability, valence, acousticness or vibes")
    value: Any = Field(None, description="Your answer; null takes your earlier answer back.")


@router.post("/vote")
async def vote(req: VoteRequest, request: Request, voter: Optional[str] = Depends(listener)) -> dict:
    """Correct one stat of one song. It changes your map now, and everyone's once another listener agrees."""
    if not voter:
        raise HTTPException(status_code=400, detail="Send an X-Listener-Id header or sign in to edit songs.")
    try:
        saved = await run_in_threadpool(community.vote, req.artist, req.title, req.field, req.value,
                                        voter, community.ip_hash(client_ip(request)))
    except community.VoteError as e:
        raise HTTPException(status_code=400, detail=str(e))
    view = await run_in_threadpool(community.song_view, req.artist, req.title, voter)
    return {"saved": saved, **view}


@router.get("/activity")
async def activity(limit: int = 30) -> dict:
    """The latest song edits from everyone, and totals."""
    return await run_in_threadpool(community.activity, max(1, min(100, limit)))
