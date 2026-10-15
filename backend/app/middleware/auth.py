from __future__ import annotations

import os
import time
from typing import Optional
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

# JWT configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"

security = HTTPBearer(auto_error=False)


TOKEN_DAYS = 30


def create_access_token(data: dict) -> str:
    """Create JWT access token (valid for TOKEN_DAYS days)."""
    return jwt.encode({**data, "exp": int(time.time()) + TOKEN_DAYS * 86400}, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)) -> Optional[dict]:
    """Verify JWT token."""
    if credentials is None:
        return None
    
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def require_auth(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)) -> dict:
    """Require authentication - raises 401 if not authenticated."""
    payload = verify_token(credentials)
    if payload is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return payload



def current_username(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)) -> Optional[str]:
    """The signed-in account's username, or None."""
    payload = verify_token(credentials)
    return payload.get("sub") if payload else None


def require_username(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)) -> str:
    """The signed-in account's username; 401 when signed out."""
    name = current_username(credentials)
    if not name:
        raise HTTPException(status_code=401, detail="Sign in first.")
    return name
