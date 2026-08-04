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
from app.services.intelligence.report_agent import clean_report_output

logger = structlog.get_logger()


def _adversarial_block(simulation_id: str) -> dict:
    """The run's adversarial disclosure, read from the artifact.

    Read rather than recomputed. The sentence is composed once in
    `analysis_builder._adversarial_disclosure` so that the viewer, the print
    page, the PDF and this export all say the same thing — a disclosure
    re-derived per renderer is a disclosure that will differ per renderer.

    Absent artifact returns `{"enabled": False}`, which is correct for every run
    made before Phase 2 and for any run whose analysis failed.
    """
    from app.services.intelligence.analysis_builder import get_analysis

    stored = get_analysis(simulation_id) or {}
    artifact = stored.get("artifact") or {}
    return artifact.get("adversarial") or {"enabled": False}


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
        "id, entity_name, username, platform, profile, is_adversarial, adversarial_role"
    ).eq("simulation_id", report["simulation_id"]).execute().data

    export_data = {
        # PRD §4: adversarial agents are labelled synthetic in every report
        # **and export**. An export is the artefact that leaves Saibyl and gets
        # forwarded, so it is the one that most needs to carry the label — the
        # recipient never saw the Run Configurator.
        "adversarial_cohort": _adversarial_block(report["simulation_id"]),
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
            "variants": sim.get("variants") or 1,
            "status": sim.get("status"),
        },
        "sections": [
            {
                "index": s["section_index"],
                "title": s["title"],
                "content": clean_report_output(s.get("content") or ""),
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
                "is_adversarial": bool(a.get("is_adversarial")),
                "adversarial_role": a.get("adversarial_role"),
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
        "adversarial_cohort": _adversarial_block(str(simulation_id)),
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
            "variants": sim.get("variants") or 1,
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
