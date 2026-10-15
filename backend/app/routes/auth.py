from __future__ import annotations

import time
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
import bcrypt

from ..middleware.auth import create_access_token, require_auth
from app.core import store

router = APIRouter(prefix="/auth", tags=["auth"])

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=72)
    email: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


def _get_user(username: str) -> Optional[dict]:
    row = store.connect().execute(
        "SELECT username, hashed_password, email FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash."""
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def get_password_hash(password: str) -> str:
    """Hash password."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


@router.post("/register")
async def register(user: UserRegister):
    """Register a new user."""
    hashed_password = get_password_hash(user.password)
    cur = store.connect().execute(
        "INSERT OR IGNORE INTO users (username, hashed_password, email, created_at) VALUES (?, ?, ?, ?)",
        (user.username, hashed_password, user.email, time.time()))
    if cur.rowcount == 0:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    access_token = create_access_token({"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login")
async def login(user: UserLogin):
    """Login and get access token."""
    stored_user = _get_user(user.username)
    if not stored_user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(user.password, stored_user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = create_access_token({"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me")
async def get_current_user(payload: dict = Depends(require_auth)):
    """Get current user info."""
    username = payload.get("sub")
    user = _get_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    del user["hashed_password"]
    return user

