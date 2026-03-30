from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.auth import get_current_org
from app.core.database import get_supabase_admin
from app.services.engine.personas.interview_engine import (
    interview_agent,
    interview_batch,
    interview_by_persona_type,
)
from app.services.platforms.simulation_runner import get_simulation_status, stop_simulation
from app.workers.simulation_tasks import (
    run_prepare_agents,
    run_simulation,
    run_simulation_ab,
)

log = structlog.get_logger()


async def _safe_task(coro, name: str, simulation_id: str | None = None):
    try:
        await coro
    except Exception as exc:
        log.exception("background_task_failed", task=name)
        if simulation_id:
            try:
                admin = get_supabase_admin()
                admin.table("simulations").update({
                    "status": "failed",
                    "error_message": f"[{name}] {type(exc).__name__}: {exc}",
                }).eq("id", simulation_id).execute()
            except Exception:
                pass

router = APIRouter(tags=["simulations"])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class CreateSimulationBody(BaseModel):
    name: str
    prediction_goal: str
    project_id: str
    platforms: list[str]
    max_rounds: int = 10
    is_ab_test: bool = False
    persona_pack_ids: list[str] = []
    agent_count: int | None = None
    description: str | None = None


class InterviewBody(BaseModel):
    agent_id: str
    prompt: str


class BatchInterviewBody(BaseModel):
    agent_ids: list[str]
    prompt: str


class PersonaInterviewBody(BaseModel):
    persona_type: str
    prompt: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("")
async def create_simulation(body: CreateSimulationBody, auth: dict = Depends(get_current_org)):
    """Create a new simulation."""
    log.info("create_simulation", name=body.name, project_id=body.project_id, org_id=auth["org_id"])
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

    result = (
        admin.table("simulations")
        .insert({
            "name": body.name,
            "prediction_goal": body.prediction_goal,
            "project_id": body.project_id,
            "organization_id": auth["org_id"],
            "platforms": body.platforms,
            "max_rounds": body.max_rounds,
            "is_ab_test": body.is_ab_test,
            "persona_pack_ids": body.persona_pack_ids,
            "agent_count": body.agent_count,
            "description": body.description,
            "status": "draft",
            "created_by": auth["user"]["id"],
            "created_at": datetime.now(UTC).isoformat(),
        })
        .execute()
    )
    return result.data[0]


@router.get("")
async def list_simulations(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    project_id: str | None = Query(None),
    auth: dict = Depends(get_current_org),
):
    """List simulations (paginated, optionally filtered by project)."""
    log.info("list_simulations", org_id=auth["org_id"], limit=limit, offset=offset, project_id=project_id)
    admin = get_supabase_admin()
    query = (
        admin.table("simulations")
        .select("*", count="exact")
        .eq("organization_id", auth["org_id"])
    )
    if project_id:
        query = query.eq("project_id", project_id)
    result = (
        query
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return result.data


@router.get("/{id}")
async def get_simulation(id: str, auth: dict = Depends(get_current_org)):
    """Get simulation details."""
    log.info("get_simulation", simulation_id=id)
    admin = get_supabase_admin()
    result = (
        admin.table("simulations")
        .select("*")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return result.data


@router.post("/{id}/prepare")
async def prepare_simulation(id: str, auth: dict = Depends(get_current_org)):
    """Trigger agent preparation for a simulation."""
    log.info("prepare_simulation", simulation_id=id, org_id=auth["org_id"])
    admin = get_supabase_admin()
    sim = (
        admin.table("simulations")
        .select("id")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not sim.data:
        raise HTTPException(status_code=404, detail="Simulation not found")

    asyncio.create_task(_safe_task(run_prepare_agents(id), "prepare_agents", simulation_id=id))
    return {"status": "started"}


@router.post("/{id}/start")
async def start_simulation(id: str, auth: dict = Depends(get_current_org)):
    """Start running a simulation."""
    log.info("start_simulation", simulation_id=id, org_id=auth["org_id"])
    admin = get_supabase_admin()
    sim = (
        admin.table("simulations")
        .select("id, is_ab_test, status")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not sim.data:
        raise HTTPException(status_code=404, detail="Simulation not found")

    current_status = sim.data.get("status")
    if current_status == "preparing":
        raise HTTPException(
            status_code=409,
            detail="Simulation is still being prepared. Wait for status 'ready' before starting.",
        )
    if current_status == "draft":
        raise HTTPException(
            status_code=409,
            detail="Simulation must be prepared first. Call /prepare and wait for status 'ready'.",
        )
    if current_status == "running":
        raise HTTPException(status_code=409, detail="Simulation is already running.")

    if sim.data.get("is_ab_test"):
        asyncio.create_task(_safe_task(run_simulation_ab(id), "run_simulation_ab", simulation_id=id))
    else:
        asyncio.create_task(_safe_task(run_simulation(id), "run_simulation", simulation_id=id))
    return {"status": "started"}


@router.post("/{id}/stop")
async def stop_simulation_endpoint(id: str, auth: dict = Depends(get_current_org)):
    """Stop a running simulation."""
    log.info("stop_simulation", simulation_id=id, org_id=auth["org_id"])
    admin = get_supabase_admin()
    sim = (
        admin.table("simulations")
        .select("id")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not sim.data:
        raise HTTPException(status_code=404, detail="Simulation not found")

    await stop_simulation(id)
    # Also directly update DB status so frontend sees it immediately
    admin.table("simulations").update({"status": "stopped"}).eq("id", id).execute()
    return {"detail": "Simulation stopped"}


@router.get("/{id}/status")
async def simulation_status(id: str, auth: dict = Depends(get_current_org)):
    """Get current simulation status."""
    log.info("simulation_status", simulation_id=id)
    admin = get_supabase_admin()
    sim = (
        admin.table("simulations")
        .select("id")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not sim.data:
        raise HTTPException(status_code=404, detail="Simulation not found")

    status = get_simulation_status(id)
    return status.model_dump()


@router.get("/{id}/events")
async def list_events(
    id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    auth: dict = Depends(get_current_org),
):
    """List simulation events (paginated)."""
    log.info("list_events", simulation_id=id, limit=limit, offset=offset)
    admin = get_supabase_admin()
    # Verify simulation belongs to org
    sim = (
        admin.table("simulations")
        .select("id")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not sim.data:
        raise HTTPException(status_code=404, detail="Simulation not found")

    result = (
        admin.table("simulation_events")
        .select("*")
        .eq("simulation_id", id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return result.data


@router.get("/{id}/agents")
async def list_agents(id: str, auth: dict = Depends(get_current_org)):
    """List agents in a simulation."""
    log.info("list_agents", simulation_id=id)
    admin = get_supabase_admin()
    sim = (
        admin.table("simulations")
        .select("id")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not sim.data:
        raise HTTPException(status_code=404, detail="Simulation not found")

    result = (
        admin.table("simulation_agents")
        .select("*")
        .eq("simulation_id", id)
        .execute()
    )
    return result.data


@router.post("/{id}/interview")
async def interview_agent_endpoint(id: str, body: InterviewBody, auth: dict = Depends(get_current_org)):
    """Interview a single agent."""
    log.info("interview_agent", simulation_id=id, agent_id=body.agent_id)
    admin = get_supabase_admin()
    sim = (
        admin.table("simulations")
        .select("id")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not sim.data:
        raise HTTPException(status_code=404, detail="Simulation not found")

    result = await interview_agent(id, body.agent_id, body.prompt)
    return result.model_dump()


@router.post("/{id}/interview/batch")
async def interview_batch_endpoint(id: str, body: BatchInterviewBody, auth: dict = Depends(get_current_org)):
    """Interview multiple agents."""
    log.info("interview_batch", simulation_id=id, count=len(body.agent_ids))
    admin = get_supabase_admin()
    sim = (
        admin.table("simulations")
        .select("id")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not sim.data:
        raise HTTPException(status_code=404, detail="Simulation not found")

    results = await interview_batch(id, body.agent_ids, body.prompt)
    return [r.model_dump() for r in results]


@router.post("/{id}/interview/by-persona")
async def interview_by_persona_endpoint(id: str, body: PersonaInterviewBody, auth: dict = Depends(get_current_org)):
    """Interview all agents of a specific persona type."""
    log.info("interview_by_persona", simulation_id=id, persona_type=body.persona_type)
    admin = get_supabase_admin()
    sim = (
        admin.table("simulations")
        .select("id")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not sim.data:
        raise HTTPException(status_code=404, detail="Simulation not found")

    results = await interview_by_persona_type(id, body.persona_type, body.prompt)
    return [r.model_dump() for r in results]
