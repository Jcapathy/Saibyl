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
from app.services.intelligence.analysis_builder import get_analysis

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
        raise HTTPException(
            status_code=409,
            detail=row.get("error_message") or "Analysis failed for this simulation.",
        )

    return {
        "simulation_id": id,
        "schema_version": row["schema_version"],
        "artifact": row["artifact"],
        "generated_at": row.get("updated_at") or row.get("created_at"),
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
