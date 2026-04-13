from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from app.core.auth import get_current_org, get_current_user
from app.core.config import settings
from app.core.database import get_supabase, get_supabase_admin
from app.core.rate_limit import check_rate_limit

router = APIRouter(tags=["auth"])

# Cookie configuration
_COOKIE_OPTS: dict = {
    "httponly": True,
    "secure": True,
    "samesite": "none",
    "path": "/",
}
_ACCESS_MAX_AGE = 60 * 60           # 1 hour
_REFRESH_MAX_AGE = 60 * 60 * 24 * 7  # 7 days


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Set httpOnly cookies for both tokens."""
    response.set_cookie(
        key="saibyl_access_token",
        value=access_token,
        max_age=_ACCESS_MAX_AGE,
        **_COOKIE_OPTS,
    )
    response.set_cookie(
        key="saibyl_refresh_token",
        value=refresh_token,
        max_age=_REFRESH_MAX_AGE,
        **_COOKIE_OPTS,
    )


def _clear_auth_cookies(response: Response) -> None:
    """Remove auth cookies."""
    for name in ("saibyl_access_token", "saibyl_refresh_token"):
        response.delete_cookie(key=name, path="/", httponly=True, secure=True, samesite="none")


class SignupRequest(BaseModel):
    email: str
    password: str
    org_name: str


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/signup")
async def signup(body: SignupRequest, request: Request, response: Response):
    """Create a new user, organization, and link them."""
    await check_rate_limit(request, "signup", max_attempts=5, window_seconds=300, fail_open=False)
    supabase = get_supabase()
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
    org = admin.table("organizations").insert({
        "name": body.org_name,
        "slug": slug,
    }).execute().data[0]

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

    # Sign in to get tokens, then set cookies
    try:
        result = supabase.auth.sign_in_with_password({
            "email": body.email,
            "password": body.password,
        })
        _set_auth_cookies(response, result.session.access_token, result.session.refresh_token)
    except Exception:
        pass  # Signup succeeded but auto-login failed — user can login manually

    return {"user_id": user.id, "organization_id": org["id"], "email": body.email}


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response):
    """Sign in and set httpOnly session cookies."""
    await check_rate_limit(request, "login", max_attempts=10, window_seconds=60, fail_open=False)
    supabase = get_supabase()
    try:
        result = supabase.auth.sign_in_with_password({
            "email": body.email,
            "password": body.password,
        })
        _set_auth_cookies(response, result.session.access_token, result.session.refresh_token)
        return {"user_id": result.user.id}
    except Exception:
        raise HTTPException(401, "Invalid email or password")


@router.post("/logout")
async def logout(response: Response):
    """Sign out — clear httpOnly cookies."""
    try:
        supabase = get_supabase()
        supabase.auth.sign_out()
    except Exception:
        pass
    _clear_auth_cookies(response)
    return {"message": "Logged out"}


@router.post("/refresh")
async def refresh(request: Request, response: Response):
    """Refresh session using httpOnly cookie."""
    await check_rate_limit(request, "refresh", max_attempts=20, window_seconds=60, fail_open=False)
    token = request.cookies.get("saibyl_refresh_token")
    if not token:
        raise HTTPException(401, "No refresh token")
    supabase = get_supabase()
    try:
        result = supabase.auth.refresh_session(token)
        _set_auth_cookies(response, result.session.access_token, result.session.refresh_token)
        return {"message": "Refreshed"}
    except Exception:
        _clear_auth_cookies(response)
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
