from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app.core.auth import get_current_org, require_can_destroy, require_can_spend
from app.core.config import settings
from app.core.database import get_supabase_admin, maybe_one
from app.core.tasks import spawn
from app.services.billing.agent_pricing import MAX_AGENTS_ANY_TIER
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


def _now_iso() -> str:
    """This instant, for the `updated_at` stamps the reaper ages runs from."""
    return datetime.now(UTC).isoformat()


# The statuses a run is still in flight in — the same set the reaper's
# `simulations` rule watches, and the only ones `_mark_simulation_failed` may
# write over.
#
# A run that has reached `complete`, `stopped` or a `failed` some other writer
# has already explained is finished, and a late `on_failure` must not rewrite
# it. Named here rather than inlined because two things depend on the set
# agreeing: this handler and the reaper.
UNFINISHED_STATUSES = ("queued", "preparing", "running", "analyzing")


def _mark_simulation_failed(simulation_id: str, name: str) -> Callable[[Exception], None]:
    """`on_failure` for `spawn`: a run whose worker died must say so.

    Without this the row stays `preparing`/`running` forever and the user
    watches a spinner for a failure that was logged and never surfaced.

    **Conditional on the run still being in flight**, and it was not. This was
    a bare `.update(...).eq("id", ...)` — the only writer in this row family
    without a compare-and-set, while `website_tasks._advance`,
    `revision_tasks._advance` and the reaper's own UPDATE all have one. Two
    things went through the gap:

    - `run_simulation` writes `status='complete'` (simulation_tasks.py:1189),
      publishes, and *then* calls `reconcile_run_cost`, which makes two
      unguarded network calls. A transient PostgREST or RPC error there
      propagates to `spawn`, and this handler rewrote a run whose events,
      analysis artifact and report were all stored and correct to `failed`.
      Since `failed` is startable, the founder then paid the full price again
      for work already delivered.
    - `run_prepare_agents` refuses a run whose room has already posted with a
      sentence written for the founder to read. This handler overwrote that
      sentence with the generic one, so the founder was told to retry something
      retrying cannot fix — and clicked again, and paid for another swarm.

    The guard fixes both: a row that already carries a terminal status, or a
    `failed` with a better sentence on it, is left exactly as its writer left it.
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
        written = (
            get_supabase_admin().table("simulations").update({
                "status": "failed",
                "error_message": (
                    "This run stopped before it finished. Anything it had already "
                    "measured is saved — start a new run when you're ready, and "
                    "tell us if it happens again."
                ),
            })
            .eq("id", simulation_id)
            .in_("status", list(UNFINISHED_STATUSES))
            .execute()
        ).data or []
        if not written:
            # Not an error: the ordinary case is a worker that already closed
            # the row with a better sentence than this one. Logged because the
            # other case — a run that finished and then had its tail raise — is
            # the one worth being able to find.
            log.info(
                "simulation_failure_not_recorded",
                simulation_id=simulation_id,
                task=name,
                detail="the row was no longer in flight; its own writer's "
                       "status and sentence were left alone",
            )
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


# ---------------------------------------------------------------------------
# Interviews — the one place a caller chooses how many model calls we make
# ---------------------------------------------------------------------------
#
# Every interview is two calls on Saibyl's account (the answer, then the
# sentiment read) and **none of it is metered**: no quote, no `deduct_credits`,
# no balance check. So the only thing standing between this surface and an
# unbounded bill is the size of the fan-out, and the size of the fan-out has to
# be bounded here, at the boundary, on the request.
#
# `MAX_AGENTS_ANY_TIER` is the ceiling of `TIER_CAPS` — 1,000, at enterprise —
# and it is the right number for three reasons rather than because it is round:
#
# 1. **It is what the product needs.** A batch names agents belonging to one
#    run, and no run on any plan can hold more agents than the biggest tier
#    allows. A request naming more than that is not a large batch, it is a
#    request that cannot be about a real swarm.
# 2. **It is the ceiling the sibling routes already have.** `by-persona`
#    interviews every matching agent in the run, so its fan-out is already
#    bounded by the swarm and cannot exceed this. Capping the caller-chosen
#    route at the same number makes the request-driven path no worse than the
#    shape-driven one — anything lower would refuse a batch that `by-persona`
#    would happily run, and anything higher leaves the hole open.
# 3. **It costs no real caller anything.** The UI sends five ids
#    (`SimulationDetailPage.handleInterview` slices to 5). The cap exists for
#    the request the UI never makes.
#
# Derived, not restated: it moves when `TIER_CAPS` moves. It is a spend
# guardrail, not a per-plan entitlement — an org that downgrades must still be
# able to interview the swarm of a run it already paid for, which is why this
# is the global ceiling rather than `tier_caps(plan).max_agents`.
MAX_INTERVIEW_BATCH = MAX_AGENTS_ANY_TIER

# And a role gate on all three routes, for the half of the sentence above that
# the cap does not cover. `core/auth` states the contract plainly — "a viewer
# does neither; that is not a judgement call, it is what the word means" — and
# the interview surface broke it: three routes on `get_current_org` alone, each
# able to drive up to 2,000 model calls per request on Saibyl's account,
# repeatedly, from an account whose whole grant is to read. The cap bounds one
# request; the gate bounds who may make it.
#
# A question, not a payload. The prompt is re-sent in full to every agent in
# the batch, so its length multiplies by the fan-out — 1,000 agents × an
# unbounded string is the same defect as an unbounded id list, reached by the
# other axis. 2,000 characters is several paragraphs of question; the field
# behind it is a single-line input.
MAX_INTERVIEW_PROMPT_CHARS = 2_000


class _InterviewPromptBody(BaseModel):
    """The bound every interview request shares.

    A base class rather than `max_length` written three times: the cap that is
    restated per-route is the cap a fourth route forgets.
    """

    prompt: str = Field(min_length=1, max_length=MAX_INTERVIEW_PROMPT_CHARS)


class InterviewBody(_InterviewPromptBody):
    # A row id. 64 rather than 36 leaves room for a non-UUID key without
    # leaving room for a payload.
    agent_id: str = Field(min_length=1, max_length=64)


class BatchInterviewBody(_InterviewPromptBody):
    agent_ids: list[str]

    @field_validator("agent_ids")
    @classmethod
    def within_the_largest_possible_swarm(cls, v: list[str]) -> list[str]:
        # Deduplicated before counting, and the order the caller sent is kept.
        # `interview_batch` resolves ids with a single `IN (…)`, so repeats
        # already collapse to one agent and one pair of model calls — counting
        # them against the cap would refuse a harmless client bug while letting
        # the expensive case (many *distinct* ids) sit at the same number.
        unique = list(dict.fromkeys(id_.strip() for id_ in v if id_.strip()))
        if not unique:
            raise ValueError("Choose at least one person to ask.")
        if len(unique) > MAX_INTERVIEW_BATCH:
            raise ValueError(
                f"You can ask up to {MAX_INTERVIEW_BATCH:,} people at once, and "
                f"this asks {len(unique):,}. Pick the ones you want to hear "
                f"from, or ask a whole persona group instead."
            )
        return unique


class PersonaInterviewBody(_InterviewPromptBody):
    # Matched against a profile field, never sent to a model, so the bound is
    # hygiene rather than spend control — but an unbounded string that nothing
    # needs is an allowance nobody chose to make.
    persona_type: str = Field(min_length=1, max_length=200)


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
    project = maybe_one(
        admin.table("projects")
        .select("id")
        .eq("id", body.project_id)
        .eq("organization_id", auth["org_id"])
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


#: Spellings that all mean "this run is over and it worked".
#:
#: The column has carried both since before the rename and neither was
#: backfilled, so a status filter that matched one of them would hide half the
#: finished runs in an account. Mirrors ``RUN_DONE`` in
#: ``frontend/src/lib/status.ts``.
_FINISHED_SPELLINGS = ("complete", "completed")


def _escape_like(value: str) -> str:
    """Make ``value`` a literal in a PostgREST ``ilike`` pattern.

    ``%`` and ``_`` are wildcards, so a founder searching for a run named
    ``Q3_pricing`` would otherwise match ``Q3-pricing`` and ``Q3xpricing`` too —
    a wrong answer rather than an unsafe one, but a wrong answer that looks
    right.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("")
async def list_simulations(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    project_id: str | None = Query(None),
    search: str | None = Query(None, max_length=200),
    status: str | None = Query(None, max_length=40),
    auth: dict = Depends(get_current_org),
):
    """List simulations (paginated; optionally filtered by product, name or state).

    ``search`` and ``status`` are applied **here**, not by the caller.

    They used to be applied in the browser, to whichever twenty rows the current
    page happened to hold, while the pager reported the server's count of
    everything. So searching for a run that sat on page 2 answered "Nothing
    matches what you have filtered to" — a confident false statement about the
    account, produced by filtering one page and counting all of them. Filtering
    and counting have to happen in the same place, and this is the only place
    that can see every row.
    """
    # FastAPI substitutes the declared default on a real request. A **direct
    # call** does not — and this module is tested by calling its endpoints
    # directly — so an omitted parameter arrives as the `Query(...)` object
    # itself, which is truthy. A naive `if search:` therefore filtered on a
    # sentinel and raised `'Query' object has no attribute 'strip'`.
    #
    # `project_id` has carried the same hazard since it was added; it only
    # never fired because every existing caller passes it explicitly. Both are
    # normalised here rather than guarded at each use, so the next parameter
    # added to this signature inherits the fix instead of the bug.
    product = project_id if isinstance(project_id, str) else None
    name_query = search.strip() if isinstance(search, str) else ""
    state = status.strip() if isinstance(status, str) else ""

    log.info(
        "list_simulations",
        org_id=auth["org_id"],
        limit=limit,
        offset=offset,
        project_id=product,
        has_search=bool(name_query),
        status=state or None,
    )
    admin = get_supabase_admin()
    query = (
        admin.table("simulations")
        .select("*", count="exact")
        .eq("organization_id", auth["org_id"])
    )
    if product:
        query = query.eq("project_id", product)
    if name_query:
        query = query.ilike("name", f"%{_escape_like(name_query)}%")
    if state:
        # `count="exact"` is applied to the filtered set, so the pager counts
        # the same rows the founder is looking at.
        if state in _FINISHED_SPELLINGS:
            query = query.in_("status", list(_FINISHED_SPELLINGS))
        else:
            query = query.eq("status", state)
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
    result = maybe_one(
        admin.table("simulations")
        .select("*")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return result.data


@router.delete("/{id}")
async def delete_simulation(id: str, auth: dict = Depends(require_can_destroy)):
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

    # Re-simulations are refused, not silently orphaned.
    #
    # Two foreign keys made routine tidying destructive in a way nothing said
    # out loud (021_inoculation_loop.sql):
    #
    #   inoculation_results.parent_simulation_id  ON DELETE CASCADE
    #   simulations.parent_simulation_id          ON DELETE SET NULL
    #
    # So deleting a completed parent cascaded away the stored before/after the
    # founder paid for — after which `GET /api/inoculation/{child}/result`
    # answers "This run is not a re-simulation" for an artifact that exists
    # nowhere else — and nulled the child's link, which `start_simulation` used
    # to derive `reuse_agents` from. That link is now only half the derivation
    # (see below), but the deleted comparison cannot be rebuilt at all: it is
    # measured from two artifacts, and one of them is being deleted here.
    #
    # This is the flagship V3 path — the website-room "prove" leg and the
    # inoculation loop both create parent/child pairs — so it is reached by
    # tidying an old run, not by anything unusual.
    #
    # Refused rather than warned. The two sibling delete routes written for
    # this problem (`icp.py`'s `orphaned_pack_ids`, `packs.py`'s
    # `detached_simulation_ids`) report what they broke because a detached pack
    # is recoverable; a cascaded `inoculation_results` row is not. The founder
    # is told which runs to delete first, which is a step they can take.
    children = (
        admin.table("simulations")
        .select("id, name")
        .eq("parent_simulation_id", id)
        .eq("organization_id", auth["org_id"])
        .limit(50)
        .execute()
    ).data or []
    if children:
        log.warning(
            "delete_refused_has_resimulations",
            simulation_id=id,
            org_id=auth["org_id"],
            children=[c["id"] for c in children],
        )
        names = ", ".join(str(c.get("name") or c["id"]) for c in children)
        raise HTTPException(
            status_code=409,
            detail=(
                f"This run is the 'before' for {len(children)} re-simulation(s) "
                f"({names}). Deleting it would destroy the before/after "
                f"comparison you paid for, and that cannot be rebuilt. Delete "
                f"the re-simulation(s) first if you really want this gone."
            ),
        )

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


# The statuses a run may legitimately be prepared from.
#
# `draft` is a run that has never been prepared; `failed` is one whose earlier
# preparation died and which the founder is retrying. Everything else — a run
# already `preparing`, one sitting `ready` with its swarm built, one that has
# run — is refused, because preparing again does not replace the swarm, it adds
# a second one.
PREPARABLE_STATUSES = ("draft", "failed")

# The statuses a run may legitimately be started from — the same set that
# already reached the deduction, since `preparing`, `draft` and `running` are
# refused by name higher up in `start_simulation`. `analyzing` is deliberately
# absent: a run in its analysis pass is in flight, and starting it again is the
# duplicate charge this list exists to prevent.
STARTABLE_STATUSES = ("ready", "complete", "completed", "failed", "stopped")


@router.post("/{id}/prepare")
async def prepare_simulation(id: str, auth: dict = Depends(require_can_spend)):
    """Trigger agent preparation for a simulation.

    **Gated, and single-use.** This route had neither. It checked that the run
    belonged to the org and nothing else — not its status, not whether it
    already had agents — while `run_prepare_agents` makes one `llm_fast` call
    per agent, up to 1,000 at enterprise. So a viewer could fire it, and a
    double-click on a prepared 100-agent run spent another 100 uncharged model
    calls and then either tripped migration 019's unique username index (whose
    failure handler marks a run that was prepared and fine as "stopped before it
    finished") or, where 019 is not yet applied, inserted a **second full
    swarm** with colliding handles — the run then executing with twice the
    agents it was quoted for and every confidence interval drawn from a swarm of
    the wrong size.

    The claim is a compare-and-set on `status` rather than a read-then-write:
    two clicks land in the same event-loop window, and a plain read would let
    both through.
    """
    log.info("prepare_simulation", simulation_id=id, org_id=auth["org_id"])
    admin = get_supabase_admin()
    sim = maybe_one(
        admin.table("simulations")
        .select("id, status")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
    )
    if not sim.data:
        raise HTTPException(status_code=404, detail="Simulation not found")

    claimed = (
        admin.table("simulations")
        # `updated_at` is stamped, not left to the trigger. The reaper measures
        # this run's 90-minute budget from it (see `StuckRule.age_column`), and
        # a run may have rested at `draft` for a day before this moment — so
        # the one write that means "the work starts now" says so itself rather
        # than depending on migration 008 being present.
        .update({"status": "preparing", "updated_at": _now_iso()})
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
        .in_("status", list(PREPARABLE_STATUSES))
        .execute()
    ).data or []
    if not claimed:
        current = str(sim.data.get("status") or "")

        # **Already prepared is success, not conflict.** The compare-and-set
        # exists to stop a second room being built, and a run at `ready` has
        # exactly the room it should — so refusing it protects nothing and
        # breaks the one control the founder uses.
        #
        # The Start button posts `/prepare` and then `/start` unconditionally,
        # and it renders for draft, ready and failed. Answering 409 on `ready`
        # meant the frontend's catch fired and `/start` was never called: a
        # prepared run could not be started at all from the primary button.
        # The guard was added to one side of a two-call contract without the
        # other side being looked at.
        if current == "ready":
            log.info(
                "prepare_noop_already_ready",
                simulation_id=id, org_id=auth["org_id"],
            )
            return {"status": "ready", "detail": "The room is already built."}

        log.warning(
            "prepare_refused_not_preparable",
            simulation_id=id, org_id=auth["org_id"], status=current,
        )
        raise HTTPException(
            status_code=409,
            detail=(
                "This run's people are already being built. Wait for status "
                "'ready' and start the run — preparing it again would build a "
                "second room."
            ),
        )

    spawn(
        run_prepare_agents(id), "prepare_agents",
        on_failure=_mark_simulation_failed(id, "prepare_agents"),
    )
    return {"status": "started"}


@router.post("/{id}/start")
async def start_simulation(
    id: str,
    body: StartSimulationBody | None = None,
    auth: dict = Depends(require_can_spend),
):
    """Start running a simulation, redeeming its quote."""
    log.info("start_simulation", simulation_id=id, org_id=auth["org_id"])
    admin = get_supabase_admin()
    sim = maybe_one(
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

    # No monthly quota check. It was derived from the subscription tier's
    # grant, and tiers were removed on 2026-08-25 (PRD_V3 §6) — credits are the
    # only ration. `check_credit_budget` immediately below is the gate, and it
    # answers with the actual shape of this run rather than a monthly count.

    from app.services.billing.agent_pricing import check_credit_budget, deduct_credits
    from app.services.billing.run_quote import QuoteError, consume_quote

    agent_count = sim.data.get("agent_count") or 1
    max_rounds = sim.data.get("max_rounds") or 10
    platforms = len(sim.data.get("platforms") or ["twitter_x"])
    variants = sim.data.get("variants") or 1
    # An inoculation re-simulation copies its parent's agents rather than
    # generating them, so it makes zero generation calls and must not be
    # charged for them.
    #
    # **Not derived from `parent_simulation_id` alone.** That column is
    # `ON DELETE SET NULL` (021_inoculation_loop.sql:86), so deleting the parent
    # rewrote this run's price: `estimate_simulation_cost(100, 5, 2, 1,
    # inoculation_assets=2)` is 2,681 credits with `reuse_agents=True` and 2,996
    # without — 315 credits, 11.7%, for an `agent_generation` stage that
    # provably never executes, since the child's agents are copied rows that
    # already exist.
    #
    # `inoculation_asset_ids` is the child's own state and survives the parent:
    # `NOT NULL DEFAULT '{}'` on every ordinary run, and non-empty on every
    # re-simulation because `ResimulateBody.asset_ids` is `min_length=1`.
    # Either fact alone is enough to know this run will not generate a swarm.
    inoculation_asset_ids = sim.data.get("inoculation_asset_ids") or []
    reuse_agents = bool(sim.data.get("parent_simulation_id")) or bool(
        inoculation_asset_ids
    )
    # It does, however, carry its assets in every single action prompt. Measured
    # at 5.3x the parent's action input on the first live loop — the saving on
    # generation and the surcharge on actions are separate facts, and quoting
    # only the first one under-charged the re-simulation by roughly a fifth.
    inoculation_assets = len(inoculation_asset_ids)
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
        credits_to_charge = quote.credits
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
        credits_to_charge = budget.credits_required

    # The single-use guard, and the reason it is a compare-and-set.
    #
    # The quote path has one already — `load_quote` refuses a quote whose
    # `consumed_at` is set — and the no-quote branch above had **nothing**: it
    # checked the budget and deducted, with the plain read at the top of this
    # handler as its only protection and the database status not written until
    # `run_simulation` runs inside the spawned task. Two POSTs landing in the
    # same event-loop window (a double-click, or a client retry on a slow
    # response — this handler awaits `check_simulation_quota` over the network
    # before deducting) each deducted ~17,000 credits and each spawned an engine
    # on the same run. Two engines writing into one `simulation_events` doubles
    # every count and draws `mean_interval`'s bands from duplicated
    # observations.
    #
    # And re-simulations are *forced* onto that branch: the 409 above refuses a
    # `quote_id` on a run with a `parent_simulation_id`, which is the
    # inoculation loop and the website-room "prove" leg — the flagship V3 flow.
    #
    # Placed immediately before the deduction so no earlier refusal (402, a
    # QuoteError) can leave a run claimed and unstarted.
    started = (
        admin.table("simulations")
        # `updated_at`, for the same reason as `/prepare`: this is the instant
        # the run's own 90-minute reaper budget begins, and the row it is
        # written on may have been created a day ago in the wizard. Aged from
        # `created_at` the deduction below was followed within one sweep by a
        # `failed` row and no refund.
        .update({"status": "running", "updated_at": _now_iso()})
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
        .in_("status", list(STARTABLE_STATUSES))
        .execute()
    ).data or []
    if not started:
        log.warning(
            "start_refused_already_started",
            simulation_id=id, org_id=auth["org_id"], status=current_status,
        )
        raise HTTPException(
            status_code=409,
            detail="This run has already been started.",
        )

    deduct_credits(auth["org_id"], credits_to_charge)

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
    sim = maybe_one(
        admin.table("simulations")
        .select("id")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
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
    sim = maybe_one(
        admin.table("simulations")
        .select("id")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
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
    sim = maybe_one(
        admin.table("simulations")
        .select("id")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
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
    sim = maybe_one(
        admin.table("simulations")
        .select("id")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
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
async def interview_agent_endpoint(id: str, body: InterviewBody, auth: dict = Depends(require_can_spend)):
    """Interview a single agent."""
    log.info("interview_agent", simulation_id=id, agent_id=body.agent_id)
    admin = get_supabase_admin()
    sim = maybe_one(
        admin.table("simulations")
        .select("id")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
    )
    if not sim.data:
        raise HTTPException(status_code=404, detail="Simulation not found")

    result = await interview_agent(id, body.agent_id, body.prompt)
    return result.model_dump()


@router.post("/{id}/interview/batch")
async def interview_batch_endpoint(id: str, body: BatchInterviewBody, auth: dict = Depends(require_can_spend)):
    """Interview multiple agents."""
    log.info("interview_batch", simulation_id=id, count=len(body.agent_ids))
    admin = get_supabase_admin()
    sim = maybe_one(
        admin.table("simulations")
        .select("id")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
    )
    if not sim.data:
        raise HTTPException(status_code=404, detail="Simulation not found")

    results = await interview_batch(id, body.agent_ids, body.prompt)
    return [r.model_dump() for r in results]


@router.post("/{id}/interview/by-persona")
async def interview_by_persona_endpoint(id: str, body: PersonaInterviewBody, auth: dict = Depends(require_can_spend)):
    """Interview all agents of a specific persona type.

    **No request-side cap here, deliberately.** The sibling batch route needs
    one because the caller names the agents; this one interviews whichever
    agents of this run happen to carry the persona, so its fan-out is the run's
    own swarm — already bounded by `TIER_CAPS`, already paid for, and never
    larger than `MAX_INTERVIEW_BATCH`. A cap on `persona_type` would bound
    nothing a caller controls.
    """
    log.info("interview_by_persona", simulation_id=id, persona_type=body.persona_type)
    admin = get_supabase_admin()
    sim = maybe_one(
        admin.table("simulations")
        .select("id")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
    )
    if not sim.data:
        raise HTTPException(status_code=404, detail="Simulation not found")

    results = await interview_by_persona_type(id, body.persona_type, body.prompt)
    return [r.model_dump() for r in results]
