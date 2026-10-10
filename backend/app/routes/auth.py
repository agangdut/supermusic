from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from passlib.context import CryptContext

from ..middleware.auth import create_access_token, require_auth

router = APIRouter(prefix="/auth", tags=["auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    email: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


# Simple in-memory user store (replace with database in production)
users_db: dict[str, dict] = {}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash password."""
    return pwd_context.hash(password)


@router.post("/register")
async def register(user: UserRegister):
    """Register a new user."""
    if user.username in users_db:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    hashed_password = get_password_hash(user.password)
    users_db[user.username] = {
        "username": user.username,
        "hashed_password": hashed_password,
        "email": user.email,
    }
    
    access_token = create_access_token({"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login")
async def login(user: UserLogin):
    """Login and get access token."""
    if user.username not in users_db:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    stored_user = users_db[user.username]
    if not verify_password(user.password, stored_user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = create_access_token({"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me")
async def get_current_user(payload: dict = Depends(require_auth)):
    """Get current user info."""
    username = payload.get("sub")
    if username not in users_db:
        raise HTTPException(status_code=404, detail="User not found")
    
    user = users_db[username].copy()
    del user["hashed_password"]
    return user

