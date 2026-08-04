"""IP rate limiting, backed by Redis.

The default is fail-*closed*. A limiter that fails open is not a limiter: the
one condition under which it stops counting — Redis unreachable — is also the
condition an attacker can produce, and the old default turned every backend
error into unlimited login attempts with nothing in the logs to say so. Callers
that genuinely prefer availability to protection must now say so explicitly.
"""
from __future__ import annotations

from functools import lru_cache

import redis
import structlog
from fastapi import HTTPException, Request

from app.core.config import settings

logger = structlog.get_logger()


@lru_cache(maxsize=1)
def _client() -> redis.Redis:
    """One pooled client for the process.

    Built per call, this leaked a connection pool on every request — which
    eventually produced exactly the backend error the limiter used to swallow.
    """
    return redis.from_url(settings.redis_url)


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
    fail_open: bool = False,
) -> None:
    """Check rate limit using Redis. Raises 429 if exceeded.

    Raises 503 if the limit cannot be checked at all, unless `fail_open=True`
    is passed deliberately.
    """
    ip = _get_client_ip(request)
    cache_key = f"ratelimit:{key_prefix}:{ip}"

    try:
        r = _client()
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
        # Never silent: an unenforced limit is a security event, and without
        # this line a brute-force window looks identical to a quiet one.
        logger.exception(
            "rate_limit_backend_unavailable",
            key_prefix=key_prefix,
            client_ip=ip,
            fail_open=fail_open,
        )
        # Drop the possibly-poisoned pool so the next request rebuilds it.
        _client.cache_clear()
        if not fail_open:
            raise HTTPException(
                status_code=503,
                detail="Service temporarily unavailable",
            )
