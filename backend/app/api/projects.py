from __future__ import annotations

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_org
from app.core.database import get_supabase_admin

log = structlog.get_logger()

router = APIRouter(tags=["projects"])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class CreateProjectBody(BaseModel):
    name: str
    description: str | None = None


class UpdateProjectBody(BaseModel):
    name: str | None = None
    description: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def list_projects(auth: dict = Depends(get_current_org)):
    """List all projects for the current organization."""
    log.info("list_projects", org_id=auth["org_id"])
    admin = get_supabase_admin()
    result = (
        admin.table("projects")
        .select("*")
        .eq("organization_id", auth["org_id"])
        .neq("status", "archived")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


@router.post("")
async def create_project(body: CreateProjectBody, auth: dict = Depends(get_current_org)):
    """Create a new project."""
    log.info("create_project", name=body.name, org_id=auth["org_id"])
    admin = get_supabase_admin()
    result = (
        admin.table("projects")
        .insert({
            "name": body.name,
            "description": body.description,
            "organization_id": auth["org_id"],
            "created_by": auth["user"]["id"],
            "created_at": datetime.now(UTC).isoformat(),
        })
        .execute()
    )
    return result.data[0]


@router.get("/{id}")
async def get_project(id: str, auth: dict = Depends(get_current_org)):
    """Get project details."""
    log.info("get_project", project_id=id)
    admin = get_supabase_admin()
    result = (
        admin.table("projects")
        .select("*")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Project not found")
    return result.data


@router.patch("/{id}")
async def update_project(id: str, body: UpdateProjectBody, auth: dict = Depends(get_current_org)):
    """Update a project."""
    log.info("update_project", project_id=id)
    admin = get_supabase_admin()
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = (
        admin.table("projects")
        .update(updates)
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Project not found")
    return result.data[0]


@router.delete("/{id}")
async def delete_project(id: str, auth: dict = Depends(get_current_org)):
    """Archive a project (soft delete)."""
    log.info("delete_project", project_id=id)
    admin = get_supabase_admin()
    result = (
        admin.table("projects")
        .update({"status": "archived"})
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"detail": "Project archived"}
