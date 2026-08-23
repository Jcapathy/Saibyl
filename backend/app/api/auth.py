from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from app.core.auth import get_current_org, get_current_user, security
from app.core.database import get_supabase_admin, new_auth_client
from app.core.rate_limit import check_rate_limit
from app.services.billing.agent_pricing import tier_grant

# This module imported no logger at all, so all five handlers were silent by
# construction — a Supabase outage read as every user typing a bad password.
log = structlog.get_logger()

# What a new account starts on. Explicit rather than relying on the column
# default, because the credit grant is derived from it and the two must agree.
DEFAULT_SIGNUP_PLAN = "free"

router = APIRouter(tags=["auth"])


class SignupRequest(BaseModel):
    email: str
    password: str
    org_name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    """The refresh token, in the body — never in the URL.

    It was a bare `str` parameter, which FastAPI reads as a **query
    parameter**: the live request was
    `POST /api/auth/refresh?refresh_token=<token>`, and the generated OpenAPI
    said so (`"in": "query"`, no requestBody). A Supabase refresh token mints
    new access tokens for the life of the session — it is a full account
    credential — and a query string is written verbatim into Render's request
    logs, any proxy log in between, Sentry breadcrumbs, and the browser's own
    history. Anyone who could read a log could resume anyone's session.
    """

    refresh_token: str


@router.post("/signup")
async def signup(body: SignupRequest, request: Request):
    """Create a new user, organization, and link them."""
    await check_rate_limit(request, "signup", max_attempts=5, window_seconds=300, fail_open=False)
    admin = get_supabase_admin()

    # Create user via Supabase Admin Auth (auto-confirms email)
    try:
        auth_result = admin.auth.admin.create_user({
            "email": body.email,
            "password": body.password,
            "email_confirm": True,
        })
        user = auth_result.user
        if not user:
            raise HTTPException(400, "Signup failed")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Signup failed")

    # Create organization
    import secrets
    slug = body.org_name.lower().replace(" ", "-")[:50] + "-" + secrets.token_hex(3)
    # `plan` and the credit grant are set explicitly, not left to defaults.
    #
    # **Without this every new account was dead on arrival.** The org was created
    # with name and slug only, `organizations.credits_balance` defaults to 0, and
    # `check_credit_budget` compares the balance against the run's cost — so the
    # first thing a new user ever did returned
    # "Not enough credits. This run needs 1,180; you have 0."
    #
    # The `grant_credits` RPC exists for exactly this and had **zero callers**
    # anywhere in the codebase. The free grant is sized so it covers one free run
    # (`test_the_free_grant_covers_one_free_run`), which is worth nothing if
    # nobody is ever given it.
    org = admin.table("organizations").insert({
        "name": body.org_name,
        "slug": slug,
        "plan": DEFAULT_SIGNUP_PLAN,
    }).execute().data[0]

    granted = tier_grant(DEFAULT_SIGNUP_PLAN)
    try:
        admin.rpc("grant_credits", {
            "org_uuid": org["id"],
            "amount": granted,
        }).execute()
    except Exception:
        # Loud, and not fatal: the account exists and is recoverable by granting
        # credits manually. Silently leaving it at zero is what produced a
        # signup that could never run anything.
        log.exception(
            "signup_credit_grant_failed",
            org_id=org["id"],
            plan=DEFAULT_SIGNUP_PLAN,
            amount=granted,
        )
    else:
        log.info(
            "signup_credits_granted",
            org_id=org["id"],
            plan=DEFAULT_SIGNUP_PLAN,
            amount=granted,
        )

    # Link user as owner
    admin.table("organization_members").insert({
        "organization_id": org["id"],
        "user_id": user.id,
        "role": "owner",
    }).execute()

    # Update user profile
    admin.table("user_profiles").update({
        "default_organization_id": org["id"],
    }).eq("id", user.id).execute()

    return {"user_id": user.id, "organization_id": org["id"], "email": body.email}


@router.post("/login")
async def login(body: LoginRequest, request: Request):
    """Sign in and return session tokens."""
    await check_rate_limit(request, "login", max_attempts=10, window_seconds=60, fail_open=False)
    # A per-request client, never the shared singleton: `sign_in_with_password`
    # ends in `_save_session`, so every login on the shared object replaced the
    # session the whole process was holding — and `sign_out()` reads exactly
    # that. See `new_auth_client`.
    supabase = new_auth_client()
    try:
        result = supabase.auth.sign_in_with_password({
            "email": body.email,
            "password": body.password,
        })
        return {
            "access_token": result.session.access_token,
            "refresh_token": result.session.refresh_token,
            "user_id": result.user.id,
        }
    except Exception:
        raise HTTPException(401, "Invalid email or password")


@router.post("/logout")
async def logout(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(security),
):
    """Sign out **the caller**, named by the token they present.

    This route revoked whoever had authenticated most recently, and needed no
    credentials to do it.

    `supabase.auth.sign_out()` takes no argument: it reads `self.get_session()`
    and calls `admin.sign_out(that_token, scope='global')`. The client it read
    from is `get_supabase()`, a process-wide singleton that
    `sign_in_with_password` and `refresh_session` both write their session into.
    So Alice logs in at 10:00, Bob at 10:01, Alice presses Log Out — and **Bob's**
    refresh tokens are revoked on every device he owns, dropping him mid-run at
    his next `/auth/refresh`, while Alice's own token is never revoked at all.
    With no auth dependency on the route, an unauthenticated attacker could POST
    here in a loop and keep signing out whoever last logged in; `except
    Exception: pass` made it silent.

    Two changes close it, and both are needed. The token to revoke is now taken
    from the caller's own `Authorization` header and passed to `admin.sign_out`
    explicitly, so this call can only ever end the session it was given. And
    login and refresh no longer write into a shared client at all — see
    `new_auth_client` — so there is no ambient session left for anything to
    read.

    `Security(security)` also means a request with no bearer token is refused
    before any of this runs. A *stale* token is still accepted here on purpose:
    GoTrue simply finds nothing to revoke, and the frontend clears local state
    either way, so there is no value in making log-out fail for someone whose
    session already expired.
    """
    await check_rate_limit(
        request, "logout", max_attempts=20, window_seconds=60, fail_open=True
    )
    try:
        # `admin` here is the GoTrue admin *API surface* on an anon client, not
        # the service-role client — it is the same call the browser SDK makes to
        # end its own session, and it authenticates as the presented token.
        new_auth_client().auth.admin.sign_out(credentials.credentials, "global")
    except Exception:
        # Not fatal, but no longer silent: the caller's tokens are discarded
        # client-side regardless, and a GoTrue that is refusing sign-outs is
        # something we want to be able to find afterwards.
        log.warning("logout_revoke_failed", exc_info=True)
    return {"message": "Logged out"}


@router.post("/refresh")
async def refresh(body: RefreshRequest, request: Request):
    """Refresh session token."""
    await check_rate_limit(request, "refresh", max_attempts=20, window_seconds=60, fail_open=False)
    # A per-request client. `refresh_session` ends in `_save_session`, so on the
    # shared singleton every refresh overwrote the stored session for the whole
    # process — which is the state `sign_out()` used to read.
    supabase = new_auth_client()
    try:
        result = supabase.auth.refresh_session(body.refresh_token)
        return {
            "access_token": result.session.access_token,
            "refresh_token": result.session.refresh_token,
        }
    except Exception:
        raise HTTPException(401, "Token refresh failed")


@router.get("/me")
async def get_me(
    user: dict = Depends(get_current_user),
    auth: dict = Depends(get_current_org),
):
    """Get current user and organization info."""
    return {
        "user": user,
        "organization": auth["org"],
        "role": auth["role"],
    }
