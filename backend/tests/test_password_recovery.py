"""A locked-out founder must be able to get back in without emailing a human.

**There was no password recovery at all.** Not a broken flow — none: no route,
no email, no token. `LoginPage` offered "Forgot password?" as a `mailto:`, and
Settings → Account said password changes were handled by email. It surfaced on
2026-08-27 when the founder could not get into his own account.

`POST /auth/forgot-password` and `POST /auth/reset-password` close that. What is
pinned here is not that they exist but the four things that make them safe:

1. The answer to "forgot password" never varies with whether the address has an
   account — otherwise the route is a free account-existence oracle.
2. The account acted on is named by the **verified token**, never by the request
   body. A body-supplied user id would let anyone with any valid recovery token
   reset anybody's password.
3. A reset **revokes every other session**. Somebody resetting a password is
   often doing it because they believe somebody else has it; if the attacker's
   refresh token survived, the reset would achieve nothing.
4. A short password is refused before GoTrue is ever asked.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from app.api import auth as auth_api

GOOD_TOKEN = "recovery-jwt-for-dana"  # noqa: S105 - a fake, not a credential
DANA = "user-dana"


class _FakeGoTrue:
    """The anon-client half: sends the mail, and verifies recovery tokens."""

    def __init__(self, sent: list, *, send_raises=False, known_token=GOOD_TOKEN):
        self._sent = sent
        self._send_raises = send_raises
        self._known_token = known_token

    def reset_password_email(self, email: str, options: dict | None = None) -> None:
        if self._send_raises:
            raise RuntimeError("gotrue is down")
        self._sent.append((email, (options or {}).get("redirect_to")))

    def get_user(self, jwt: str):
        if jwt != self._known_token:
            raise RuntimeError("invalid or expired token")
        return SimpleNamespace(user=SimpleNamespace(id=DANA))


class _FakeAdminAPI:
    def __init__(self, updated: list, revoked: list, *, revoke_raises=False):
        self._updated = updated
        self._revoked = revoked
        self._revoke_raises = revoke_raises

    def update_user_by_id(self, uid: str, attributes: dict):
        self._updated.append((uid, attributes))
        return SimpleNamespace(user=SimpleNamespace(id=uid))

    def sign_out(self, jwt: str, scope: str = "global") -> None:
        if self._revoke_raises:
            raise RuntimeError("gotrue refused the revoke")
        self._revoked.append((jwt, scope))


@pytest.fixture
def recovery(monkeypatch):
    """Wire both clients, silence the rate limiter, pin the frontend origin."""
    state = SimpleNamespace(sent=[], updated=[], revoked=[])
    knobs = SimpleNamespace(send_raises=False, revoke_raises=False, known_token=GOOD_TOKEN)

    monkeypatch.setattr(
        auth_api,
        "new_auth_client",
        lambda: SimpleNamespace(
            auth=_FakeGoTrue(
                state.sent,
                send_raises=knobs.send_raises,
                known_token=knobs.known_token,
            )
        ),
    )
    monkeypatch.setattr(
        auth_api,
        "get_supabase_admin",
        lambda: SimpleNamespace(
            auth=SimpleNamespace(
                admin=_FakeAdminAPI(
                    state.updated, state.revoked, revoke_raises=knobs.revoke_raises
                )
            )
        ),
    )
    monkeypatch.setattr(auth_api, "check_rate_limit", lambda *_a, **_k: _noop())
    monkeypatch.setattr(
        auth_api, "settings", SimpleNamespace(frontend_url="https://saibyl.com")
    )
    return state, knobs


async def _noop():
    return None


def _request(ip: str = "203.0.113.5"):
    return SimpleNamespace(headers={}, client=SimpleNamespace(host=ip))


# ── 1. No account enumeration ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_answer_is_the_same_for_an_address_that_has_no_account(recovery):
    """Otherwise this route tells anyone which addresses are registered."""
    _state, _knobs = recovery

    known = await auth_api.forgot_password(
        auth_api.ForgotPasswordRequest(email="dana@example.com"), _request()
    )
    unknown = await auth_api.forgot_password(
        auth_api.ForgotPasswordRequest(email="nobody@example.com"), _request()
    )

    assert known == unknown, "the reply distinguishes real addresses from fake ones"
    assert known["message"] == auth_api.RESET_SENT_MESSAGE


@pytest.mark.asyncio
async def test_a_gotrue_outage_does_not_change_the_answer_either(recovery):
    """A 500 that only fires for real addresses leaks the same fact."""
    _state, knobs = recovery
    knobs.send_raises = True

    reply = await auth_api.forgot_password(
        auth_api.ForgotPasswordRequest(email="dana@example.com"), _request()
    )

    assert reply["message"] == auth_api.RESET_SENT_MESSAGE


@pytest.mark.asyncio
async def test_the_link_comes_back_to_our_own_reset_page(recovery):
    """Without `redirect_to` the link lands on Supabase's default page."""
    state, _knobs = recovery

    await auth_api.forgot_password(
        auth_api.ForgotPasswordRequest(email="dana@example.com"), _request()
    )

    assert state.sent == [("dana@example.com", "https://saibyl.com/reset-password")]


# ── 2. The token names the account, and nothing else does ────────────────────

@pytest.mark.asyncio
async def test_the_account_reset_is_the_one_the_token_belongs_to(recovery):
    """`update_user_by_id` is called with GoTrue's answer, not anything sent."""
    state, _knobs = recovery

    await auth_api.reset_password(
        auth_api.ResetPasswordRequest(access_token=GOOD_TOKEN, password="a-good-password"),
        _request(),
    )

    assert state.updated == [(DANA, {"password": "a-good-password"})]


@pytest.mark.asyncio
async def test_the_request_body_cannot_name_a_user(recovery):
    """The only fields on the wire are the token and the new password.

    If a `user_id` ever appears here, anyone holding any valid recovery token
    could reset any account.
    """
    fields = set(auth_api.ResetPasswordRequest.model_fields)
    assert fields == {"access_token", "password"}, fields


@pytest.mark.asyncio
async def test_an_expired_or_forged_token_changes_nothing(recovery):
    """The refusal is the same sentence for expired, forged and already-used."""
    state, _knobs = recovery

    with pytest.raises(HTTPException) as caught:
        await auth_api.reset_password(
            auth_api.ResetPasswordRequest(
                access_token="not-a-real-token", password="a-good-password"
            ),
            _request(),
        )

    assert caught.value.status_code == 400
    assert "expired" in caught.value.detail
    assert state.updated == [], "a rejected token still changed a password"
    assert state.revoked == []


# ── 3. A reset evicts everyone else ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_reset_revokes_every_other_session(recovery):
    """A reset that leaves the old sessions live has achieved nothing."""
    state, _knobs = recovery

    await auth_api.reset_password(
        auth_api.ResetPasswordRequest(access_token=GOOD_TOKEN, password="a-good-password"),
        _request(),
    )

    assert state.revoked == [(GOOD_TOKEN, "global")]


@pytest.mark.asyncio
async def test_a_failed_revoke_does_not_lose_the_password_change(recovery):
    """The password is already set; failing here would strand the caller."""
    state, knobs = recovery
    knobs.revoke_raises = True

    reply = await auth_api.reset_password(
        auth_api.ResetPasswordRequest(access_token=GOOD_TOKEN, password="a-good-password"),
        _request(),
    )

    assert state.updated == [(DANA, {"password": "a-good-password"})]
    assert "Sign in" in reply["message"]


# ── 4. The password floor is enforced before GoTrue is asked ─────────────────

@pytest.mark.asyncio
async def test_a_short_password_is_refused_without_a_round_trip(recovery):
    state, _knobs = recovery
    too_short = "x" * (auth_api.MIN_PASSWORD_LENGTH - 1)

    with pytest.raises(HTTPException) as caught:
        await auth_api.reset_password(
            auth_api.ResetPasswordRequest(access_token=GOOD_TOKEN, password=too_short),
            _request(),
        )

    assert caught.value.status_code == 400
    assert str(auth_api.MIN_PASSWORD_LENGTH) in caught.value.detail
    assert state.updated == []


# ── 5. Both routes are actually mounted ──────────────────────────────────────

def test_both_routes_are_mounted_as_post():
    """A handler nobody can reach is the same defect as no handler."""
    paths = {
        route.path: route.methods
        for route in auth_api.router.routes
        if isinstance(route, APIRoute)
    }

    assert "/forgot-password" in paths, "the reset request route is not mounted"
    assert "/reset-password" in paths, "the reset completion route is not mounted"
    assert "POST" in paths["/forgot-password"]
    assert "POST" in paths["/reset-password"]


def test_signup_no_longer_sends_a_locked_out_founder_to_a_mailbox():
    """The 409 for an existing address used to say "email info@saidolabs.com".

    That sentence was correct while there was no reset flow. It is now the
    wrong instruction, and the kind that survives for months because nothing
    reads it.
    """
    body = inspect.getsource(auth_api.signup)
    assert "Forgot password?" in body, "the 409 does not point at the reset flow"
    assert "email info@saidolabs.com if you need the password reset" not in body
