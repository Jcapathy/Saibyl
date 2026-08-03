from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.auth import get_current_org
from app.core.database import get_supabase_admin
from app.services.engine.founder_stages import FOUNDER_STAGES, FounderStage
from app.services.engine.personas.interview_engine import (
    interview_agent,
    interview_batch,
    interview_by_persona_type,
)
from app.services.platforms.simulation_control import get_simulation_status, stop_simulation
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
    variants: int = Field(default=1, ge=1, le=8)
    depth: Literal["brief", "standard", "deep"] = "standard"

    # Which lens this run is configured through. None means an unlensed run —
    # the 63 simulations that predate lenses read that way too, rather than
    # being retroactively assigned one they were never configured with.
    lens: Literal["founder", "marketing", "crisis"] | None = None
    founder_stage: FounderStage | None = None
    # A synthesized ICP to run against. Its compiled pack is appended to
    # persona_pack_ids, so an ICP and built-in packs can be blended.
    icp_profile_id: str | None = None
    # Share of the swarm that is incumbent-aligned. The 0.5 ceiling is enforced
    # here, in the database, and in the ICP API: past half the swarm the
    # headline valence is a function of the share the user picked, and it will
    # still be read as a measurement of the market.
    adversarial_share: float = Field(default=0.0, ge=0.0, le=0.5)


class StartSimulationBody(BaseModel):
    """The quote to redeem for this run.

    Optional so an API client can start a run without configuring one in the
    UI, but a run started without a quote is priced from the stored shape at
    the same rate — there is no cheaper path.
    """

    quote_id: str | None = None


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

    # Guarded here as well as in the quote: `POST /simulations/{id}/start`
    # without a quote prices from this stored shape, so a simulation created
    # with variants > 1 would be charged for arenas the engine never runs.
    from app.services.billing.agent_pricing import MAX_RUNNABLE_VARIANTS
    if body.variants > MAX_RUNNABLE_VARIANTS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Multi-variant runs are not available yet — the engine runs "
                f"{MAX_RUNNABLE_VARIANTS} arena. Matched-swarm variant testing "
                f"arrives with the Marketing lens."
            ),
        )

    # A stage belongs to the Founder lens. Silently accepting one on a Crisis
    # run would let a report be planned from questions the run was never
    # configured to answer.
    if body.founder_stage and body.lens != "founder":
        raise HTTPException(
            status_code=400,
            detail="founder_stage is only valid on a Founder-lens run (lens='founder').",
        )

    persona_pack_ids = list(body.persona_pack_ids)
    if body.icp_profile_id:
        icp = (
            admin.table("icp_profiles")
            .select("pack_id")
            .eq("id", body.icp_profile_id)
            .eq("organization_id", auth["org_id"])
            .execute()
        )
        if not icp.data:
            raise HTTPException(status_code=404, detail="ICP profile not found")
        # Appended rather than replacing: a founder may legitimately blend a
        # synthesized ICP with a built-in pack — press, or a demographic
        # segment the material never mentions. The 16 packs are priors and
        # blend targets, not the answer (DECISIONS §3), and that is only true
        # if blending is actually possible.
        pack_id = icp.data[0]["pack_id"]
        if pack_id not in persona_pack_ids:
            persona_pack_ids.append(pack_id)

    # An adversarial share with no adversarial archetypes in any selected pack
    # silently does nothing — the share is expressed as archetype weight, and
    # built-in packs carry none. Caught here, because the run would otherwise
    # complete and report a cohort split the user configured and never got.
    if body.adversarial_share > 0 and not body.icp_profile_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "adversarial_share requires an ICP profile. The incumbent-aligned "
                "cohort is synthesized from your uploaded material; the built-in "
                "persona packs contain no adversarial archetypes for the share to "
                "apply to."
            ),
        )

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
            "persona_pack_ids": persona_pack_ids,
            "agent_count": body.agent_count,
            "description": body.description,
            "variants": body.variants,
            "depth": body.depth,
            "lens": body.lens,
            "founder_stage": body.founder_stage,
            "icp_profile_id": body.icp_profile_id,
            "adversarial_share": body.adversarial_share,
            "status": "draft",
            "created_by": auth["user"]["id"],
            "created_at": datetime.now(UTC).isoformat(),
        })
        .execute()
    )
    return result.data[0]


@router.get("/founder-stages")
async def list_founder_stages(auth: dict = Depends(get_current_org)):
    """The five Founder-lens stages, for the stage picker.

    Served from the backend registry rather than duplicated in the frontend so
    that a stage's defaults, its report questions, and the limits it states in
    the report cannot disagree with what the picker showed.

    Registered above `GET /{id}`, which would otherwise match "founder-stages"
    as a simulation id and 404. That collision is the same class of bug as the
    unreachable export route Phase 0 fixed, and route order is the only thing
    preventing it.
    """
    return [spec.model_dump() for spec in FOUNDER_STAGES.values()]


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


@router.delete("/{id}")
async def delete_simulation(id: str, auth: dict = Depends(get_current_org)):
    """Delete a simulation and everything derived from it."""
    log.info("delete_simulation", simulation_id=id, org_id=auth["org_id"])
    admin = get_supabase_admin()

    sim = (
        admin.table("simulations")
        .select("id, status")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
        .execute()
    )
    if not sim.data:
        raise HTTPException(status_code=404, detail="Simulation not found")

    if sim.data[0]["status"] == "running":
        raise HTTPException(status_code=409, detail="Stop the simulation before deleting it")

    # Report sections are keyed by report_id, so they must go before the reports.
    reports = (
        admin.table("reports").select("id").eq("simulation_id", id).execute()
    ).data or []
    for report in reports:
        admin.table("report_sections").delete().eq("report_id", report["id"]).execute()
    admin.table("reports").delete().eq("simulation_id", id).execute()

    admin.table("simulation_events").delete().eq("simulation_id", id).execute()
    admin.table("simulation_agents").delete().eq("simulation_id", id).execute()
    admin.table("simulations").delete().eq("id", id).execute()

    return {"status": "deleted", "id": id}


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
async def start_simulation(
    id: str,
    body: StartSimulationBody | None = None,
    auth: dict = Depends(get_current_org),
):
    """Start running a simulation, redeeming its quote."""
    log.info("start_simulation", simulation_id=id, org_id=auth["org_id"])
    admin = get_supabase_admin()
    sim = (
        admin.table("simulations")
        .select("id, is_ab_test, status, agent_count, max_rounds, platforms, variants")
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

    # Enforce billing quota
    from app.services.billing.stripe_service import check_simulation_quota
    if not await check_simulation_quota(auth["org_id"]):
        raise HTTPException(status_code=402, detail="Simulation quota exceeded for this billing period")

    from app.services.billing.agent_pricing import check_credit_budget, deduct_credits
    from app.services.billing.run_quote import QuoteError, consume_quote

    agent_count = sim.data.get("agent_count") or 1
    max_rounds = sim.data.get("max_rounds") or 10
    platforms = len(sim.data.get("platforms") or ["twitter_x"])
    variants = sim.data.get("variants") or 1

    # Credits are charged at start, not at completion. Deducting on completion
    # would let a user with one run's worth of credits start ten runs at once
    # and have every balance check pass; a failed run still consumed compute.
    quote_id = body.quote_id if body else None
    if quote_id:
        try:
            quote = consume_quote(
                quote_id, auth["org_id"], id,
                (agent_count, max_rounds, platforms, variants),
            )
        except QuoteError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        deduct_credits(auth["org_id"], quote.credits)
    else:
        # No quote — a run started from the API or an older client. Priced the
        # same way, just without the signed guarantee that the price shown is
        # the price charged.
        budget = check_credit_budget(
            auth["org_id"], agent_count, max_rounds, platforms, variants
        )
        if not budget.allowed:
            raise HTTPException(status_code=402, detail=budget.message)
        deduct_credits(auth["org_id"], budget.credits_required)

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
