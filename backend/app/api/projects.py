from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_org, require_can_destroy
from app.core.database import fetch_all, get_supabase_admin

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
    """List all projects for the current organization, each with a real file count.

    `document_count` is counted from `documents` on every request. It replaces
    `projects.asset_count`, which the card used to render and which was never a
    count of anything: migration 010 added the column with `DEFAULT 0` and never
    backfilled it, migration 025 records that the single-argument RPC the upload
    route calls existed in production only because somebody added it by hand,
    the media ingestion path built the same request without `.execute()` so
    those uploads never counted at all, and the upload route logs and carries on
    when the RPC fails. A founder with files in a product read "0 documents".

    Counted rather than backfilled because a backfill fixes the rows that exist
    today and leaves every leak above in place. `asset_count` is still returned
    by `select("*")` — dropping the column is a migration that must land after
    this is deployed and serving, per §2a's ordering rule — but nothing reads it
    from here on.
    """
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
    projects = result.data or []
    if not projects:
        return projects

    # One query for the whole page rather than one per card. `fetch_all` because
    # PostgREST caps a response at 1,000 rows by default and an org past that
    # would silently start under-counting the products at the end of the list —
    # which is the same defect as the counter, arrived at a different way.
    documents = fetch_all(
        admin.table("documents")
        .select("id, project_id")
        .eq("organization_id", auth["org_id"])
        .in_("project_id", [p["id"] for p in projects])
    )
    counts: dict[str, int] = defaultdict(int)
    for row in documents:
        counts[str(row["project_id"])] += 1

    for project in projects:
        project["document_count"] = counts[str(project["id"])]
    return projects


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
async def delete_project(id: str, auth: dict = Depends(require_can_destroy)):
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
