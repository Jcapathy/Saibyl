from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.auth import get_current_org
from app.core.database import get_supabase_admin
from app.services.engine.ontology_generator import approve_ontology, refine_ontology
from app.workers.simulation_tasks import task_generate_ontology

log = structlog.get_logger()

router = APIRouter(tags=["ontologies"])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class GenerateOntologyBody(BaseModel):
    project_id: str


class RefineOntologyBody(BaseModel):
    feedback: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/generate")
async def generate_ontology(body: GenerateOntologyBody, auth: dict = Depends(get_current_org)):
    """Trigger ontology generation for a project."""
    log.info("generate_ontology", project_id=body.project_id, org_id=auth["org_id"])
    admin = get_supabase_admin()

    # Verify project belongs to org
    project = (
        admin.table("projects")
        .select("id")
        .eq("id", body.project_id)
        .eq("organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not project.data:
        raise HTTPException(status_code=404, detail="Project not found")

    task = task_generate_ontology.delay(body.project_id)
    return {"task_id": task.id}


@router.get("")
async def list_ontologies(project_id: str = Query(...), auth: dict = Depends(get_current_org)):
    """List ontologies for a project."""
    log.info("list_ontologies", project_id=project_id, org_id=auth["org_id"])
    admin = get_supabase_admin()
    result = (
        admin.table("ontologies")
        .select("*")
        .eq("project_id", project_id)
        .eq("organization_id", auth["org_id"])
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


@router.get("/{id}")
async def get_ontology(id: str, auth: dict = Depends(get_current_org)):
    """Get ontology details."""
    log.info("get_ontology", ontology_id=id)
    admin = get_supabase_admin()
    result = (
        admin.table("ontologies")
        .select("*")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Ontology not found")
    return result.data


@router.post("/{id}/refine")
async def refine_ontology_endpoint(id: str, body: RefineOntologyBody, auth: dict = Depends(get_current_org)):
    """Refine an ontology with user feedback."""
    log.info("refine_ontology", ontology_id=id, org_id=auth["org_id"])
    admin = get_supabase_admin()

    # Verify ontology belongs to org
    ontology = (
        admin.table("ontologies")
        .select("id")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not ontology.data:
        raise HTTPException(status_code=404, detail="Ontology not found")

    result = await refine_ontology(id, body.feedback)
    return result


@router.post("/{id}/approve")
async def approve_ontology_endpoint(id: str, auth: dict = Depends(get_current_org)):
    """Approve an ontology."""
    log.info("approve_ontology", ontology_id=id, org_id=auth["org_id"])
    admin = get_supabase_admin()

    # Verify ontology belongs to org
    ontology = (
        admin.table("ontologies")
        .select("id")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not ontology.data:
        raise HTTPException(status_code=404, detail="Ontology not found")

    result = await approve_ontology(id, auth["user"]["id"])
    return result
