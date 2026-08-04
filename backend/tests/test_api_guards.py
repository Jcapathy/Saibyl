"""Tests for the request-path guards: rate limiting, org resolution, SSRF, routing.

Same governing failure as the cost tests — a miss and a legitimate absence
sharing one value. A Redis outage read as "under the limit", an arbitrary row
read as "the user's org", the first of several resolved addresses read as "all
of them", and a static path read as a UUID.
"""
from __future__ import annotations

import inspect
import socket
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from starlette.routing import Match
from structlog.testing import capture_logs

from app.core import auth as core_auth
from app.core import rate_limit, security


def _events(logs) -> set[str]:
    return {entry["event"] for entry in logs}


# ── Rate limiting: the default must be fail-closed ───────

def _request(ip: str = "203.0.113.5"):
    return SimpleNamespace(headers={}, client=SimpleNamespace(host=ip))


class _ClientStub:
    """Stands in for the lru_cached `_client`, including its `cache_clear`."""

    def __init__(self, client):
        self._client = client
        self.cleared = 0

    def __call__(self):
        return self._client

    def cache_clear(self):
        self.cleared += 1


class _DeadRedis:
    def incr(self, _key):
        raise ConnectionError("redis unreachable")


class _CountingRedis:
    def __init__(self, count):
        self.count = count

    def incr(self, _key):
        return self.count

    def expire(self, _key, _seconds):
        return True


def test_rate_limit_defaults_to_fail_closed():
    """All three callers already pass False; the default was the risk.

    A limiter that fails open stops counting under exactly the condition an
    attacker can produce.
    """
    default = inspect.signature(rate_limit.check_rate_limit).parameters["fail_open"].default
    assert default is False


@pytest.mark.asyncio
async def test_a_redis_outage_refuses_the_request_by_default(monkeypatch):
    stub = _ClientStub(_DeadRedis())
    monkeypatch.setattr(rate_limit, "_client", stub)

    with capture_logs() as logs:
        with pytest.raises(HTTPException) as exc:
            await rate_limit.check_rate_limit(_request(), "login", 10, 60)

    assert exc.value.status_code == 503
    assert "rate_limit_backend_unavailable" in _events(logs)
    assert stub.cleared == 1, "a poisoned pool must be dropped, not reused"


@pytest.mark.asyncio
async def test_an_unenforced_limit_is_never_silent(monkeypatch):
    """Even when a caller opts into fail-open, the gap must be in the logs."""
    stub = _ClientStub(_DeadRedis())
    monkeypatch.setattr(rate_limit, "_client", stub)

    with capture_logs() as logs:
        await rate_limit.check_rate_limit(_request(), "login", 10, 60, fail_open=True)

    assert "rate_limit_backend_unavailable" in _events(logs)


@pytest.mark.asyncio
async def test_exceeding_the_limit_still_returns_429(monkeypatch):
    monkeypatch.setattr(rate_limit, "_client", _ClientStub(_CountingRedis(11)))

    with pytest.raises(HTTPException) as exc:
        await rate_limit.check_rate_limit(_request(), "login", 10, 60)

    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_a_request_under_the_limit_passes(monkeypatch):
    monkeypatch.setattr(rate_limit, "_client", _ClientStub(_CountingRedis(1)))

    await rate_limit.check_rate_limit(_request(), "login", 10, 60)


# ── Org resolution must be deterministic ─────────────────

class _RecordingQuery:
    def __init__(self, data, calls):
        self._data = data
        self.calls = calls

    def select(self, *args, **_kwargs):
        self.calls.append(("select", args))
        return self

    def eq(self, *args, **_kwargs):
        self.calls.append(("eq", args))
        return self

    def order(self, *args, **kwargs):
        self.calls.append(("order", args, kwargs))
        return self

    def limit(self, *args, **_kwargs):
        self.calls.append(("limit", args))
        return self

    def execute(self):
        return SimpleNamespace(data=self._data)


@pytest.mark.asyncio
async def test_a_multi_org_user_gets_a_deterministic_org():
    """`.limit(1)` with no `.order()` leaves the row to the query plan, so two
    consecutive requests from one user could answer with different orgs."""
    calls = []
    rows = [{
        "organization_id": "org-a",
        "role": "owner",
        "organizations": {"id": "org-a", "name": "A", "slug": "a", "plan": "free"},
    }]

    class _Admin:
        def table(self, _name):
            return _RecordingQuery(rows, calls)

    original = core_auth.get_supabase_admin
    core_auth.get_supabase_admin = lambda: _Admin()
    try:
        result = await core_auth.get_current_org(user={"id": "user-1", "email": "a@b.c"})
    finally:
        core_auth.get_supabase_admin = original

    ordered_by = [call[1][0] for call in calls if call[0] == "order"]
    assert ordered_by, "the selection must be ordered, or it is arbitrary"
    assert ordered_by[0] == "joined_at"
    assert "organization_id" in ordered_by, "the ordering must be total, not just by timestamp"
    assert result["org_id"] == "org-a"


# ── SSRF: every resolved address, not just the first ─────

def _resolves_to(*addresses):
    def _fake(hostname, *_args, **_kwargs):
        infos = []
        for addr in addresses:
            family = socket.AF_INET6 if ":" in addr else socket.AF_INET
            sockaddr = (addr, 0, 0, 0) if family == socket.AF_INET6 else (addr, 0)
            infos.append((family, socket.SOCK_STREAM, 6, "", sockaddr))
        return infos

    return _fake


def test_a_public_host_is_allowed(monkeypatch):
    monkeypatch.setattr(security.socket, "getaddrinfo", _resolves_to("93.184.216.34"))
    security.validate_external_url("https://example.com/resource/1")


def test_an_ipv4_mapped_loopback_is_rejected(monkeypatch):
    """`::ffff:127.0.0.1` matches none of the v6 private networks and is not an
    IPv4Address, so it walked straight through the old check."""
    monkeypatch.setattr(security.socket, "getaddrinfo", _resolves_to("::ffff:127.0.0.1"))
    with pytest.raises(HTTPException) as exc:
        security.validate_external_url("http://localtest.me/")
    assert exc.value.status_code == 400


def test_an_ipv4_mapped_metadata_address_is_rejected(monkeypatch):
    """The cloud metadata endpoint is the payload this check exists to stop."""
    monkeypatch.setattr(
        security.socket, "getaddrinfo", _resolves_to("::ffff:169.254.169.254")
    )
    with pytest.raises(HTTPException):
        security.validate_external_url("http://metadata.example/")


def test_every_resolved_address_is_checked_not_just_the_first(monkeypatch):
    """getaddrinfo ordering is a system policy, not a guarantee — validating
    `[0]` means the check passes or fails by resolver luck."""
    monkeypatch.setattr(
        security.socket, "getaddrinfo", _resolves_to("93.184.216.34", "127.0.0.1")
    )
    with pytest.raises(HTTPException):
        security.validate_external_url("http://split-horizon.example/")


def test_a_scoped_ipv6_link_local_is_rejected(monkeypatch):
    monkeypatch.setattr(security.socket, "getaddrinfo", _resolves_to("fe80::1%eth0"))
    with pytest.raises(HTTPException) as exc:
        security.validate_external_url("http://link-local.example/")
    assert "private or internal" in exc.value.detail


def test_a_host_that_resolves_to_nothing_is_rejected(monkeypatch):
    monkeypatch.setattr(security.socket, "getaddrinfo", lambda *a, **k: [])
    with pytest.raises(HTTPException):
        security.validate_external_url("http://nowhere.example/")


def test_a_non_http_scheme_is_rejected():
    with pytest.raises(HTTPException):
        security.validate_external_url("file:///etc/passwd")


@pytest.mark.parametrize("addr", ["10.1.2.3", "192.168.1.1", "172.16.0.9", "169.254.169.254", "0.0.0.0"])
def test_private_v4_ranges_stay_rejected(monkeypatch, addr):
    monkeypatch.setattr(security.socket, "getaddrinfo", _resolves_to(addr))
    with pytest.raises(HTTPException):
        security.validate_external_url("http://internal.example/")


# ── Routing: static paths must not be shadowed ───────────

def _resolve_in(routes, method: str, path: str):
    """The endpoint FastAPI would actually dispatch to, in registration order."""
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "path_params": {},
        "root_path": "",
        "headers": [],
    }
    for route in routes:
        match, _child = route.matches(scope)
        if match == Match.FULL:
            return getattr(route.endpoint, "__name__", None)
    return None


def test_no_static_route_anywhere_is_shadowed_by_a_parameterised_one():
    """A scan of the whole app, not a spot check.

    This class has now shipped twice: `GET /simulations/founder-stages` behind
    `GET /simulations/{id}` in V1, and `GET /markets/keys` behind
    `GET /markets/{market_id}`. Both reached Postgres as an invalid UUID cast —
    a 500, not a 404, so it read as a server fault rather than a routing bug.
    Scanning every registered router means the next static path added under a
    parameterised one fails here instead of in production.
    """
    from app.main import create_app

    routes = [r for r in create_app().routes if isinstance(r, APIRoute)]

    shadowed = []
    for route in routes:
        if "{" in route.path:
            continue
        for method in sorted(route.methods):
            if method in ("HEAD", "OPTIONS"):
                continue
            if _resolve_in(routes, method, route.path) != route.endpoint.__name__:
                shadowed.append(f"{method} {route.path}")

    assert not shadowed, f"unreachable static routes: {shadowed}"
