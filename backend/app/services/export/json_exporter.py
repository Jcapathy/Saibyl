# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# export_report_json(report_id: UUID) -> dict
# export_simulation_json(simulation_id: UUID) -> dict
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime
from uuid import UUID

import structlog

from app.core.database import get_supabase_admin

logger = structlog.get_logger()


async def export_report_json(report_id: UUID) -> bytes:
    """Export report as gzipped JSON."""
    admin = get_supabase_admin()

    report = admin.table("reports").select("*").eq(
        "id", str(report_id)
    ).single().execute().data

    sim = admin.table("simulations").select("*").eq(
        "id", report["simulation_id"]
    ).single().execute().data

    sections = admin.table("report_sections").select("*").eq(
        "report_id", str(report_id)
    ).order("section_index").execute().data

    agents = admin.table("simulation_agents").select(
        "id, entity_name, username, platform, profile"
    ).eq("simulation_id", report["simulation_id"]).execute().data

    export_data = {
        "meta": {
            "report_id": report["id"],
            "title": report.get("title"),
            "status": report.get("status"),
            "variant": report.get("variant"),
            "created_at": report.get("created_at"),
            "completed_at": report.get("completed_at"),
        },
        "simulation": {
            "id": sim["id"],
            "name": sim["name"],
            "prediction_goal": sim.get("prediction_goal"),
            "platforms": sim.get("platforms"),
            "max_rounds": sim.get("max_rounds"),
            "is_ab_test": sim.get("is_ab_test"),
            "status": sim.get("status"),
        },
        "sections": [
            {
                "index": s["section_index"],
                "title": s["title"],
                "content": s.get("content"),
                "tool_calls": s.get("tool_calls", []),
            }
            for s in sections
        ],
        "agent_profiles": [
            {
                "id": a["id"],
                "name": a["entity_name"],
                "username": a["username"],
                "platform": a["platform"],
                "persona_type": (a.get("profile") or {}).get("persona_type"),
            }
            for a in agents
        ],
        "export_version": "1.0",
        "exported_at": datetime.now(UTC).isoformat(),
    }

    json_bytes = json.dumps(export_data, indent=2, default=str).encode()
    compressed = gzip.compress(json_bytes)
    logger.info("json_report_exported", report_id=str(report_id), size=len(compressed))
    return compressed


async def export_simulation_json(simulation_id: UUID) -> bytes:
    """Export full simulation data as gzipped JSON."""
    admin = get_supabase_admin()

    sim = admin.table("simulations").select("*").eq(
        "id", str(simulation_id)
    ).single().execute().data

    agents = admin.table("simulation_agents").select("*").eq(
        "simulation_id", str(simulation_id)
    ).execute().data

    events = admin.table("simulation_events").select("*").eq(
        "simulation_id", str(simulation_id)
    ).order("created_at").execute().data

    export_data = {
        "meta": {
            "simulation_id": sim["id"],
            "name": sim["name"],
            "prediction_goal": sim.get("prediction_goal"),
            "status": sim.get("status"),
            "created_at": sim.get("created_at"),
            "completed_at": sim.get("completed_at"),
        },
        "config": {
            "platforms": sim.get("platforms"),
            "max_rounds": sim.get("max_rounds"),
            "is_ab_test": sim.get("is_ab_test"),
            "timezone": sim.get("timezone"),
        },
        "agents": [
            {
                "id": a["id"],
                "entity_name": a["entity_name"],
                "username": a["username"],
                "platform": a["platform"],
                "variant": a.get("variant"),
                "profile": a.get("profile"),
            }
            for a in agents
        ],
        "events": [
            {
                "id": e["id"],
                "event_type": e["event_type"],
                "agent_id": e.get("agent_id"),
                "platform": e.get("platform"),
                "variant": e.get("variant"),
                "round_number": e.get("round_number"),
                "content": e.get("content"),
                "metadata": e.get("metadata"),
                "created_at": e.get("created_at"),
            }
            for e in events
        ],
        "export_version": "1.0",
        "exported_at": datetime.now(UTC).isoformat(),
    }

    json_bytes = json.dumps(export_data, indent=2, default=str).encode()
    compressed = gzip.compress(json_bytes)
    logger.info("json_simulation_exported", simulation_id=str(simulation_id), size=len(compressed))
    return compressed
