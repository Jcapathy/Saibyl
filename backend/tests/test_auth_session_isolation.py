"""One account's Log Out must not end another account's session.

`get_supabase()` is a process-wide singleton and supabase-auth stores the
session **on the client**: `sign_in_with_password` ends in `_save_session(...)`,
and so does the `_call_refresh_token` behind `refresh_session`. `sign_out()`
takes no argument — it reads `self.get_session()` and hands that token to
`admin.sign_out(token, scope='global')`.

So, with the shared client:

    10:00  Alice logs in    -> the process now holds Alice's session
    10:01  Bob logs in      -> the process now holds Bob's session
    10:02  Alice logs out   -> Bob's refresh tokens are revoked on every
                              device, Bob is dropped at his next /auth/refresh,
                              and Alice's own token is never revoked

And `POST /api/auth/logout` had no auth dependency at all, so an
unauthenticated caller could POST it in a loop and keep signing out whoever
last authenticated. `except Exception: pass` made it silent.

Both halves are pinned here: the token handed to GoTrue is the caller's own,
and login/refresh no longer write into shared state for anything to read.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials

from app.api import auth as auth_api

ALICE = "access-token-of-alice"
BOB = "access-token-of-bob"


class _FakeAdminAPI:
    def __init__(self, revoked: list[tuple[str, str]]) -> None:
        self._revoked = revoked

    def sign_out(self, jwt: str, scope: str = "global") -> None:
        self._revoked.append((jwt, scope))


class _FakeSession:
    """A client that remembers whoever authenticated through it last.

    Exactly the behaviour of the real `SyncGoTrueClient`: this is what made a
    shared instance dangerous.
    """

    def __init__(self, revoked: list[tuple[str, str]]) -> None:
        self.admin = _FakeAdminAPI(revoked)
        self._stored: str | None = None

    def sign_in_with_password(self, credentials: dict):
        self._stored = f"access-token-of-{credentials['email']}"
        return SimpleNamespace(
            session=SimpleNamespace(
                access_token=self._stored, refresh_token="refresh"
            ),
            user=SimpleNamespace(id="user-1"),
        )

    def sign_out(self) -> None:
        # The no-argument form: whatever this client happens to hold.
        if self._stored:
            self.admin.sign_out(self._stored, "global")


@pytest.fixture
def gotrue(monkeypatch):
    """Every `new_auth_client()` call gets its own client, as in production."""
    revoked: list[tuple[str, str]] = []
    built: list[_FakeSession] = []

    def _new():
        session = _FakeSession(revoked)
        built.append(session)
        return SimpleNamespace(auth=session)

    monkeypatch.setattr(auth_api, "new_auth_client", _new)
    monkeypatch.setattr(
        auth_api, "check_rate_limit",
        lambda *_a, **_k: _noop(),
    )
    return revoked, built


async def _noop():
    return None


@pytest.mark.asyncio
async def test_logout_revokes_the_caller_and_only_the_caller(gotrue):
    """The failure verbatim: Alice logs in, Bob logs in, Alice logs out."""
    revoked, _built = gotrue

    await auth_api.login(
        auth_api.LoginRequest(email="alice", password="x"), _request()
    )
    await auth_api.login(
        auth_api.LoginRequest(email="bob", password="x"), _request()
    )

    await auth_api.logout(
        _request(),
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=ALICE),
    )

    assert revoked == [(ALICE, "global")], (
        f"logout revoked somebody else's session: {revoked}"
    )
    assert BOB not in [token for token, _scope in revoked]


@pytest.mark.asyncio
async def test_a_login_does_not_leave_a_session_on_a_shared_client(gotrue):
    """Each request gets its own client, so nothing ambient survives it."""
    _revoked, built = gotrue

    await auth_api.login(
        auth_api.LoginRequest(email="alice", password="x"), _request()
    )
    await auth_api.login(
        auth_api.LoginRequest(email="bob", password="x"), _request()
    )

    assert len(built) == 2, "two logins shared one client"
    assert [c._stored for c in built] == [
        "access-token-of-alice",
        "access-token-of-bob",
    ]


@pytest.mark.asyncio
async def test_a_gotrue_failure_on_logout_is_logged_rather_than_swallowed(
    gotrue, monkeypatch
):
    """`except Exception: pass` is how this stayed invisible."""
    from structlog.testing import capture_logs

    def _broken():
        class _Boom:
            def sign_out(self, *_a, **_k):
                raise ConnectionError("gotrue is gone")

        return SimpleNamespace(auth=SimpleNamespace(admin=_Boom()))

    monkeypatch.setattr(auth_api, "new_auth_client", _broken)

    with capture_logs() as logs:
        result = await auth_api.logout(
            _request(),
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=ALICE),
        )

    assert result == {"message": "Logged out"}
    assert "logout_revoke_failed" in {entry["event"] for entry in logs}


def _code(fn) -> str:
    """A handler's source with its docstring removed.

    These files explain their own history in prose, so a scan over raw source
    matches the sentence describing the defect as readily as the defect. What
    is being asserted is what the function *does*.
    """
    source = inspect.getsource(fn)
    doc = inspect.getdoc(fn)
    if not doc:
        return source
    first = doc.splitlines()[0]
    start = source.find(first)
    if start == -1:
        return source
    close = source.find('"""', start)
    return source[:start] + (source[close:] if close != -1 else "")


def _security_schemes(dependant) -> set[str]:
    """Every security scheme on a route, including ones nested in dependencies."""
    found = {
        type(d._security_scheme).__name__ for d in dependant._security_dependencies
    }
    for sub in dependant.dependencies:
        found |= _security_schemes(sub)
    return found


def test_logout_cannot_be_called_without_a_bearer_token():
    """The route had no auth dependency at all, so anyone could drive it."""
    from app.main import create_app

    route = next(
        r for r in create_app().routes
        if isinstance(r, APIRoute) and r.path == "/api/auth/logout"
    )

    assert "HTTPBearer" in _security_schemes(route.dependant), (
        "POST /api/auth/logout accepts unauthenticated callers"
    )


def test_no_auth_route_signs_a_user_into_the_shared_client():
    """The singleton is fine for reads; it must never hold a session.

    `get_supabase()` is process-wide, and every call that authenticates through
    it leaves its session there for the next request to find. Scanned rather
    than reviewed, because the defect is invisible at the call site — the line
    reads `supabase.auth.sign_in_with_password(...)` either way.
    """
    for handler in ("login", "refresh", "logout"):
        assert "get_supabase()" not in _code(getattr(auth_api, handler)), (
            f"{handler} authenticates through the shared singleton"
        )
    assert "new_auth_client" in inspect.getsource(auth_api)


def test_sign_out_is_never_called_without_a_token():
    """The no-argument form is the bug. It reads ambient state by design."""
    body = _code(auth_api.logout)

    assert "auth.sign_out()" not in body, (
        "logout revokes whatever session the client happens to hold"
    )
    assert "admin.sign_out(credentials.credentials" in body


def _request(ip: str = "203.0.113.5"):
    return SimpleNamespace(headers={}, client=SimpleNamespace(host=ip))
