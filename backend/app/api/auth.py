from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.core.auth import get_current_org, get_current_user
from app.core.database import get_supabase, get_supabase_admin
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
    supabase = get_supabase()
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
async def logout():
    """Sign out (invalidate Supabase refresh token, client should discard tokens)."""
    try:
        supabase = get_supabase()
        supabase.auth.sign_out()
    except Exception:
        pass
    return {"message": "Logged out"}


@router.post("/refresh")
async def refresh(refresh_token: str, request: Request):
    """Refresh session token."""
    await check_rate_limit(request, "refresh", max_attempts=20, window_seconds=60, fail_open=False)
    supabase = get_supabase()
    try:
        result = supabase.auth.refresh_session(refresh_token)
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
