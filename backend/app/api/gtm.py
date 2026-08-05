"""Go-to-market candidate discovery.

Route order in this module is load-bearing. Every static path (`/settings`,
`/estimate`, `/discover`, `/purge`, `/runs`, `/candidates`) is registered before
any parameterised one, because a static path shadowed by `/{id}` has shipped
twice in this codebase and both times reached Postgres as an invalid UUID cast —
a 500 that reads as a server fault rather than a routing bug.
`tests/test_api_guards.py::test_no_static_route_anywhere_is_shadowed_by_a_parameterised_one`
scans the whole app for it.

Both list endpoints return `{items, total}` rather than a bare array. `GET
/simulations` returning a bare array meant a user with 50 rows could never reach
page 2, and the frontend now has one `unwrapList` helper that expects the
envelope.
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.auth import get_current_org
from app.core.database import get_supabase_admin
from app.services.gtm import store
from app.services.gtm.discovery import (
    DiscoveryRefusedError,
    DiscoveryUnavailableError,
    preview_queries,
    reconcile_run,
    run_discovery,
)
from app.services.gtm.pricing import (
    check_discovery_budget,
    estimate_discovery_cost,
    reconcile_discovery_charge,
)
from app.services.gtm.privacy import (
    ContactGateUnavailableError,
    contact_discovery_gate,
    set_contact_discovery,
)
from app.services.gtm.query_compiler import MAX_QUERIES_PER_DISCOVERY

log = structlog.get_logger()

router = APIRouter(tags=["gtm"])

MAX_PAGE_SIZE = 100


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class DiscoverBody(BaseModel):
    icp_profile_id: str
    # Fewer queries costs less and covers less of the ICP. Capped server-side;
    # a client asking for more gets the cap, not an error.
    max_queries: int = Field(default=MAX_QUERIES_PER_DISCOVERY, ge=1)


class ContactSettingBody(BaseModel):
    enabled: bool


class PurgeBody(BaseModel):
    """Purge is irreversible, so it takes an explicit confirmation.

    Not a UI concern pushed into the API: this endpoint deletes rows, and a
    client that calls it by accident has no way to undo it.
    """

    confirm: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _with_delivery(run: dict | None) -> dict | None:
    """Attach what this run asked for, delivered, and actually cost.

    Every run row leaves this module through here, so no screen can render a
    charge without the delivery beside it. Computed on read rather than stored:
    `queries_completed`, `queries_empty` and `credits_charged` are already on the
    row, and a stored summary is a second copy of the same facts that can drift
    from them.

    `sentence` is written here rather than in the client because it is the one
    place that knows both halves of the arithmetic. A founder should not have to
    subtract two numbers to find out whether they were charged for work that
    never happened.
    """
    if run is None:
        return None

    delivery = reconcile_discovery_charge(run)
    refunded = int(run.get("credits_refunded") or 0)
    settled = run.get("refunded_at") is not None
    net = delivery.credits_charged - refunded

    if delivery.queries_delivered >= delivery.queries_requested:
        sentence = (
            f"All {delivery.queries_requested} searches ran. "
            f"You were charged {net:,} credits."
        )
    elif refunded > 0:
        sentence = (
            f"{delivery.queries_delivered} of {delivery.queries_requested} searches "
            f"ran. You were charged for the {delivery.queries_delivered} that ran — "
            f"{refunded:,} credits for the rest have been put back on your balance, "
            f"so this search cost you {net:,} credits."
        )
    elif settled:
        sentence = (
            f"{delivery.queries_delivered} of {delivery.queries_requested} searches "
            f"ran, and this run was charged {net:,} credits."
        )
    else:
        # Not yet reconciled — a run still in flight, or one whose refund could
        # not be attempted. Says what is owed rather than implying it has been
        # paid, because claiming a refund that has not happened is worse than
        # the missing refund.
        sentence = (
            f"{delivery.queries_delivered} of {delivery.queries_requested} searches "
            f"have finished. {delivery.credits_refundable:,} credits for the rest "
            f"are still to be put back."
            if delivery.credits_refundable > 0
            else f"{delivery.queries_delivered} of {delivery.queries_requested} "
                 f"searches have finished."
        )

    return {
        **run,
        "delivery": {
            "queries_requested": delivery.queries_requested,
            "queries_delivered": delivery.queries_delivered,
            "credits_charged": delivery.credits_charged,
            "credits_refunded": refunded,
            "credits_net": net,
            "credits_refundable": 0 if settled else delivery.credits_refundable,
            "reconciled": settled,
            "sentence": sentence,
        },
    }


def _fetch_profile(profile_id: str, org_id: str) -> dict:
    admin = get_supabase_admin()
    row = (
        admin.table("icp_profiles")
        .select("*")
        .eq("id", profile_id)
        .eq("organization_id", org_id)
        .execute()
    )
    if not row.data:
        raise HTTPException(status_code=404, detail="ICP profile not found")
    return row.data[0]


# ---------------------------------------------------------------------------
# Static routes — registered before anything parameterised
# ---------------------------------------------------------------------------

@router.get("/settings")
async def get_settings(auth: dict = Depends(get_current_org)):
    """The org's contact-discovery setting.

    A failed read is a 503, never a `false`. An unreadable setting and a
    deliberate opt-out are different facts, and a UI that renders one as the
    other would show "off" to an org that had turned it on.
    """
    try:
        gate = contact_discovery_gate(auth["org_id"])
    except ContactGateUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "contact_discovery_enabled": gate.enabled,
        # Stated in the payload so the frontend does not have to encode the
        # policy, and so a reader of the API sees what "off" means.
        "note": (
            "Company discovery works with this off. Turning it on lets Saibyl "
            "store named people — public professional information only — with "
            "the source and retrieval time of every record."
        ),
    }


@router.patch("/settings")
async def update_settings(
    body: ContactSettingBody,
    auth: dict = Depends(get_current_org),
):
    """Turn contact discovery on or off.

    Turning it off stops future collection. It does not delete what was already
    collected — that is `POST /purge`, deliberately separate.
    """
    try:
        gate = set_contact_discovery(
            auth["org_id"], body.enabled, actor_user_id=auth["user"]["id"]
        )
    except ContactGateUnavailableError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"contact_discovery_enabled": gate.enabled}


@router.get("/estimate")
async def estimate(
    icp_profile_id: str = Query(...),
    max_queries: int = Query(default=MAX_QUERIES_PER_DISCOVERY, ge=1),
    auth: dict = Depends(get_current_org),
):
    """What this discovery would search for, and what it would cost.

    Returns the compiled queries themselves. The compiler is deterministic, so
    these are exactly the searches that will run — which makes this the screen
    where a founder who has never heard the phrase "ICP" can see, in plain
    words, what the product is about to go and look for.
    """
    profile_row = _fetch_profile(icp_profile_id, auth["org_id"])
    try:
        queries = preview_queries(profile_row, max_queries=max_queries)
    except DiscoveryUnavailableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    cost = estimate_discovery_cost(len(queries))
    budget = check_discovery_budget(auth["org_id"], len(queries))
    return {
        "queries": [q.model_dump(mode="json") for q in queries],
        "estimate": cost.model_dump(),
        "budget": budget.model_dump(),
    }


@router.post("/discover")
async def discover(body: DiscoverBody, auth: dict = Depends(get_current_org)):
    """Find real companies for one ICP.

    Runs inline. Background jobs in this codebase are not durable — no queue, no
    worker, every job an `asyncio.create_task` in the API process — so detaching
    this would trade a wait for a class of silent failure. It is bounded: at
    most `MAX_QUERIES_PER_DISCOVERY` queries, four in flight, and a hard
    deadline after which the run closes `partial` with whatever it already
    stored. `services/gtm/discovery.py` states the failure behaviour in full.

    Credits are charged before the first search, like a run, and a 402 here
    means nothing was spent and no run row was created.
    """
    profile_row = _fetch_profile(body.icp_profile_id, auth["org_id"])
    log.info(
        "gtm_discover_requested",
        project_id=profile_row["project_id"],
        org_id=auth["org_id"],
        icp_profile_id=body.icp_profile_id,
    )
    try:
        run = await run_discovery(
            profile_row["project_id"],
            auth["org_id"],
            profile_row,
            max_queries=body.max_queries,
            created_by=auth["user"]["id"],
        )
    except DiscoveryRefusedError as exc:
        raise HTTPException(status_code=402, detail=exc.budget.message) from exc
    except DiscoveryUnavailableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _with_delivery(run)


@router.post("/purge")
async def purge(body: PurgeBody, auth: dict = Depends(get_current_org)):
    """Delete every candidate and contact this org holds.

    Rows are deleted, not flagged. Discovery runs survive, stamped `purged_at`:
    they hold queries, counts and spend — the billing record that reconciles
    against `llm_usage` — and none of that is personal data.
    """
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="Set confirm=true. This deletes every candidate and contact "
                   "for the organization and cannot be undone.",
        )
    log.info("gtm_purge_requested", org_id=auth["org_id"], actor=auth["user"]["id"])
    return {"status": "purged", **store.purge_organization(auth["org_id"])}


@router.get("/runs")
async def list_runs(
    project_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    auth: dict = Depends(get_current_org),
):
    items, total = store.list_runs(
        auth["org_id"], project_id=project_id, limit=limit, offset=offset
    )
    return {"items": [_with_delivery(run) for run in items], "total": total}


@router.get("/candidates")
async def list_candidates(
    project_id: str | None = Query(default=None),
    discovery_run_id: str | None = Query(default=None),
    archetype_id: str | None = Query(default=None),
    min_score: float | None = Query(default=None, ge=0, le=1),
    search: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    auth: dict = Depends(get_current_org),
):
    """Candidates, filtered and paged. `{items, total}`.

    The list view carries no evidence quotes and no contacts — `total` is the
    count before paging, so page 2 is reachable, and personal data stays out of
    the query that renders a grid. `GET /candidates/{id}` returns both.
    """
    items, total = store.list_candidates(
        auth["org_id"],
        project_id=project_id,
        discovery_run_id=discovery_run_id,
        archetype_id=archetype_id,
        min_score=min_score,
        search=search,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "total": total}


# ---------------------------------------------------------------------------
# Parameterised routes
# ---------------------------------------------------------------------------

@router.get("/runs/{id}")
async def get_run(id: str, auth: dict = Depends(get_current_org)):
    run = store.get_run(id, auth["org_id"])
    if run is None:
        raise HTTPException(status_code=404, detail="Discovery run not found")
    return _with_delivery(run)


@router.post("/runs/{id}/reconcile")
async def reconcile(id: str, auth: dict = Depends(get_current_org)):
    """Settle this run's charge against what it delivered.

    `run_discovery` already does this as it closes, so this exists for the runs
    that closed before it did, and for the case where the refund could not be
    attempted at the time (`gtm_refund_unavailable` in the logs — usually a
    migration not yet applied).

    **Safe to call repeatedly.** The refund is claimed by a compare-and-set in
    `refund_discovery_credits`, so a retry, a double callback, or two clients
    pressing this at once credit the balance exactly once between them. That is
    also why this is not a 409 on an already-settled run: the caller asked for
    the run to be settled, and it is.
    """
    run = store.get_run(id, auth["org_id"])
    if run is None:
        raise HTTPException(status_code=404, detail="Discovery run not found")
    if run.get("status") == "running":
        raise HTTPException(
            status_code=409,
            detail="This search is still running. It settles itself when it finishes.",
        )
    return _with_delivery(reconcile_run(run))


@router.get("/candidates/{id}")
async def get_candidate(id: str, auth: dict = Depends(get_current_org)):
    """One candidate with the evidence behind every field, and any contacts.

    Each evidence entry names the field it supports, the URL it came from and
    the text that supports it. A field absent from `evidence` is null on the
    record — no source stated it, and nothing estimated one.
    """
    candidate = store.get_candidate(id, auth["org_id"])
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


@router.delete("/candidates/{id}")
async def delete_candidate(id: str, auth: dict = Depends(get_current_org)):
    """Delete one candidate and every contact attached to it. Rows, not flags."""
    removed = store.delete_candidate(id, auth["org_id"])
    if removed is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {"status": "deleted", **removed}
