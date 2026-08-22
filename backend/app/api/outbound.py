# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# POST   /api/outbound                    build one, charging credits
# GET    /api/outbound/by-simulation/{simulation_id}
# GET    /api/outbound/{sequence_id}
# ─────────────────────────────────────────────────────────
"""The outbound sequences, as an ordinary paid artifact.

Charging follows the rule every other paid surface in this codebase uses:
**charged at create, never at completion.** Deducting on success would let one
build's worth of credits start ten concurrent builds, and a founder who is
refused after the work is a founder who has already spent the time.

The route refuses before it charges, in this order: the run must belong to this
org, it must carry measured objections, it must carry a buyer profile to write
to, and the balance must cover the price. Charging first and discovering there
is nothing to build second is how a product takes money for an empty document.

**There is no send endpoint here and there is not going to be one.** These
routes create copy and read it back. Saibyl stores no contacts, no list and no
suppression state — see `services/gtm/privacy.py` — so it has none of the
things a sending path would need to be operated responsibly. The founder sends
from their own inbox, to their own list.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_org, require_can_spend
from app.core.database import get_supabase_admin
from app.core.tasks import spawn
from app.services.billing.agent_pricing import (
    deduct_credits,
    get_credit_balance,
    outbound_sequence_credits,
)
from app.services.gtm.outbound import available_inputs
from app.workers.outbound_tasks import GENERIC_FAILURE_MESSAGE, run_outbound_sequences

log = structlog.get_logger()

router = APIRouter(tags=["outbound"])


class BuildBody(BaseModel):
    simulation_id: str


def _mark_failed(sequence_id: str) -> Callable[[Exception], None]:
    """`on_failure` for `spawn`: a build whose worker died must say so.

    Without this the row stays `queued` forever and the founder watches a
    spinner for a failure that was logged and never surfaced. The sentence is
    the founder-readable one — the exception is already in the log.
    """
    def _mark(exc: Exception) -> None:
        log.error("outbound_worker_died", sequence_id=sequence_id, error=str(exc))
        get_supabase_admin().table("outbound_sequences").update({
            "status": "failed",
            "error_message": GENERIC_FAILURE_MESSAGE,
        }).eq("id", sequence_id).execute()
    return _mark


@router.post("")
async def build_sequences(body: BuildBody, auth: dict = Depends(require_can_spend)):
    """Write the outbound sequences for one run's measured objections."""
    admin = get_supabase_admin()
    org_id = auth["org_id"]

    sim = (
        admin.table("simulations")
        .select("id, name")
        .eq("id", body.simulation_id)
        .eq("organization_id", org_id)
        .single()
        .execute()
    )
    if not sim.data:
        raise HTTPException(status_code=404, detail="We could not find that run.")

    # Refuse before charging. A run with nothing measured cannot support a
    # sequence, and taking money for one is worse than declining.
    inputs = available_inputs(body.simulation_id, org_id)
    if inputs.objections == 0:
        raise HTTPException(
            status_code=409,
            detail=(
                "This run has no measured objections yet, so there is nothing "
                "to build a sequence around. A sequence written without them "
                "is the generic outbound this is meant to replace."
            ),
        )
    if inputs.archetypes == 0:
        raise HTTPException(
            status_code=409,
            detail=(
                "This run has no buyer profile attached, so there is nobody to "
                "write a sequence to. Runs built from a synthesized ICP carry "
                "one."
            ),
        )

    credits = outbound_sequence_credits()
    balance, _granted, _plan = get_credit_balance(org_id)
    if balance < credits:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Not enough credits. Writing your sequences needs {credits:,}; "
                f"you have {balance:,}."
            ),
        )

    deduct_credits(org_id, credits)

    row = (
        admin.table("outbound_sequences")
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
        run_outbound_sequences(row["id"], body.simulation_id, org_id),
        "outbound_sequences",
        on_failure=_mark_failed(row["id"]),
    )
    log.info(
        "outbound_started",
        sequence_id=row["id"],
        simulation_id=body.simulation_id,
        org_id=org_id,
        objections=inputs.objections,
        archetypes=inputs.archetypes,
        credits=credits,
    )
    return row


@router.get("/by-simulation/{simulation_id}")
async def sequences_for_simulation(simulation_id: str, auth: dict = Depends(get_current_org)):
    """The newest build for this run, or 404.

    Newest rather than only: a founder who rebuilds after answering an objection
    wants the new sequences, and the old row stays as the record of what was
    being sent before.
    """
    admin = get_supabase_admin()
    result = (
        admin.table("outbound_sequences")
        .select("*")
        .eq("simulation_id", simulation_id)
        .eq("organization_id", auth["org_id"])
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=404, detail="No sequences have been written for this run."
        )
    return result.data[0]


@router.get("/{sequence_id}")
async def get_sequences(sequence_id: str, auth: dict = Depends(get_current_org)):
    admin = get_supabase_admin()
    result = (
        admin.table("outbound_sequences")
        .select("*")
        .eq("id", sequence_id)
        .eq("organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="We could not find those sequences.")
    return result.data
