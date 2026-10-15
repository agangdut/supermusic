from __future__ import annotations

import time
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
import bcrypt

from ..middleware.auth import create_access_token, require_username
from app.core import map_share, social, store

router = APIRouter(prefix="/auth", tags=["auth"])


class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=72)
    email: Optional[str] = None
    display_name: Optional[str] = Field(None, max_length=40)


class UserLogin(BaseModel):
    username: str
    password: str


def _get_user(username: str) -> Optional[dict]:
    row = store.connect().execute(
        "SELECT username, hashed_password, email FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
    return dict(row) if row else None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash."""
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def get_password_hash(password: str) -> str:
    """Hash password."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _session(username: str) -> dict:
    return {"access_token": create_access_token({"sub": username}), "token_type": "bearer",
            "user": social.public_user(social.user_row(username))}


@router.post("/register")
async def register(user: UserRegister):
    """Register a new user. Usernames become profile links (/u/<name>): letters, numbers, . _ - only."""
    if not social.USERNAME_RE.match(user.username):
        raise HTTPException(status_code=400, detail="Usernames can use letters, numbers, dots, dashes and underscores.")
    if _get_user(user.username):
        raise HTTPException(status_code=400, detail="That username is taken.")
    hashed_password = get_password_hash(user.password)
    cur = store.connect().execute(
        "INSERT OR IGNORE INTO users (username, hashed_password, email, created_at, display_name) VALUES (?, ?, ?, ?, ?)",
        (user.username, hashed_password, user.email, time.time(), (user.display_name or "").strip() or None))
    if cur.rowcount == 0:
        raise HTTPException(status_code=400, detail="That username is taken.")
    return _session(user.username)


@router.post("/login")
async def login(user: UserLogin):
    """Login and get access token."""
    stored_user = _get_user(user.username.strip())
    if not stored_user or not verify_password(user.password, stored_user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Wrong username or password.")
    return _session(stored_user["username"])


@router.get("/me")
async def get_current_user(username: str = Depends(require_username)):
    """Get current user info."""
    u = social.user_row(username)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return {**social.public_user(u), "email": u.get("email")}


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = Field(None, max_length=40)
    bio: Optional[str] = Field(None, max_length=280)
    is_artist: Optional[bool] = None


@router.patch("/me")
async def update_me(req: ProfileUpdate, username: str = Depends(require_username)):
    """Change your display name, bio, or whether you're an artist."""
    return social.update_profile(username, req.display_name, req.bio, req.is_artist)


class ClaimRequest(BaseModel):
    shares: List[Dict[str, str]] = Field(..., max_length=200, description="[{id, delete_token}] saved in this browser")


@router.post("/claim-shares")
async def claim_shares(req: ClaimRequest, username: str = Depends(require_username)):
    """Put maps shared from this browser before signing in on your profile."""
    claimed = map_share.claim(username, req.shares)
    return {"claimed": claimed}
