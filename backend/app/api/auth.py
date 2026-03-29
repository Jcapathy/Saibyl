from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_org, get_current_user
from app.core.database import get_supabase, get_supabase_admin

router = APIRouter(tags=["auth"])


class SignupRequest(BaseModel):
    email: str
    password: str
    org_name: str


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/signup")
async def signup(body: SignupRequest):
    """Create a new user, organization, and link them."""
    supabase = get_supabase()
    admin = get_supabase_admin()

    # Create user via Supabase Auth
    try:
        auth_result = supabase.auth.sign_up({
            "email": body.email,
            "password": body.password,
        })
        user = auth_result.user
        if not user:
            raise HTTPException(400, "Signup failed")
    except Exception as e:
        raise HTTPException(400, f"Signup failed: {e}")

    # Create organization
    slug = body.org_name.lower().replace(" ", "-")[:50]
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

    return {"user_id": user.id, "organization_id": org["id"], "email": body.email}


@router.post("/login")
async def login(body: LoginRequest):
    """Sign in and return session."""
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
    except Exception as e:
        raise HTTPException(401, f"Login failed: {e}")


@router.post("/logout")
async def logout():
    """Sign out (client should discard tokens)."""
    return {"message": "Logged out"}


@router.post("/refresh")
async def refresh(refresh_token: str):
    """Refresh session token."""
    supabase = get_supabase()
    try:
        result = supabase.auth.refresh_session(refresh_token)
        return {
            "access_token": result.session.access_token,
            "refresh_token": result.session.refresh_token,
        }
    except Exception as e:
        raise HTTPException(401, f"Refresh failed: {e}")


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
