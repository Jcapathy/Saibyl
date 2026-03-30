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


async def _safe_task(coro, name: str):
    try:
        await coro
    except Exception:
        log.exception("background_task_failed", task=name)

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
    persona_pack_id: str | None = None
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
            "persona_pack_id": body.persona_pack_id,
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
    auth: dict = Depends(get_current_org),
):
    """List simulations (paginated)."""
    log.info("list_simulations", org_id=auth["org_id"], limit=limit, offset=offset)
    admin = get_supabase_admin()
    result = (
        admin.table("simulations")
        .select("*")
        .eq("organization_id", auth["org_id"])
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

    asyncio.create_task(_safe_task(run_prepare_agents(id), "prepare_agents"))
    return {"status": "started"}


@router.post("/{id}/start")
async def start_simulation(id: str, auth: dict = Depends(get_current_org)):
    """Start running a simulation."""
    log.info("start_simulation", simulation_id=id, org_id=auth["org_id"])
    admin = get_supabase_admin()
    sim = (
        admin.table("simulations")
        .select("id, is_ab_test")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not sim.data:
        raise HTTPException(status_code=404, detail="Simulation not found")

    if sim.data.get("is_ab_test"):
        asyncio.create_task(_safe_task(run_simulation_ab(id), "run_simulation_ab"))
    else:
        asyncio.create_task(_safe_task(run_simulation(id), "run_simulation"))
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
    return {"detail": "Stop signal sent"}


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
