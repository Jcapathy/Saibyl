"""USPTO clearance runs (PRD_V3 §11): "is this even mine to build?"

A founder submits a name, an invention description, or both, and gets a tiered
clearance report — trademarks, prior art, the pending landscape. The run is
created here, charged here, and executed by `workers.clearance_tasks`; the
methodology lives in the clearance services, not in this module.

Route order is load-bearing: the static list path is registered before
`/{run_id}`, because a static path shadowed by a parameterised one has shipped
twice in this codebase.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, time
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app.core.auth import get_current_org
from app.core.config import settings
from app.core.database import get_supabase_admin
from app.core.tasks import spawn
from app.services.billing.agent_pricing import (
    clearance_credits,
    deduct_credits,
    get_credit_balance,
)
from app.workers.clearance_tasks import run_clearance

log = structlog.get_logger()

router = APIRouter(tags=["clearance"])

# QUICK runs are free, so the balance rations nothing here — this cap is what
# stands between the free teaser and a script hammering the USPTO on our keys.
QUICK_RUNS_PER_DAY = 5

LIST_LIMIT = 50


def _mark_clearance_failed(run_id: str, name: str) -> Callable[[Exception], None]:
    """`on_failure` for `spawn`: a run whose worker died must say so.

    Without this the row stays `queued`/`running` forever and the founder
    watches a spinner for a failure that was logged and never surfaced.
    """
    def _mark(exc: Exception) -> None:
        get_supabase_admin().table("clearance_runs").update({
            "status": "failed",
            "error_message": f"[{name}] {type(exc).__name__}: {exc}",
        }).eq("id", run_id).execute()
    return _mark


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class CreateClearanceBody(BaseModel):
    project_id: str | None = None
    item: str = Field(min_length=1, max_length=4000)
    type_hint: Literal["name", "invention", "both"] | None = None
    field: str | None = Field(default=None, max_length=200)
    competitors: list[str] = Field(default_factory=list, max_length=10)
    tier: Literal["QUICK", "STANDARD", "COMPREHENSIVE"] = "QUICK"

    @field_validator("item")
    @classmethod
    def item_has_substance(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Tell us the name or invention to check.")
        return v

    @field_validator("competitors")
    @classmethod
    def competitors_are_names(cls, v: list[str]) -> list[str]:
        cleaned = [c.strip() for c in v if c.strip()]
        for name in cleaned:
            if len(name) > 200:
                raise ValueError("Keep each competitor name under 200 characters.")
        return cleaned


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("")
async def create_clearance_run(
    body: CreateClearanceBody, auth: dict = Depends(get_current_org)
):
    """Create a clearance run, charge it, and hand it to the worker."""
    log.info(
        "create_clearance_run",
        org_id=auth["org_id"],
        tier=body.tier,
        item=body.item[:80],
    )

    # Guarded before anything is created or charged: a run row for a search
    # that can never execute is a spinner with no ending, and a deducted credit
    # for it is worse.
    if not (getattr(settings, "uspto_odp_api_key", "") or "").strip():
        raise HTTPException(
            status_code=503,
            detail="The search service isn't configured yet — try again soon.",
        )

    admin = get_supabase_admin()

    if body.project_id:
        owned = (
            admin.table("projects")
            .select("id")
            .eq("id", body.project_id)
            .eq("organization_id", auth["org_id"])
            .execute()
        )
        if not owned.data:
            raise HTTPException(
                status_code=404, detail="We couldn't find that workspace."
            )

    # The only place now() is read in this route. The cap window and the run's
    # search_date must come from the same instant — a run counted against one
    # day and stamped with another is exactly the ambiguity a date-stamped
    # clearance answer cannot carry.
    now = datetime.now(UTC)

    if body.tier == "QUICK":
        credits = 0
        start_of_day = datetime.combine(now.date(), time.min, tzinfo=UTC)
        today = (
            admin.table("clearance_runs")
            .select("id", count="exact")
            .eq("organization_id", auth["org_id"])
            .eq("tier", "QUICK")
            .gte("created_at", start_of_day.isoformat())
            .execute()
        )
        used = today.count if today.count is not None else len(today.data or [])
        if used >= QUICK_RUNS_PER_DAY:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"You've used today's {QUICK_RUNS_PER_DAY} free checks. "
                    f"They reset tomorrow — or run a Standard or Comprehensive "
                    f"search now, which isn't capped."
                ),
            )
    else:
        credits = clearance_credits(body.tier)
        balance, _granted, _plan = get_credit_balance(auth["org_id"])
        if balance < credits:
            raise HTTPException(
                status_code=402,
                detail=(
                    f"Not enough credits. This search needs {credits:,}; "
                    f"you have {balance:,}."
                ),
            )
        # Charged at create, not at completion — the same rule as every run:
        # deducting later would let one run's worth of credits start ten.
        deduct_credits(auth["org_id"], credits)

    result = (
        admin.table("clearance_runs")
        .insert({
            "organization_id": auth["org_id"],
            "project_id": body.project_id,
            "item": body.item,
            "type_hint": body.type_hint,
            "field": body.field,
            "competitors": body.competitors,
            "tier": body.tier,
            "status": "queued",
            "credits_charged": credits,
            "search_date": now.date().isoformat(),
            "created_at": now.isoformat(),
        })
        .execute()
    )
    run = result.data[0]

    spawn(
        run_clearance(run["id"], auth["org_id"]), "clearance_run",
        on_failure=_mark_clearance_failed(run["id"], "clearance_run"),
    )
    return run


@router.get("")
async def list_clearance_runs(
    project_id: str | None = Query(None),
    auth: dict = Depends(get_current_org),
):
    """The org's clearance runs, newest first, without the report bodies.

    The artifact is fetched only to lift the headline risk tier out of it; it
    is dropped before the response, because a list of 50 runs each carrying a
    full artifact is a detail view pretending to be an index.
    """
    admin = get_supabase_admin()
    query = (
        admin.table("clearance_runs")
        .select(
            "id, project_id, item, tier, status, credits_charged, "
            "search_date, created_at, completed_at, artifact",
            count="exact",
        )
        .eq("organization_id", auth["org_id"])
    )
    if project_id:
        query = query.eq("project_id", project_id)
    result = query.order("created_at", desc=True).limit(LIST_LIMIT).execute()

    items = []
    for row in result.data or []:
        artifact = row.pop("artifact", None) or {}
        items.append({
            **row,
            "risk": (artifact.get("patents") or {}).get("overall_risk"),
        })
    return {"items": items, "total": result.count, "limit": LIST_LIMIT}


@router.get("/{run_id}")
async def get_clearance_run(run_id: str, auth: dict = Depends(get_current_org)):
    """One run, with its artifact and report once complete."""
    admin = get_supabase_admin()
    rows = (
        admin.table("clearance_runs")
        .select("*")
        .eq("id", run_id)
        .eq("organization_id", auth["org_id"])
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Clearance run not found")
    return rows[0]
