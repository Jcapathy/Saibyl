from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import get_current_org, require_can_destroy, require_can_spend
from app.core.database import get_supabase_admin

log = structlog.get_logger()

router = APIRouter(tags=["inoculation"])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class DraftBody(BaseModel):
    """Which objections to write assets against.

    Empty means the run's most load-bearing objections, capped by
    `MAX_OBJECTIONS_TO_DRAFT`. Ranking is by reach x intensity x cohort spread,
    not raw frequency — the loudest objection and the one that kills the deal
    are usually different objections.
    """

    objection_keys: list[str] = Field(default_factory=list)


class UpdateAssetBody(BaseModel):
    """A founder's edit to a drafted asset.

    The body is what agents will read verbatim in the re-simulation, so an edit
    here changes the experiment, not the presentation.
    """

    title: str | None = None
    body: str | None = None
    hypothesis: str | None = None
    asset_type: (
        Literal[
            "disclosure", "roadmap", "pricing_rationale", "security_page",
            "migration_guide", "faq_entry", "comparison_page",
        ]
        | None
    ) = None


class ResimulateBody(BaseModel):
    asset_ids: list[str] = Field(min_length=1)
    name: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _verify_simulation(simulation_id: str, org_id: str) -> dict:
    admin = get_supabase_admin()
    sim = (
        admin.table("simulations")
        .select("id, name, status, parent_simulation_id")
        .eq("id", simulation_id)
        .eq("organization_id", org_id)
        .execute()
    )
    if not sim.data:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return sim.data[0]


# ---------------------------------------------------------------------------
# Draft
# ---------------------------------------------------------------------------

@router.post("/{simulation_id}/assets")
async def draft(
    simulation_id: str,
    body: DraftBody | None = None,
    auth: dict = Depends(require_can_spend),
):
    """Draft counter-assets for this run's load-bearing objections."""
    from app.services.billing.agent_pricing import (
        check_inoculation_draft_budget,
        deduct_credits,
    )
    from app.services.intelligence.inoculation import draft_assets

    log.info("inoculation_draft", simulation_id=simulation_id, org_id=auth["org_id"])
    _verify_simulation(simulation_id, auth["org_id"])

    budget = check_inoculation_draft_budget(auth["org_id"])
    if not budget.allowed:
        raise HTTPException(status_code=402, detail=budget.message)

    try:
        assets = await draft_assets(
            simulation_id,
            auth["org_id"],
            (body.objection_keys if body else None) or None,
            created_by=auth["user"]["id"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    deduct_credits(auth["org_id"], budget.credits_required)
    return assets


@router.get("/{simulation_id}/assets")
async def list_assets(simulation_id: str, auth: dict = Depends(get_current_org)):
    """Assets drafted against this run's objections."""
    _verify_simulation(simulation_id, auth["org_id"])
    admin = get_supabase_admin()
    return (
        admin.table("inoculation_assets")
        .select("*")
        .eq("simulation_id", simulation_id)
        .eq("organization_id", auth["org_id"])
        .order("created_at")
        .execute()
    ).data


@router.patch("/assets/{asset_id}")
async def update_asset(
    asset_id: str,
    body: UpdateAssetBody,
    auth: dict = Depends(get_current_org),
):
    """Edit a drafted asset before testing it."""
    admin = get_supabase_admin()
    existing = (
        admin.table("inoculation_assets")
        .select("id, status")
        .eq("id", asset_id)
        .eq("organization_id", auth["org_id"])
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Asset not found")
    if existing.data[0]["status"] == "tested":
        # Editing a tested asset would leave a stored result describing copy
        # that no longer exists — the before/after would be attributed to text
        # nobody can read. Draft a new asset instead.
        raise HTTPException(
            status_code=409,
            detail=(
                "This asset has already been tested in a re-simulation. Editing "
                "it would leave the stored result describing copy that no longer "
                "exists. Draft a new asset instead."
            ),
        )

    updates = {
        k: v for k, v in body.model_dump(exclude_none=True).items()
    }
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")
    updates["edited_by_user"] = True
    updates["updated_at"] = datetime.now(UTC).isoformat()

    return (
        admin.table("inoculation_assets")
        .update(updates)
        .eq("id", asset_id)
        .eq("organization_id", auth["org_id"])
        .execute()
    ).data[0]


@router.delete("/assets/{asset_id}")
async def delete_asset(asset_id: str, auth: dict = Depends(require_can_destroy)):
    admin = get_supabase_admin()
    admin.table("inoculation_assets").delete().eq("id", asset_id).eq(
        "organization_id", auth["org_id"]
    ).execute()
    return {"status": "deleted", "id": asset_id}


@router.get("/draft-estimate")
async def draft_estimate(auth: dict = Depends(get_current_org)):
    """What one drafting pass costs, before committing to it."""
    from app.services.billing.agent_pricing import check_inoculation_draft_budget

    return check_inoculation_draft_budget(auth["org_id"]).model_dump()


# ---------------------------------------------------------------------------
# Re-simulate
# ---------------------------------------------------------------------------

@router.post("/{simulation_id}/resimulate")
async def resimulate(
    simulation_id: str,
    body: ResimulateBody,
    auth: dict = Depends(get_current_org),
):
    """Clone this run with the chosen assets pre-positioned.

    Returns a simulation in status `ready` — its agents are copies of the
    parent's, so there is nothing to prepare. Start it through the normal
    `POST /api/simulations/{id}/start`, which quotes and charges it like any
    other run, minus the agent generation it provably does not perform.
    """
    from app.services.intelligence.inoculation import create_resimulation

    log.info(
        "inoculation_resimulate",
        simulation_id=simulation_id,
        assets=len(body.asset_ids),
        org_id=auth["org_id"],
    )
    _verify_simulation(simulation_id, auth["org_id"])

    try:
        return create_resimulation(
            simulation_id,
            auth["org_id"],
            body.asset_ids,
            created_by=auth["user"]["id"],
            name=body.name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Prove
# ---------------------------------------------------------------------------

@router.get("/{simulation_id}/result")
async def result(simulation_id: str, auth: dict = Depends(get_current_org)):
    """The before/after comparison for a completed re-simulation.

    `simulation_id` is the **child** — the run that was inoculated. The result
    is built automatically when that run completes; this only reads it.
    """
    from app.services.intelligence.inoculation import get_inoculation_result

    sim = _verify_simulation(simulation_id, auth["org_id"])
    if not sim.get("parent_simulation_id"):
        raise HTTPException(
            status_code=400,
            detail=(
                "This run is not a re-simulation, so there is nothing to compare "
                "it against. Pass the id of the inoculated run, not the original."
            ),
        )

    stored = get_inoculation_result(simulation_id)
    if not stored:
        raise HTTPException(
            status_code=404,
            detail=(
                "No comparison has been built for this run yet. It is built when "
                "the re-simulation completes."
            ),
        )
    return stored


@router.post("/{simulation_id}/result/rebuild")
async def rebuild_result(simulation_id: str, auth: dict = Depends(get_current_org)):
    """Rebuild the comparison from the two stored artifacts.

    Free: it reads two artifacts and makes no model calls. Exists because the
    comparison is derived data built at the end of a long-running task, and a
    task that dies after the run completes should not cost a second run to
    recover from.
    """
    from app.services.intelligence.inoculation import measure_inoculation

    sim = _verify_simulation(simulation_id, auth["org_id"])
    parent_id = sim.get("parent_simulation_id")
    if not parent_id:
        raise HTTPException(
            status_code=400, detail="This run is not a re-simulation."
        )

    result = await measure_inoculation(parent_id, simulation_id, auth["org_id"])
    return result.model_dump(mode="json")
