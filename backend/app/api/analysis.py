"""Read access to the measurement layer.

The frontend renders every number from these responses. There is deliberately no
endpoint that returns raw event metadata for charting — that path is how the
report viewer ended up scraping markdown and filling the gaps with
`Math.random()`.
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import get_current_org
from app.core.database import fetch_all, get_supabase_admin
from app.core.messages import founder_safe
from app.services.intelligence.analysis_builder import (
    build_simulation_analysis,
    get_analysis,
)

log = structlog.get_logger()

router = APIRouter(tags=["analysis"])


def _owned_simulation(sim_id: str, org_id: str) -> dict:
    admin = get_supabase_admin()
    rows = (
        admin.table("simulations")
        .select("id, name, status, organization_id")
        .eq("id", sim_id)
        .eq("organization_id", org_id)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return rows[0]


@router.get("/simulations/{id}/analysis")
async def simulation_analysis(id: str, auth: dict = Depends(get_current_org)):
    """The analysis artifact for a run.

    Returns 404 rather than an empty artifact when a run has not been analysed:
    an empty artifact is indistinguishable from a run where nobody said
    anything, and the client must be able to tell those apart to decide between
    "still working" and "this run produced no signal".
    """
    _owned_simulation(id, auth["org_id"])
    row = get_analysis(id)
    if not row:
        raise HTTPException(
            status_code=404,
            detail="This simulation has not been analysed yet.",
        )

    if row.get("build_status") != "complete":
        # The stored message is served when somebody wrote it for a founder,
        # and replaced when it is the machine's. Caught live: this endpoint
        # returned `409 {"detail": "RemoteProtocolError: Server disconnected"}`
        # to a customer. The raw text stays in the row for us.
        raise HTTPException(
            status_code=409,
            detail=founder_safe(
                row.get("error_message"),
                "We could not finish analysing this run. Your run and its "
                "events are safe — try rebuilding the analysis, and tell us "
                "if it keeps failing.",
            ),
        )

    return {
        "simulation_id": id,
        "schema_version": row["schema_version"],
        "artifact": row["artifact"],
        "generated_at": row.get("updated_at") or row.get("created_at"),
    }


@router.post("/simulations/{simulation_id}/analysis/rebuild")
async def rebuild_analysis(simulation_id: str, auth: dict = Depends(get_current_org)):
    """Recompose the artifact from the run's stored measurements.

    The artifact is derived data, composed once when a run finishes. A
    vocabulary or copy fix shipped after that moment reaches nothing already
    composed, so every earlier artifact stays frozen with the old sentences
    until somebody rebuilds it — which, without this route, meant paying for
    the run again (PRD_V3 §8.2). Measurement is NOT re-run: this reads the
    measured events the run already paid for and composes them afresh. The
    one model call left in the path is the small objection-grouping pass,
    not a second run.
    """
    _owned_simulation(simulation_id, auth["org_id"])
    analysis = await build_simulation_analysis(simulation_id, auth["org_id"])
    log.info(
        "analysis_rebuilt",
        simulation_id=simulation_id,
        org_id=auth["org_id"],
        objections=len(analysis.objections),
    )
    return {
        "simulation_id": simulation_id,
        "build_status": "complete",
        "schema_version": analysis.schema_version,
        "generated_at": analysis.generated_at,
        "objections": len(analysis.objections),
        "flashpoints": len(analysis.flashpoints),
        "rounds": len(analysis.sentiment_timeline),
        "confidence": analysis.quality.confidence,
    }


@router.get("/simulations/{id}/objections")
async def simulation_objections(
    id: str,
    limit: int = Query(50, ge=1, le=200),
    auth: dict = Depends(get_current_org),
):
    """Canonical objections, ranked by load-bearing weight."""
    _owned_simulation(id, auth["org_id"])
    admin = get_supabase_admin()
    rows = (
        admin.table("canonical_objections")
        .select("*")
        .eq("simulation_id", id)
        .order("load_bearing_score", desc=True)
        .limit(limit)
        .execute()
    ).data or []
    return rows


@router.get("/simulations/{id}/evidence")
async def simulation_evidence(
    id: str,
    event_ids: str = Query(..., description="Comma-separated simulation_event ids"),
    auth: dict = Depends(get_current_org),
):
    """The agent quotes behind a finding.

    This is the drill-down every number in the artifact points at. Without it
    a measured figure is just a more expensive assertion.
    """
    _owned_simulation(id, auth["org_id"])

    ids = [eid.strip() for eid in event_ids.split(",") if eid.strip()][:200]
    if not ids:
        return []

    admin = get_supabase_admin()
    rows = fetch_all(
        admin.table("simulation_events")
        .select(
            "id, agent_id, platform, round_number, event_type, content, "
            "valence, stance, intensity, intent, is_novel_claim, objections"
        )
        .eq("simulation_id", id)
        .in_("id", ids)
        .order("id")
    )

    agents = fetch_all(
        admin.table("simulation_agents")
        .select("id, username, entity_name, profile")
        .eq("simulation_id", id)
        .order("id")
    )
    agent_index = {
        a["id"]: {
            "username": a.get("username"),
            "display_name": a.get("entity_name"),
            "archetype": (a.get("profile") or {}).get("archetype")
            or (a.get("profile") or {}).get("persona_type")
            or "Unclassified",
        }
        for a in agents
    }

    return [
        {**row, "agent": agent_index.get(row.get("agent_id"), {})} for row in rows
    ]
