"""IP rate limiting, backed by Redis.

The default is fail-*closed*. A limiter that fails open is not a limiter: the
one condition under which it stops counting — Redis unreachable — is also the
condition an attacker can produce, and the old default turned every backend
error into unlimited login attempts with nothing in the logs to say so. Callers
that genuinely prefer availability to protection must now say so explicitly.
"""
from __future__ import annotations

import ipaddress
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
    """The address this request is counted against.

    **The left-most `X-Forwarded-For` entry is the attacker's half of the
    header, and this used to return it verbatim.** XFF is a list each proxy
    *appends its own peer to*, so the right-most entry is the one written by the
    proxy nearest us — everything to its left is whatever the client typed.
    Reading `split(",")[0]` therefore let any caller choose their own Redis key:
    `X-Forwarded-For: attacker-nonce-0001` came back as
    `'attacker-nonce-0001'` — not even an IP — and a fresh value per request
    bought a fresh 10-attempt budget every time. Login, signup and refresh were
    all keyed this way, so the limits never fired, and signup grants
    `tier_grant('free')` credits to every account it creates.

    So: count `settings.trusted_proxy_hops` in from the right, which is the
    entry our own trusted proxy wrote. Anything that is not a parseable IP
    address, and any header shorter than the number of hops we expect, falls
    back to the socket peer — the one value no client can forge.
    """
    peer = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        return peer

    parts = [part.strip() for part in forwarded.split(",") if part.strip()]
    hops = max(1, settings.trusted_proxy_hops)
    if len(parts) < hops:
        # Fewer entries than proxies means the chain is not the one this
        # deployment was configured for; the peer is the only address left that
        # nobody upstream could have written.
        logger.warning(
            "rate_limit_forwarded_for_too_short",
            entries=len(parts), trusted_proxy_hops=hops,
        )
        return peer

    candidate = parts[-hops]
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        logger.warning("rate_limit_forwarded_for_not_an_ip", trusted_proxy_hops=hops)
        return peer
    return candidate


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
