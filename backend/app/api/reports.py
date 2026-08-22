from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.auth import get_current_org, require_can_destroy
from app.core.database import get_supabase_admin
from app.core.tasks import spawn
from app.services.engine.document_processor import _extract_text
from app.services.intelligence.analysis_data import load_run_data
from app.services.intelligence.report_agent import (
    compute_polarization,
    get_report_progress,
    strip_react_artifacts,
)
from app.services.intelligence.report_chat import chat_with_report
from app.workers.report_tasks import run_generate_report

log = structlog.get_logger()

router = APIRouter(tags=["reports"])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class GenerateReportBody(BaseModel):
    simulation_id: str
    evidence_depth: str = "deep"  # shallow, standard, deep, exhaustive
    max_sections: int | None = None

    # `variant` was here and did nothing — it reached a log line and no further.
    # A report covers the whole run, and on a matched-swarm run that is the
    # point: the scoreboard compares the arenas, so a per-arena report would be
    # the one thing the Marketing lens exists to replace. Dropped rather than
    # kept as an ignored field, because an accepted parameter that has no effect
    # is a promise the API does not keep.


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

    spawn(
        run_generate_report(body.simulation_id, body.evidence_depth, body.max_sections),
        "generate_report",
    )
    return {"status": "started"}


@router.get("")
async def list_reports(
    limit: int = Query(default=50, ge=1, le=200),
    auth: dict = Depends(get_current_org),
):
    """Every report this organisation has, newest first.

    Added for the dashboard. Reports could only be reached one at a time,
    through the run that produced them — so a founder with a quarter of work
    behind them had no way to see what they had, and the export endpoints that
    turn a report into a PDF or a deck had **no caller anywhere in the
    frontend**. The rendering was repaired on 2026-08-05 and remained
    unreachable.

    The run's name and its product come back with each row, because "report
    a3f8" is not a thing anybody can choose between.
    """
    admin = get_supabase_admin()
    result = (
        admin.table("reports")
        .select(
            "id, status, created_at, simulation_id, "
            "simulations!inner(name, organization_id, completed_at, "
            "projects(name))"
        )
        .eq("simulations.organization_id", auth["org_id"])
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

    items = []
    for row in result.data or []:
        sim = row.get("simulations") or {}
        project = sim.get("projects") or {}
        items.append({
            "id": row["id"],
            "status": row.get("status"),
            "created_at": row.get("created_at"),
            "simulation_id": row.get("simulation_id"),
            # Absent rather than a placeholder. A row whose run was deleted has
            # no name, and "Untitled" would read as a name somebody chose.
            "run_name": sim.get("name"),
            "product_name": project.get("name"),
        })

    log.info("list_reports", org_id=auth["org_id"], count=len(items))
    return {"items": items, "total": len(items)}


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

    # Polarization from measured valence. `load_run_data` pages past
    # PostgREST's 1,000-row cap; the `.limit(2000)` this replaces truncated any
    # larger run and reported the ratio of its first thousand events.
    polarization = compute_polarization(load_run_data(sim_id).events)
    if polarization["polarization_ratio"] is None:
        log.info("report_polarization_unmeasured", simulation_id=sim_id)

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
        # Carried on the per-run route too, not only on `/reports/{id}`. This
        # is the route the run page reads, so without it a founder whose
        # report failed saw the word "failed" and no reason — which is the
        # whole point of the column.
        "error_message": report.get("error_message"),
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
async def delete_report(id: str, auth: dict = Depends(require_can_destroy)):
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
