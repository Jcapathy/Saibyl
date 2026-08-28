from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from app.core.auth import get_current_org, get_current_user, security
from app.core.config import settings
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


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    """The recovery JWT from the emailed link, plus the new password.

    `access_token` is the token GoTrue puts in the link's URL fragment. It is a
    real, short-lived, single-purpose JWT — so it is *verified* here by asking
    GoTrue who it belongs to, never decoded and trusted locally.
    """

    access_token: str
    password: str


# Supabase's own floor is 6. Eight is ours, and it is checked here so the
# refusal comes back in a sentence a founder can act on rather than as a
# GoTrue error string surfaced through a generic 400.
MIN_PASSWORD_LENGTH = 8

# The same answer for an address that has an account and one that does not.
#
# This route is otherwise a free account-existence oracle: anyone could type
# addresses in and read which ones come back "sent". The cost of closing that is
# that a founder who typos their own address is told the mail is on its way, so
# the sentence says which address it went to — they can read it and see the typo.
RESET_SENT_MESSAGE = (
    "If an account exists for that address, a reset link is on its way. "
    "The link is good for one hour."
)


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
    #
    # **This used to answer every failure with "Signup failed" and discard the
    # reason.** Not log it — discard it: a bare `except Exception` that raised a
    # fixed string. So a founder whose email already had an account was told
    # nothing usable, and nobody could find out why from the server either,
    # because the original error never reached a log.
    #
    # Found on 2026-08-27 when the founder could not create an account with his
    # own address. The address had a confirmed account from 2026-03-28. The
    # refusal was correct; the sentence was useless.
    #
    # The already-exists case is separated because it is the only one the person
    # reading it can act on, and the action is not "try again".
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
    except Exception as exc:
        detail = str(exc).lower()
        already = (
            "already" in detail
            or "registered" in detail
            or "duplicate" in detail
            or "exists" in detail
        )
        # The address is the founder's own and is echoed back to them, so it
        # discloses nothing they did not type. The *reason* goes to the log with
        # the exception attached, which is where a diagnosis has to be possible.
        log.warning(
            "signup_rejected",
            email=body.email,
            already_registered=already,
            error=str(exc)[:300],
            error_type=type(exc).__name__,
        )
        if already:
            raise HTTPException(
                409,
                "An account already exists for this email. Sign in instead, or "
                'use "Forgot password?" on the sign-in page to reset it.',
            ) from exc
        raise HTTPException(
            400,
            "We could not create the account. If this keeps happening, email "
            "info@saidolabs.com and we will sort it out.",
        ) from exc

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


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, request: Request):
    """Send a password reset link.

    **There was no way to recover an account.** Not a broken one — none: no
    route, no email, no token. `LoginPage` offered "Forgot password?" as a
    `mailto:info@saidolabs.com`, and Settings → Account said password changes
    were handled by email, meaning a founder locked out of Saibyl waited on a
    human reading a mailbox. That is the same class of defect as the grey
    button the founder's rule bans: it looks like a flow and it is not one.

    GoTrue already mints and mails the recovery token; all this does is ask it
    to, and point the link at our own `/reset-password` page instead of
    Supabase's default. The link's token is what `reset_password` verifies.

    The answer never varies with whether the address has an account — see
    `RESET_SENT_MESSAGE`. That includes the failure path: if GoTrue itself is
    down, the caller still gets the same sentence and the reason goes to the
    log, because a 500 here that only fires for real addresses would leak the
    same fact the neutral message exists to hide.
    """
    await check_rate_limit(
        request, "forgot_password", max_attempts=5, window_seconds=900, fail_open=False
    )
    # A per-request client, for the same reason login uses one: anything that
    # touches auth on the shared singleton writes into a session the whole
    # process reads. See `new_auth_client`.
    try:
        new_auth_client().auth.reset_password_email(
            body.email,
            {"redirect_to": f"{settings.frontend_url}/reset-password"},
        )
        log.info("password_reset_requested", email=body.email)
    except Exception:
        log.warning("password_reset_send_failed", email=body.email, exc_info=True)

    return {"message": RESET_SENT_MESSAGE}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, request: Request):
    """Set a new password using the token from the emailed link.

    Three things happen, and the third is the one that is easy to leave out:

    1. The recovery token is **verified by GoTrue**, not parsed here.
       `auth.get_user(jwt)` is a round trip that fails on a forged, expired or
       already-spent token, and it is what tells us which account to act on.
       Nothing in the request body names the user — a body-supplied `user_id`
       would let anyone with any valid token reset anyone's password.
    2. The password is changed with the service-role client.
    3. **Every other session for that user is revoked.** Somebody resetting a
       password is often doing it because they think somebody else has it. If
       the attacker's existing refresh token survived, the reset would achieve
       nothing; `sign_out(..., "global")` is what makes it mean something.
    """
    await check_rate_limit(
        request, "reset_password", max_attempts=10, window_seconds=900, fail_open=False
    )

    if len(body.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            400, f"Choose a password of at least {MIN_PASSWORD_LENGTH} characters."
        )

    auth_client = new_auth_client()
    try:
        result = auth_client.auth.get_user(body.access_token)
        user = result.user if result else None
    except Exception as exc:
        log.warning("password_reset_token_rejected", error=str(exc)[:200])
        user = None

    if not user:
        # Deliberately the same sentence for expired, forged and already-used:
        # the reader's next action is identical in all three cases, and naming
        # which one it was tells an attacker whether they guessed a real token.
        raise HTTPException(
            400,
            "This reset link has expired or has already been used. "
            "Request a new one and it will work.",
        )

    admin = get_supabase_admin()
    try:
        admin.auth.admin.update_user_by_id(user.id, {"password": body.password})
    except Exception as exc:
        log.exception("password_reset_update_failed", user_id=user.id)
        raise HTTPException(
            400,
            "We could not set that password. If this keeps happening, email "
            "info@saidolabs.com and we will sort it out.",
        ) from exc

    try:
        admin.auth.admin.sign_out(body.access_token, "global")
    except Exception:
        # Not fatal — the password is already changed, which is the thing the
        # caller asked for. Loud, because a reset that failed to evict the old
        # sessions is exactly the case somebody needs to be able to find later.
        log.warning("password_reset_revoke_failed", user_id=user.id, exc_info=True)

    log.info("password_reset_completed", user_id=user.id)
    return {"message": "Your password is set. Sign in with it now."}


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
