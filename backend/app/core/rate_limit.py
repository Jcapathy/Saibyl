from __future__ import annotations

import redis
from fastapi import HTTPException, Request

from app.core.config import settings


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request, respecting X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def check_rate_limit(
    request: Request,
    key_prefix: str,
    max_attempts: int,
    window_seconds: int,
    fail_open: bool = True,
) -> None:
    """Check rate limit using Redis. Raises 429 if exceeded."""
    ip = _get_client_ip(request)
    cache_key = f"ratelimit:{key_prefix}:{ip}"

    try:
        r = redis.from_url(settings.redis_url)
        current = r.incr(cache_key)
        if current == 1:
            r.expire(cache_key, window_seconds)
        if current > max_attempts:
            raise HTTPException(
                status_code=429,
                detail="Too many attempts. Try again later.",
            )
    except HTTPException:
        raise
    except Exception:
        if not fail_open:
            raise HTTPException(
                status_code=503,
                detail="Service temporarily unavailable",
            )
