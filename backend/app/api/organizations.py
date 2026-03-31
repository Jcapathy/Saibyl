from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_org, get_current_user
from app.core.database import get_supabase_admin

log = structlog.get_logger()

router = APIRouter(tags=["organizations"])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class CreateOrgBody(BaseModel):
    name: str
    slug: str


class UpdateOrgBody(BaseModel):
    name: str


class InviteMemberBody(BaseModel):
    email: str
    role: Literal["member", "viewer"] = "member"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def list_organizations(user: dict = Depends(get_current_user)):
    """List all organizations the current user belongs to."""
    log.info("list_organizations", user_id=user["id"])
    admin = get_supabase_admin()
    result = (
        admin.table("organization_members")
        .select("organization_id, role, organizations(id, name, slug, plan, created_at)")
        .eq("user_id", user["id"])
        .execute()
    )
    return result.data


@router.post("")
async def create_organization(body: CreateOrgBody, user: dict = Depends(get_current_user)):
    """Create a new organization and add the current user as owner."""
    log.info("create_organization", name=body.name, slug=body.slug, user_id=user["id"])
    admin = get_supabase_admin()
    org = (
        admin.table("organizations")
        .insert({"name": body.name, "slug": body.slug, "created_at": datetime.now(UTC).isoformat()})
        .execute()
    ).data[0]

    admin.table("organization_members").insert({
        "organization_id": org["id"],
        "user_id": user["id"],
        "role": "owner",
        "joined_at": datetime.now(UTC).isoformat(),
    }).execute()

    return org


@router.get("/{id}")
async def get_organization(id: str, auth: dict = Depends(get_current_org)):
    """Get organization details."""
    log.info("get_organization", org_id=id)
    admin = get_supabase_admin()
    result = (
        admin.table("organizations")
        .select("*")
        .eq("id", id)
        .eq("id", auth["org_id"])
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Organization not found")
    return result.data


@router.patch("/{id}")
async def update_organization(id: str, body: UpdateOrgBody, auth: dict = Depends(get_current_org)):
    """Update organization name. Owner or admin only."""
    if auth["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owners and admins can update the organization")
    if id != auth["org_id"]:
        raise HTTPException(status_code=403, detail="Cannot update another organization")
    log.info("update_organization", org_id=id, name=body.name)
    admin = get_supabase_admin()
    result = (
        admin.table("organizations")
        .update({"name": body.name})
        .eq("id", id)
        .execute()
    )
    return result.data[0]


@router.get("/{id}/members")
async def list_members(id: str, auth: dict = Depends(get_current_org)):
    """List members of an organization."""
    if id != auth["org_id"]:
        raise HTTPException(status_code=403, detail="Cannot view members of another organization")
    log.info("list_members", org_id=id)
    admin = get_supabase_admin()
    result = (
        admin.table("organization_members")
        .select("*")
        .eq("organization_id", id)
        .execute()
    )
    return result.data


@router.post("/{id}/invite")
async def invite_member(id: str, body: InviteMemberBody, auth: dict = Depends(get_current_org)):
    """Invite a member by email. Owner or admin only."""
    if auth["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owners and admins can invite members")
    if id != auth["org_id"]:
        raise HTTPException(status_code=403, detail="Cannot invite to another organization")
    log.info("invite_member", org_id=id, email=body.email, role=body.role)
    admin = get_supabase_admin()
    result = (
        admin.table("organization_members")
        .insert({
            "organization_id": id,
            "invited_email": body.email,
            "role": body.role,
            "invited_at": datetime.now(UTC).isoformat(),
        })
        .execute()
    )
    return result.data[0]


@router.delete("/{id}/members/{user_id}")
async def remove_member(id: str, user_id: str, auth: dict = Depends(get_current_org)):
    """Remove a member from the organization. Owner or admin only."""
    if auth["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owners and admins can remove members")
    if id != auth["org_id"]:
        raise HTTPException(status_code=403, detail="Cannot modify another organization")
    log.info("remove_member", org_id=id, user_id=user_id)
    admin = get_supabase_admin()
    admin.table("organization_members").delete().eq("organization_id", id).eq("user_id", user_id).execute()
    return {"detail": "Member removed"}
