from __future__ import annotations

import asyncio

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_org
from app.core.database import get_supabase_admin
from app.services.engine.document_processor import _extract_text
from app.services.intelligence.report_agent import (
    get_report_progress,
    strip_react_artifacts,
)
from app.services.intelligence.report_chat import chat_with_report
from app.workers.report_tasks import run_generate_report

log = structlog.get_logger()


def _compute_polarization(events: list[dict]) -> dict:
    """Compute polarization metrics from simulation event sentiment values.

    Uses per-agent sentiment at the final round to compute the extreme-to-moderate
    ratio.  Returns controversy_score (0-1), polarization_ratio (str like "2.7:1"),
    and valence_switching_pct (int 0-100).
    """
    if not events:
        return {"controversy_score": None, "polarization_ratio": None, "valence_switching_pct": None}

    # Find the maximum round number (final round)
    max_round = 0
    for e in events:
        rn = e.get("round_number") or 0
        if rn > max_round:
            max_round = rn

    # Collect per-agent sentiment at the final round (deduplicated: last event wins)
    agent_sentiments: dict[str, float] = {}
    all_sentiments: list[float] = []
    for e in events:
        md = e.get("metadata") or {}
        s = md.get("sentiment")
        if s is None:
            continue
        try:
            val = float(s)
        except (ValueError, TypeError):
            continue
        all_sentiments.append(val)
        rn = e.get("round_number") or 0
        if rn == max_round and e.get("agent_id"):
            agent_sentiments[e["agent_id"]] = val

    # Use per-agent final-round sentiments for ratio; fall back to all sentiments
    sentiments = list(agent_sentiments.values()) if agent_sentiments else all_sentiments
    if not sentiments:
        return {"controversy_score": None, "polarization_ratio": None, "valence_switching_pct": None}

    # Extreme-to-moderate ratio: |sentiment| > 0.5 vs |sentiment| <= 0.5
    extreme = sum(1 for s in sentiments if abs(s) > 0.5)
    moderate = max(sum(1 for s in sentiments if abs(s) <= 0.5), 1)
    ratio = round(extreme / moderate, 1)

    # Valence switching: % of consecutive pairs that cross the zero line (all events)
    switches = 0
    for i in range(1, len(all_sentiments)):
        if (all_sentiments[i] > 0) != (all_sentiments[i - 1] > 0):
            switches += 1
    switching_pct = round(switches / max(len(all_sentiments) - 1, 1) * 100)

    # Normalize ratio to 0-1 scale (ratio of 5:1+ saturates at 1.0)
    controversy_score = round(min(1.0, ratio / 5.0), 2)

    return {
        "controversy_score": controversy_score,
        "polarization_ratio": f"{ratio}:1",
        "valence_switching_pct": switching_pct,
    }


async def _safe_task(coro, name: str):
    try:
        await coro
    except Exception:
        log.exception("background_task_failed", task=name)

router = APIRouter(tags=["reports"])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class GenerateReportBody(BaseModel):
    simulation_id: str
    variant: str = "a"
    evidence_depth: str = "deep"  # shallow, standard, deep, exhaustive
    max_sections: int | None = None


class ChatBody(BaseModel):
    message: str
    history: list[dict[str, str]] | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/generate")
async def generate_report(body: GenerateReportBody, auth: dict = Depends(get_current_org)):
    """Trigger report generation for a simulation."""
    log.info("generate_report", simulation_id=body.simulation_id, org_id=auth["org_id"])
    admin = get_supabase_admin()

    # Verify simulation belongs to org
    sim = (
        admin.table("simulations")
        .select("id")
        .eq("id", body.simulation_id)
        .eq("organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not sim.data:
        raise HTTPException(status_code=404, detail="Simulation not found")

    asyncio.create_task(_safe_task(
        run_generate_report(body.simulation_id, body.variant, body.evidence_depth, body.max_sections),
        "generate_report",
    ))
    return {"status": "started"}


@router.get("/by-simulation/{sim_id}")
async def get_reports_by_simulation(sim_id: str, auth: dict = Depends(get_current_org)):
    """Get the latest report for a simulation, with sections embedded."""
    log.info("get_reports_by_simulation", simulation_id=sim_id, org_id=auth["org_id"])
    admin = get_supabase_admin()

    # Verify simulation belongs to org
    sim = (
        admin.table("simulations")
        .select("id, project_id")
        .eq("id", sim_id)
        .eq("organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not sim.data:
        raise HTTPException(status_code=404, detail="Simulation not found")

    result = (
        admin.table("reports")
        .select("*")
        .eq("simulation_id", sim_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="No report found for this simulation")

    report = result.data[0]

    # Load sections from report_sections table
    sections_result = (
        admin.table("report_sections")
        .select("title, content")
        .eq("report_id", report["id"])
        .order("section_index")
        .execute()
    )

    # Compute polarization metrics from simulation events
    events = (
        admin.table("simulation_events")
        .select("metadata, round_number, agent_id")
        .eq("simulation_id", sim_id)
        .limit(2000)
        .execute()
    ).data or []
    polarization = _compute_polarization(events)

    # Fetch source documents for the simulation's project
    source_documents: list[dict] = []
    project_id = sim.data.get("project_id")
    if project_id:
        docs = (
            admin.table("documents")
            .select("id, filename, file_type, storage_path, file_size_bytes")
            .eq("project_id", project_id)
            .eq("processing_status", "complete")
            .order("created_at")
            .limit(5)
            .execute()
        ).data or []
        for doc in docs:
            try:
                file_bytes = admin.storage.from_("project-media").download(doc["storage_path"])
                text, _encoding, _pages = _extract_text(file_bytes, doc["file_type"])
                word_count = len(text.split())
                # Truncate to first ~500 words if over 2000 chars
                if len(text) > 2000:
                    words = text.split()[:500]
                    text = " ".join(words)
                    text += f"\n\n[Full source material: {word_count:,} words total]"
                source_documents.append({
                    "filename": doc["filename"],
                    "file_type": doc["file_type"],
                    "word_count": word_count,
                    "text": text,
                })
            except Exception:
                log.warning("source_doc_fetch_failed", doc_id=doc["id"])
                source_documents.append({
                    "filename": doc["filename"],
                    "file_type": doc["file_type"],
                    "word_count": 0,
                    "text": "[Document could not be loaded]",
                })

    # Return shape the frontend expects — strip any ReACT artifacts from content
    return {
        "id": report["id"],
        "simulation_id": report["simulation_id"],
        "status": report.get("status"),
        "sections": [
            {"title": s["title"], "content": strip_react_artifacts(s.get("content") or "")}
            for s in (sections_result.data or [])
        ],
        "full_markdown": strip_react_artifacts(report.get("markdown_content") or ""),
        "polarization": polarization,
        "source_documents": source_documents,
    }


@router.get("/{id}")
async def get_report(id: str, auth: dict = Depends(get_current_org)):
    """Get full report."""
    log.info("get_report", report_id=id)
    admin = get_supabase_admin()
    result = (
        admin.table("reports")
        .select("*, simulations!inner(organization_id)")
        .eq("id", id)
        .eq("simulations.organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Report not found")
    return result.data


@router.get("/{id}/sections")
async def list_report_sections(id: str, auth: dict = Depends(get_current_org)):
    """List sections of a report."""
    log.info("list_report_sections", report_id=id)
    admin = get_supabase_admin()

    # Verify report belongs to org via simulation join
    report = (
        admin.table("reports")
        .select("id, simulations!inner(organization_id)")
        .eq("id", id)
        .eq("simulations.organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not report.data:
        raise HTTPException(status_code=404, detail="Report not found")

    result = (
        admin.table("report_sections")
        .select("*")
        .eq("report_id", id)
        .order("section_index")
        .execute()
    )
    return result.data


@router.get("/{id}/progress")
async def report_progress(id: str, auth: dict = Depends(get_current_org)):
    """Get report generation progress."""
    log.info("report_progress", report_id=id)
    admin = get_supabase_admin()

    # Verify report belongs to org via simulation join
    report = (
        admin.table("reports")
        .select("id, simulations!inner(organization_id)")
        .eq("id", id)
        .eq("simulations.organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not report.data:
        raise HTTPException(status_code=404, detail="Report not found")

    progress = get_report_progress(id)
    return progress.model_dump()


@router.post("/{id}/chat")
async def chat_with_report_endpoint(id: str, body: ChatBody, auth: dict = Depends(get_current_org)):
    """Chat with a report using tool-augmented answers."""
    log.info("chat_with_report", report_id=id)
    admin = get_supabase_admin()

    # Verify report belongs to org via simulation join
    report = (
        admin.table("reports")
        .select("id, simulations!inner(organization_id)")
        .eq("id", id)
        .eq("simulations.organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not report.data:
        raise HTTPException(status_code=404, detail="Report not found")

    result = await chat_with_report(id, body.message, body.history)
    return result.model_dump()


# NOTE: report export lives in app/api/exports.py (POST /api/reports/{id}/export).
# A synchronous duplicate previously registered here shadowed that route — see
# main.py router order — making the chart-rendering export path unreachable.


@router.delete("/{id}")
async def delete_report(id: str, auth: dict = Depends(get_current_org)):
    """Delete a report and its sections."""
    log.info("delete_report", report_id=id)
    admin = get_supabase_admin()

    # Verify report belongs to org via simulation join
    report = (
        admin.table("reports")
        .select("id, simulations!inner(organization_id)")
        .eq("id", id)
        .eq("simulations.organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not report.data:
        raise HTTPException(status_code=404, detail="Report not found")

    # Delete sections first, then report
    admin.table("report_sections").delete().eq("report_id", id).execute()
    admin.table("reports").delete().eq("id", id).execute()

    return {"detail": "Report deleted"}
