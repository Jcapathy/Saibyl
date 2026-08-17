"""Run the room against the new page (PRD_V3 §4d, the prove leg).

Two routes. `GET /eligibility` answers "can the room be re-run for this
workspace, and against which run"; `POST /run` files the revised page as one
pre-positioned asset and clones the room around it through the inoculation
machinery (`services/website/room_run`), which is the template PRD_V3 §4d
names.

Charging is deliberately absent here. On the inoculation path, creating a
re-simulation is free and the run itself is quoted and charged at
`POST /api/simulations/{id}/start` — no generation charge because the agents
are copies, plus the per-asset action surcharge. This router rides that path
exactly; charging here as well would price the same run twice. The drafting
fee does not apply either: composing the page into an asset makes no model
call.
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.auth import get_current_org
from app.core.database import get_supabase_admin

log = structlog.get_logger()

router = APIRouter(tags=["website-room"])


class RunRoomBody(BaseModel):
    revision_id: str


def _revision_is_complete(revision: dict) -> bool:
    """Finished enough to show a room: built, and carrying its copy.

    `page_revisions` (PRD_V3 §4d) stores `revision_html` as a storage ref
    when the gauntlet finishes; a worker may instead hand the text along
    inline. A `status` column, if the row has one, must say `complete` —
    absent the column, carrying the copy is the completion signal.
    """
    status = revision.get("status")
    if status is not None and status != "complete":
        return False
    return bool(revision.get("revision_html") or revision.get("revision_text"))


@router.get("/eligibility")
async def eligibility(
    project_id: str = Query(...),
    auth: dict = Depends(get_current_org),
):
    """Whether this workspace has a finished run the room can repeat."""
    from app.services.website.room_run import (
        eligible_simulation,
        ineligibility_reason,
    )

    admin = get_supabase_admin()
    owned = (
        admin.table("projects")
        .select("id")
        .eq("id", project_id)
        .eq("organization_id", auth["org_id"])
        .execute()
    )
    if not owned.data:
        raise HTTPException(status_code=404, detail="We couldn't find that workspace.")

    sim = eligible_simulation(project_id, auth["org_id"])
    if sim:
        return {"eligible": True, "simulation_id": sim["id"]}
    return {
        "eligible": False,
        "reason": ineligibility_reason(project_id, auth["org_id"]),
    }


@router.post("/run")
async def run_room(body: RunRoomBody, auth: dict = Depends(get_current_org)):
    """Re-run the same room against the revised page.

    Returns the new run (a child of the run it repeats) in status `ready`.
    Start it through the ordinary `POST /api/simulations/{id}/start`, which
    prices and charges it the way every re-run is priced; the before/after
    lands at `GET /api/inoculation/{id}/result` when it completes.
    """
    from app.services.website.room_run import launch_room_run

    log.info("website_room_run", revision_id=body.revision_id, org_id=auth["org_id"])
    admin = get_supabase_admin()

    revisions = (
        admin.table("page_revisions")
        .select("*")
        .eq("id", body.revision_id)
        .limit(1)
        .execute()
    ).data or []
    if not revisions:
        raise HTTPException(
            status_code=404, detail="We couldn't find that revised page."
        )
    revision = revisions[0]

    # Ownership is enforced through the snapshot, which definitively carries
    # the org. The same sentence as the missing case — a revision another org
    # owns should not confirm its own existence.
    snapshots = (
        admin.table("website_snapshots")
        .select("id, project_id, organization_id, url")
        .eq("id", revision.get("snapshot_id"))
        .eq("organization_id", auth["org_id"])
        .limit(1)
        .execute()
    ).data or []
    if not snapshots:
        raise HTTPException(
            status_code=404, detail="We couldn't find that revised page."
        )
    snapshot = snapshots[0]

    if not _revision_is_complete(revision):
        raise HTTPException(
            status_code=409,
            detail=(
                "That revised page hasn't finished building yet. Wait for it "
                "to finish, then run the room against it."
            ),
        )

    # Eligibility is re-checked inside the launch — it scans the workspace's
    # finished runs at launch time rather than trusting an earlier answer —
    # and every refusal it raises is already a founder sentence.
    try:
        return await launch_room_run(
            revision_row=revision,
            snapshot_row=snapshot,
            organization_id=auth["org_id"],
            created_by=auth["user"]["id"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
