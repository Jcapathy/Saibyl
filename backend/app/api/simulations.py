from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.auth import get_current_org
from app.core.config import settings
from app.core.database import get_supabase_admin
from app.core.tasks import spawn
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
)

log = structlog.get_logger()


def _mark_simulation_failed(simulation_id: str, name: str) -> Callable[[Exception], None]:
    """`on_failure` for `spawn`: a run whose worker died must say so.

    Without this the row stays `preparing`/`running` forever and the user
    watches a spinner for a failure that was logged and never surfaced.
    """
    def _mark(exc: Exception) -> None:
        # The exception goes to the log, where we can act on it. The row gets
        # a sentence, because the row is rendered to the founder — this is the
        # line P1-7 names, and it is how somebody ends up reading
        # `KeyError: 'organization_id'` in monospace on a page they paid for.
        log.error(
            "simulation_worker_failed",
            simulation_id=simulation_id,
            task=name,
            error_type=type(exc).__name__,
            error=str(exc)[:500],
        )
        get_supabase_admin().table("simulations").update({
            "status": "failed",
            "error_message": (
                "This run stopped before it finished. Anything it had already "
                "measured is saved — start a new run when you're ready, and "
                "tell us if it happens again."
            ),
        }).eq("id", simulation_id).execute()
    return _mark


router = APIRouter(tags=["simulations"])


def _variants_carrying_copy(admin, simulation_id: str) -> int:
    """How many of this run's variants have copy for an arena to be about.

    Deliberately mirrors `services/engine/variants.load_arenas`, which is the
    only thing that decides how many arenas actually execute: a variant row with
    blank content falls back to the run's `prediction_goal`, which is not an
    alternative under test — it is the control run a second time.

    A lookup failure is raised, not counted as zero. Pricing a run from a failed
    variant lookup is precisely how a user gets charged for arenas that never
    run, and `load_arenas` already swallows this failure downstream (by design —
    a run is worth more than a scoreboard). Swallowing it here as well would
    make the overcharge unobservable on both ends.
    """
    rows = (
        admin.table("simulation_variants")
        .select("variant_key, content")
        .eq("simulation_id", simulation_id)
        .execute()
    ).data or []
    return sum(1 for row in rows if (row.get("content") or "").strip())


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class CreateSimulationBody(BaseModel):
    name: str
    prediction_goal: str
    project_id: str
    platforms: list[str]
    max_rounds: int = 10
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

    # Crisis is shelved, not deleted (PRD_V3 §7): the Literal above still
    # accepts the value so the code stays, and this flag alone decides whether
    # the surface exists. 404 rather than 403 — a hidden surface must not
    # confirm itself by refusing — and checked before any lookup so a request
    # for it touches nothing.
    if body.lens == "crisis" and not settings.crisis_enabled:
        raise HTTPException(status_code=404, detail="Not available.")

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
    from app.services.billing.agent_pricing import MAX_RUNNABLE_VARIANTS, tier_caps
    if body.variants > MAX_RUNNABLE_VARIANTS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"At most {MAX_RUNNABLE_VARIANTS} messages can be tested in one "
                f"run — each one is a full arena the swarm reacts to."
            ),
        )

    # The tier ceiling, enforced where the run is actually created.
    #
    # `POST /billing/estimate-cost` returns `caps` for the configurator to
    # respect, and nothing checked that it had. A client that sent a shape above
    # its plan got a quote for it, a simulation row holding it, and a swarm built
    # to it — the caps were advisory, which is to say they were decoration. The
    # first live run configured through the UI stored 50 agents; the cap is not
    # what produced that number, but nothing here would have stopped a client
    # that sent 250 on a plan capped at 100 either.
    #
    # Refused rather than silently clamped: a run quietly built smaller than the
    # price the customer was shown is the same defect as one built larger, and
    # the message names the ceiling so the client can correct itself.
    caps = tier_caps((auth.get("org") or {}).get("plan"))
    requested_agents = body.agent_count or 0
    if requested_agents > caps.max_agents:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Your plan allows up to {caps.max_agents} people in the room; "
                f"this run asks for {requested_agents}."
            ),
        )
    if body.max_rounds > caps.max_rounds:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Your plan allows up to {caps.max_rounds} rounds; this run asks "
                f"for {body.max_rounds}."
            ),
        )
    if body.variants > caps.max_variants:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Your plan allows {caps.max_variants} messages per run; this run "
                f"asks for {body.variants}. Every message is a full arena — the "
                f"same room reacts to each one — so the run costs proportionally "
                f"more."
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

    # The exact count was already being computed and then thrown away with the
    # rest of the response object, so a client had the page but no way to learn
    # there were others: 50 simulations rendered as one page of 20 and a pager
    # that said "1 of 1".
    #
    # `total=None` rather than `len(items)` when PostgREST answers without a
    # Content-Range: an unknown total and a total of one page are the same
    # number and opposite facts, and guessing here is what produces a pager that
    # confidently hides the rest of the user's work.
    total = result.count
    if total is None:
        log.error(
            "simulation_count_unavailable",
            org_id=auth["org_id"],
            note="count='exact' returned no count; total is unknown, not len(page)",
        )
    return {
        "items": result.data or [],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


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

    spawn(
        run_prepare_agents(id), "prepare_agents",
        on_failure=_mark_simulation_failed(id, "prepare_agents"),
    )
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
        .select(
            # `project_id` is here for `run_will_carry_subject_brief`, which
            # answers "does this run carry a brief?" from the project's material
            # for a first run. Without it every non-re-simulation quoted through
            # this path would resolve to "no brief" and be under-charged by the
            # surcharge — silently, because the shortfall stays above the margin
            # floor and `reconcile_run_cost` never fires.
            "id, status, agent_count, max_rounds, platforms, project_id, "
            "variants, parent_simulation_id, inoculation_asset_ids"
        )
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

    # A run is priced per arena — `estimate_simulation_cost` multiplies agent
    # actions by `simulations.variants` — but the engine executes one arena per
    # *variant row that has copy*. `POST /simulations` accepts `variants: 4` and
    # writes no rows, so a run configured and never given copy was billed four
    # arenas and ran one. Refused here, before the quota check and before any
    # deduction, because credits are taken at start: after the deduction the
    # only remedy is a manual refund.
    #
    # Refused rather than silently repriced to the arena count. A quote signs a
    # shape; charging for a different one would make the price shown and the
    # price taken disagree, which is the defect this guard exists to prevent,
    # inverted.
    configured_variants = sim.data.get("variants") or 1
    if configured_variants > 1:
        with_copy = _variants_carrying_copy(admin, id)
        if with_copy < configured_variants:
            log.warning(
                "start_refused_variants_without_copy",
                simulation_id=id,
                org_id=auth["org_id"],
                priced_variants=configured_variants,
                variants_with_copy=with_copy,
            )
            raise HTTPException(
                status_code=409,
                detail=(
                    f"This run is priced for {configured_variants} variants but only "
                    f"{with_copy} carry copy. Every variant is a full arena and an "
                    f"arena with no copy is never executed, so starting now would "
                    f"charge for {configured_variants - with_copy} arena(s) that do "
                    f"not run. Set the copy with PUT /api/variants/{id}, or send an "
                    f"empty variant list there to run a single arena."
                ),
            )

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
    # An inoculation re-simulation copies its parent's agents rather than
    # generating them, so it makes zero generation calls and must not be
    # charged for them.
    reuse_agents = bool(sim.data.get("parent_simulation_id"))
    # It does, however, carry its assets in every single action prompt. Measured
    # at 5.3x the parent's action input on the first live loop — the saving on
    # generation and the surcharge on actions are separate facts, and quoting
    # only the first one under-charged the re-simulation by roughly a fifth.
    inoculation_assets = len(sim.data.get("inoculation_asset_ids") or [])
    # Uploaded material is distilled into a bounded brief that rides in every
    # agent action prompt, which is the highest-volume stage by an order of
    # magnitude — so a run whose project has material costs ~10% more to serve.
    # Derived from the row already loaded, like `reuse_agents` and
    # `inoculation_assets`; a re-simulation is answered from its parent's stored
    # brief rather than from the project's material, because the material may
    # have changed and the child is charged for what it will actually send.
    from app.services.intelligence.subject_brief import run_will_carry_subject_brief
    subject_brief = run_will_carry_subject_brief(sim.data)

    # Credits are charged at start, not at completion. Deducting on completion
    # would let a user with one run's worth of credits start ten runs at once
    # and have every balance check pass; a failed run still consumed compute.
    quote_id = body.quote_id if body else None
    # A quote prices a shape, and a re-simulation is not just a shape: it skips
    # agent generation and carries its assets in every action prompt. `issue_quote`
    # knows neither, and `consume_quote` only checks agents/rounds/platforms/
    # variants — so a quote issued for the parent's shape would validate cleanly
    # against the child and charge for the wrong run. Re-simulations are priced
    # through the budget path below, which does know. Refused rather than
    # silently ignored, because a caller that sent a quote expects it honoured.
    if quote_id and reuse_agents:
        raise HTTPException(
            status_code=409,
            detail=(
                "A re-simulation cannot be started against a quote. Its price "
                "depends on the assets it carries, which a run quote does not "
                "cover. Start it without a quote_id."
            ),
        )
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
            auth["org_id"], agent_count, max_rounds, platforms, variants,
            reuse_agents=reuse_agents, inoculation_assets=inoculation_assets,
            subject_brief=subject_brief,
        )
        if not budget.allowed:
            raise HTTPException(status_code=402, detail=budget.message)
        deduct_credits(auth["org_id"], budget.credits_required)

    # One entry point. The `is_ab_test` branch that used to sit here chose
    # between `run_simulation_ab` and `run_simulation`, and the two were the same
    # function — V1's A/B ran variant B never. Arenas replaced it: a run's
    # variants live in `simulation_variants`, and `run_simulation` executes all
    # of them.
    spawn(
        run_simulation(id), "run_simulation",
        on_failure=_mark_simulation_failed(id, "run_simulation"),
    )
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
