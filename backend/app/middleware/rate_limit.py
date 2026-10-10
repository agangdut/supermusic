from __future__ import annotations

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request

# Create rate limiter
limiter = Limiter(key_func=get_remote_address)

# Rate limit configurations
RATE_LIMITS = {
    "default": "100/minute",
    "upload": "10/minute",
    "processing": "5/minute",
    "api": "200/hour",
}

