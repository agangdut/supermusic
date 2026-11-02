"""Profiles, follows, the feed, the weekly digest and the leaderboards."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.core import artist, checks, constellations, digest, games, map_share, social
from app.middleware.auth import current_username, require_username
from app.routes.community import listener

router = APIRouter(tags=["people"])


def _profile_user(username: str) -> dict:
    u = social.user_row(username)
    if not u:
        raise HTTPException(status_code=404, detail="No one here by that name.")
    return u


@router.get("/users")
async def search_users(q: str = "", limit: int = 20) -> dict:
    """Find people by username or display name."""
    return {"users": social.search_users(q, max(1, min(limit, 50))) if q.strip() else []}


@router.get("/users/{username}")
async def profile(username: str, viewer: Optional[str] = Depends(current_username),
                  voter: Optional[str] = Depends(listener)) -> dict:
    """A public profile: who they are, their maps, followers, reputation and recent activity."""
    u = _profile_user(username)
    name = u["username"]
    me = viewer == name
    maps = await run_in_threadpool(map_share.by_owner, name, me, voter)
    upvotes = sum(m.get("votes", 0) for m in maps)
    rep = await run_in_threadpool(social.reputation, name, upvotes)
    impact = await run_in_threadpool(checks.impact, f"user:{name}")
    rep = {**rep, "maps_reached": impact["maps_reached"], "settled_this_month": impact["settled_this_month"]}
    return {
        **social.public_user(u),
        "is_me": me,
        **social.follow_counts(name, viewer),
        "maps": maps,
        "reputation": rep,
        "tracks": artist.by_owner(name, include_private=me),
        "activity": [e for e in social.feed_of(name, 20)],
    }


class FollowRequest(BaseModel):
    on: bool = Field(True, description="true to follow, false to unfollow")


@router.post("/users/{username}/follow")
async def follow(username: str, req: FollowRequest, me: str = Depends(require_username)) -> dict:
    try:
        return social.follow(me, _profile_user(username)["username"], req.on)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/users/{username}/{which}")
async def follow_list(username: str, which: str) -> dict:
    if which not in ("followers", "following"):
        raise HTTPException(status_code=404, detail="Not found")
    return {"users": social.follow_list(_profile_user(username)["username"], which)}


@router.get("/feed")
async def feed(before: Optional[float] = None, me: str = Depends(require_username)) -> dict:
    """What people you follow did, and what happened to you. `discover` holds everyone's
    latest public activity, for when you don't follow anyone yet."""
    items = social.feed(me, 50, before)
    return {"items": items, "following": len(social.following(me)),
            "discover": social.recent_public(20) if not before else []}


def _my_library(username: str) -> Optional[pd.DataFrame]:
    u = social.user_row(username) or {}
    p = u.get("library_csv")
    if not p:
        return None
    try:
        return pd.read_csv(p) if Path(p).is_file() else None
    except Exception:
        return None


@router.get("/digest")
async def weekly_digest(me: str = Depends(require_username)) -> dict:
    """This week on your map."""
    df = await run_in_threadpool(_my_library, me)
    return await run_in_threadpool(digest.digest, me, df)


class LibraryRequest(BaseModel):
    csv_path: Optional[str] = None
    share_id: Optional[str] = None
    sample: bool = False
    title: Optional[str] = Field(None, max_length=80)


@router.put("/me/library")
async def set_my_library(req: LibraryRequest, me: str = Depends(require_username)) -> dict:
    """Remember which library is "my map" (used by Compare, the digest and the atlas)."""
    from app.routes.map import SAMPLE_CSV
    from app.utils.safe_paths import CSV, is_user_file

    path: Optional[Path] = None
    if req.sample:
        path = SAMPLE_CSV
    elif req.share_id:
        path = map_share.library_path(req.share_id)
    elif req.csv_path:
        if is_user_file(req.csv_path, CSV):
            path = Path(req.csv_path).resolve()
    if not path:
        raise HTTPException(status_code=400, detail="That library can't be used.")
    social.set_library(me, str(path), req.title)
    return {"ok": True, "has_library": True}


class ConstellationsRequest(BaseModel):
    constellations: list = Field(default_factory=list, description="The whole list; it replaces the saved one.")


@router.get("/me/constellations")
async def my_constellations(me: str = Depends(require_username)) -> dict:
    """Song constellations drawn on your own map, so every device you sign in on shows them."""
    return {"constellations": await run_in_threadpool(constellations.for_user, me)}


@router.put("/me/constellations")
async def save_my_constellations(req: ConstellationsRequest, me: str = Depends(require_username)) -> dict:
    return {"constellations": await run_in_threadpool(constellations.save_for_user, me, req.constellations)}


@router.get("/leaderboards")
async def leaderboards(voter: Optional[str] = Depends(listener)) -> dict:
    """This week's top maps, top contributors, radio charts and quiz scores."""
    maps = await run_in_threadpool(map_share.list_public, 10, "week", voter)
    contributors = await run_in_threadpool(social.top_contributors, map_share.upvotes_by_owner(), 15)
    return {
        "maps": maps,
        "contributors": contributors,
        "radio": games.radio_charts(),
        "quiz": games.quiz_leaders(),
        "checkers": await run_in_threadpool(checks.top_checkers),
    }
