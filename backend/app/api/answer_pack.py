# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# POST   /api/answer-pack            build one, charging credits
# GET    /api/answer-pack/by-simulation/{simulation_id}
# GET    /api/answer-pack/{id}
# ─────────────────────────────────────────────────────────
"""The objection matrix, as an ordinary paid artifact.

Charging follows the rule every other paid surface in this codebase uses:
**charged at create, never at completion.** Deducting on success would let one
pack's worth of credits start ten concurrent builds, and a founder who is
refused after the work is a founder who has already spent the time.

The route refuses before it charges, in this order: the run must belong to
this org, it must carry measured objections, and the balance must cover the
price. Charging first and discovering there is nothing to build second is how
a product takes money for an empty document.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_org, require_can_spend
from app.core.database import get_supabase_admin, maybe_one
from app.core.tasks import spawn
from app.services.billing.agent_pricing import (
    answer_pack_credits,
    deduct_credits,
    get_credit_balance,
)
from app.workers.answer_pack_tasks import GENERIC_FAILURE_MESSAGE, run_answer_pack

log = structlog.get_logger()

router = APIRouter(tags=["answer-pack"])


class BuildBody(BaseModel):
    simulation_id: str


def _mark_failed(pack_id: str) -> Callable[[Exception], None]:
    """`on_failure` for `spawn`: a build whose worker died must say so.

    Without this the row stays `queued` forever and the founder watches a
    spinner for a failure that was logged and never surfaced. The sentence is
    the founder-readable one — the exception is already in the log.
    """
    def _mark(exc: Exception) -> None:
        log.error("answer_pack_worker_died", pack_id=pack_id, error=str(exc))
        # Conditional on the row still being in flight, like every other writer
        # to this family. `run_answer_pack` writes `complete` *outside* its own
        # `except Exception`, so a write that lands in Postgres and then fails
        # on the way back reaches this handler with a finished pack on the row —
        # and a bare `.eq("id", ...)` would report it as a failure the founder
        # never had. Same states the reaper's `answer_packs` rule watches.
        get_supabase_admin().table("answer_packs").update({
            "status": "failed",
            "error_message": GENERIC_FAILURE_MESSAGE,
        }).eq("id", pack_id).in_("status", ["queued", "building"]).execute()
    return _mark


@router.post("")
async def build_pack(body: BuildBody, auth: dict = Depends(require_can_spend)):
    """Build the answers for one run's measured objections."""
    admin = get_supabase_admin()
    org_id = auth["org_id"]

    sim = maybe_one(
        admin.table("simulations")
        .select("id, name")
        .eq("id", body.simulation_id)
        .eq("organization_id", org_id)
    )
    if not sim.data:
        raise HTTPException(status_code=404, detail="We could not find that run.")

    # Refuse before charging. A run with nothing measured cannot support a
    # matrix, and taking money for one is worse than declining.
    objections = (
        admin.table("canonical_objections")
        .select("id", count="exact")
        .eq("simulation_id", body.simulation_id)
        .eq("organization_id", org_id)
        .execute()
    )
    found = objections.count if objections.count is not None else len(objections.data or [])
    if found == 0:
        raise HTTPException(
            status_code=409,
            detail=(
                "This run has no measured objections yet, so there is nothing "
                "to build answers from. Runs that finished without anyone "
                "objecting cannot produce a matrix."
            ),
        )

    credits = answer_pack_credits()
    balance, _granted, _plan = get_credit_balance(org_id)
    if balance < credits:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Not enough credits. Building your answers needs {credits:,}; "
                f"you have {balance:,}."
            ),
        )

    deduct_credits(org_id, credits)

    row = (
        admin.table("answer_packs")
        .insert({
            "simulation_id": body.simulation_id,
            "organization_id": org_id,
            "status": "queued",
            "credits_charged": credits,
            "created_at": datetime.now(UTC).isoformat(),
        })
        .execute()
    ).data[0]

    spawn(
        run_answer_pack(row["id"], body.simulation_id, org_id),
        "answer_pack",
        on_failure=_mark_failed(row["id"]),
    )
    log.info(
        "answer_pack_started",
        pack_id=row["id"],
        simulation_id=body.simulation_id,
        org_id=org_id,
        objections=found,
        credits=credits,
    )
    return row


@router.get("/by-simulation/{simulation_id}")
async def pack_for_simulation(simulation_id: str, auth: dict = Depends(get_current_org)):
    """The newest pack for this run, or 404.

    Newest rather than only: a founder who rebuilds after answering an
    objection wants the new one, and the old row stays as the record of what
    the matrix said before.
    """
    admin = get_supabase_admin()
    result = (
        admin.table("answer_packs")
        .select("*")
        .eq("simulation_id", simulation_id)
        .eq("organization_id", auth["org_id"])
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="No answers have been built for this run.")
    return result.data[0]


@router.get("/{pack_id}")
async def get_pack(pack_id: str, auth: dict = Depends(get_current_org)):
    admin = get_supabase_admin()
    result = maybe_one(
        admin.table("answer_packs")
        .select("*")
        .eq("id", pack_id)
        .eq("organization_id", auth["org_id"])
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="We could not find those answers.")
    return result.data
