# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# POST   /api/messaging-doc            build one, charging credits
# GET    /api/messaging-doc/by-simulation/{simulation_id}
# GET    /api/messaging-doc/{doc_id}
# ─────────────────────────────────────────────────────────
"""The messaging document, as an ordinary paid artifact.

Charging follows the rule every other paid surface in this codebase uses:
**charged at create, never at completion.** Deducting on success would let one
document's worth of credits start ten concurrent builds, and a founder who is
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
from app.core.database import get_supabase_admin
from app.core.tasks import spawn
from app.services.billing.agent_pricing import (
    deduct_credits,
    get_credit_balance,
    messaging_doc_credits,
)
from app.workers.messaging_doc_tasks import GENERIC_FAILURE_MESSAGE, run_messaging_doc

log = structlog.get_logger()

router = APIRouter(tags=["messaging-doc"])


class BuildBody(BaseModel):
    simulation_id: str


def _mark_failed(doc_id: str) -> Callable[[Exception], None]:
    """`on_failure` for `spawn`: a build whose worker died must say so.

    Without this the row stays `queued` forever and the founder watches a
    spinner for a failure that was logged and never surfaced. The sentence is
    the founder-readable one — the exception is already in the log.
    """
    def _mark(exc: Exception) -> None:
        log.error("messaging_doc_worker_died", doc_id=doc_id, error=str(exc))
        get_supabase_admin().table("messaging_docs").update({
            "status": "failed",
            "error_message": GENERIC_FAILURE_MESSAGE,
        }).eq("id", doc_id).execute()
    return _mark


@router.post("")
async def build_doc(body: BuildBody, auth: dict = Depends(require_can_spend)):
    """Fill the messaging worksheet from one run's measurement."""
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
    # messaging document, and taking money for one is worse than declining.
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
                "to build a messaging document from. A document written "
                "without them is the one you would have written alone."
            ),
        )

    credits = messaging_doc_credits()
    balance, _granted, _plan = get_credit_balance(org_id)
    if balance < credits:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Not enough credits. Building your messaging document needs "
                f"{credits:,}; you have {balance:,}."
            ),
        )

    deduct_credits(org_id, credits)

    row = (
        admin.table("messaging_docs")
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
        run_messaging_doc(row["id"], body.simulation_id, org_id),
        "messaging_doc",
        on_failure=_mark_failed(row["id"]),
    )
    log.info(
        "messaging_doc_started",
        doc_id=row["id"],
        simulation_id=body.simulation_id,
        org_id=org_id,
        objections=found,
        credits=credits,
    )
    return row


@router.get("/by-simulation/{simulation_id}")
async def doc_for_simulation(simulation_id: str, auth: dict = Depends(get_current_org)):
    """The newest document for this run, or 404.

    Newest rather than only: messaging is never finished — the playbook says
    so — and a founder who rebuilds after changing the pitch wants the new
    one, with the old row left as the record of what the messaging said
    before.
    """
    admin = get_supabase_admin()
    result = (
        admin.table("messaging_docs")
        .select("*")
        .eq("simulation_id", simulation_id)
        .eq("organization_id", auth["org_id"])
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=404,
            detail="No messaging document has been built for this run.",
        )
    return result.data[0]


@router.get("/{doc_id}")
async def get_doc(doc_id: str, auth: dict = Depends(get_current_org)):
    admin = get_supabase_admin()
    result = (
        admin.table("messaging_docs")
        .select("*")
        .eq("id", doc_id)
        .eq("organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=404,
            detail="We could not find that messaging document.",
        )
    return result.data
