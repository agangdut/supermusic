from __future__ import annotations

import hashlib
import re
import secrets
import time
from typing import Dict, List, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from app.core import jobs
from pydantic import BaseModel, Field
import bcrypt

from ..middleware.auth import create_access_token, require_username
from app.core import admin, mailer, map_share, social, store

router = APIRouter(prefix="/auth", tags=["auth"])

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
RESET_HOURS = 1


def _email(value: Optional[str]) -> Optional[str]:
    """A cleaned email address, None for blank; 400 when it doesn't look like one."""
    value = (value or "").strip()
    if not value:
        return None
    if len(value) > 254 or not EMAIL_RE.match(value):
        raise HTTPException(status_code=400, detail="That email address doesn't look right.")
    return value


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
    if len(plain_password) < 8 or len(plain_password.encode('utf-8')) > 72:
        return False
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def get_password_hash(password: str) -> str:
    """Hash password."""
    if len(password) < 8 or len(password.encode('utf-8')) > 72:
        raise HTTPException(status_code=400, detail="Password must be 8-72 characters.")
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _session(username: str) -> dict:
    return {"access_token": create_access_token({"sub": username}), "token_type": "bearer",
            "user": social.public_user(social.user_row(username))}


@router.post("/register", dependencies=[Depends(jobs.rate_limit("register", 10))])
async def register(user: UserRegister):
    """Register a new user. Usernames become profile links (/u/<name>): letters, numbers, . _ - only."""
    if not social.USERNAME_RE.match(user.username):
        raise HTTPException(status_code=400, detail="Usernames can use letters, numbers, dots, dashes and underscores.")
    if _get_user(user.username):
        raise HTTPException(status_code=400, detail="That username is taken.")
    email = _email(user.email)
    hashed_password = get_password_hash(user.password)
    cur = store.connect().execute(
        "INSERT OR IGNORE INTO users (username, hashed_password, email, created_at, display_name) VALUES (?, ?, ?, ?, ?)",
        (user.username, hashed_password, email, time.time(), (user.display_name or "").strip() or None))
    if cur.rowcount == 0:
        raise HTTPException(status_code=400, detail="That username is taken.")
    return _session(user.username)


@router.post("/login", dependencies=[Depends(jobs.rate_limit("login", 30))])
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
    return {**social.public_user(u), "email": u.get("email"), "is_admin": admin.is_admin(u["username"])}


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = Field(None, max_length=40)
    bio: Optional[str] = Field(None, max_length=280)
    is_artist: Optional[bool] = None


@router.patch("/me")
async def update_me(req: ProfileUpdate, username: str = Depends(require_username)):
    """Change your display name, bio, or whether you're an artist."""
    return social.update_profile(username, req.display_name, req.bio, req.is_artist)


class DeleteRequest(BaseModel):
    password: str = Field(..., max_length=72, description="Your password, to confirm")


@router.post("/me/delete", dependencies=[Depends(jobs.rate_limit("login", 30))])
async def delete_me(req: DeleteRequest, username: str = Depends(require_username)):
    """Delete your account and everything it made (shared maps, votes, follows, pins, tracks)."""
    stored = _get_user(username)
    if not stored or not verify_password(req.password, stored["hashed_password"]):
        raise HTTPException(status_code=401, detail="Wrong password.")
    return social.delete_account(stored["username"])


class ClaimRequest(BaseModel):
    shares: List[Dict[str, str]] = Field(..., max_length=200, description="[{id, delete_token}] saved in this browser")


@router.post("/claim-shares")
async def claim_shares(req: ClaimRequest, username: str = Depends(require_username)):
    """Put maps shared from this browser before signing in on your profile."""
    claimed = map_share.claim(username, req.shares)
    return {"claimed": claimed}


# ---- email and password reset ------------------------------------------------------------

class EmailUpdate(BaseModel):
    email: Optional[str] = Field(None, max_length=254, description="Blank removes it")
    password: str = Field(..., max_length=72, description="Your password, to confirm")


@router.post("/me/email", dependencies=[Depends(jobs.rate_limit("login", 30))])
async def set_email(req: EmailUpdate, username: str = Depends(require_username)):
    """Add, change or remove the email that password reset links go to."""
    stored = _get_user(username)
    if not stored or not verify_password(req.password, stored["hashed_password"]):
        raise HTTPException(status_code=401, detail="Wrong password.")
    email = _email(req.email)
    store.connect().execute("UPDATE users SET email = ? WHERE username = ?", (email, stored["username"]))
    return {"email": email}


@router.get("/reset-available")
async def reset_available():
    """Whether this site can email password reset links."""
    return {"enabled": mailer.can_send()}


class ForgotRequest(BaseModel):
    login: str = Field(..., min_length=1, max_length=254, description="Username or email")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@router.post("/forgot", dependencies=[Depends(jobs.rate_limit("forgot", 5))])
def forgot(req: ForgotRequest, bg: BackgroundTasks):
    """Email a one-time reset link to the account(s) with this username or email.
    The answer is the same (and as quick) whether or not an account matched, so it can't
    be used to find out who has an account: emails go out after the reply."""
    if not mailer.can_send():
        raise HTTPException(status_code=503, detail="This site can't send email yet, so passwords can't be reset.")
    login = req.login.strip()
    rows = store.connect().execute(
        "SELECT username, email FROM users WHERE (username = ? COLLATE NOCASE OR email = ? COLLATE NOCASE) "
        "AND email IS NOT NULL AND email != '' LIMIT 5", (login, login)).fetchall()
    now = time.time()
    for r in rows:
        token = secrets.token_urlsafe(32)
        with store.tx() as c:
            c.execute("DELETE FROM password_resets WHERE username = ? OR expires_at < ?", (r["username"], now))
            c.execute("INSERT INTO password_resets (token_sha256, username, created_at, expires_at) VALUES (?, ?, ?, ?)",
                      (_token_hash(token), r["username"], now, now + RESET_HOURS * 3600))
        link = f"{mailer.site_url()}/reset?token={token}"
        bg.add_task(mailer.send, r["email"], "Reset your SuperMusic password",
                    f"Hi {r['username']},\n\n"
                    f"Someone (hopefully you) asked to reset the password for your SuperMusic account.\n"
                    f"Open this link within {RESET_HOURS} hour to choose a new one:\n\n{link}\n\n"
                    f"If it wasn't you, ignore this email. Your password stays the same.\n")
    return {"sent": True}


class ResetRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=200)
    password: str = Field(..., min_length=8, max_length=72)


@router.post("/reset", dependencies=[Depends(jobs.rate_limit("reset", 20))])
async def reset(req: ResetRequest):
    """Set a new password with the link from the email, and sign in."""
    h = _token_hash(req.token)
    now = time.time()
    with store.tx() as c:
        row = c.execute("SELECT username, expires_at, used_at FROM password_resets WHERE token_sha256 = ?", (h,)).fetchone()
        if not row or row["used_at"] or row["expires_at"] < now:
            raise HTTPException(status_code=400, detail="This reset link has expired or was already used. Ask for a new one.")
        c.execute("UPDATE users SET hashed_password = ? WHERE username = ?", (get_password_hash(req.password), row["username"]))
        c.execute("DELETE FROM password_resets WHERE username = ?", (row["username"],))
    if not _get_user(row["username"]):
        raise HTTPException(status_code=400, detail="This account no longer exists.")
    return _session(row["username"])
