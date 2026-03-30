from __future__ import annotations

import asyncio
import io
import json
import re

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.auth import get_current_org
from app.core.database import get_supabase_admin
from app.services.intelligence.report_agent import get_report_progress
from app.services.intelligence.report_chat import chat_with_report
from app.workers.report_tasks import run_generate_report

log = structlog.get_logger()


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
    max_react_steps: int | None = None
    max_sections: int | None = None


class ExportReportBody(BaseModel):
    format: str  # "json", "pdf", "pptx"


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

    asyncio.create_task(_safe_task(run_generate_report(body.simulation_id, body.variant), "generate_report"))
    return {"status": "started"}


@router.get("/by-simulation/{sim_id}")
async def get_reports_by_simulation(sim_id: str, auth: dict = Depends(get_current_org)):
    """Get the latest report for a simulation, with sections embedded."""
    log.info("get_reports_by_simulation", simulation_id=sim_id, org_id=auth["org_id"])
    admin = get_supabase_admin()

    # Verify simulation belongs to org
    sim = (
        admin.table("simulations")
        .select("id")
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

    # Return shape the frontend expects
    return {
        "id": report["id"],
        "simulation_id": report["simulation_id"],
        "status": report.get("status"),
        "sections": [
            {"title": s["title"], "content": s.get("content") or ""}
            for s in (sections_result.data or [])
        ],
        "full_markdown": report.get("markdown_content") or "",
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


@router.post("/{id}/export")
async def export_report(id: str, body: ExportReportBody, auth: dict = Depends(get_current_org)):
    """Export report as JSON, PDF, or PPTX — returns file download directly."""
    log.info("export_report", report_id=id, format=body.format)
    admin = get_supabase_admin()

    report = (
        admin.table("reports")
        .select("*, simulations!inner(name, organization_id)")
        .eq("id", id)
        .eq("simulations.organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not report.data:
        raise HTTPException(status_code=404, detail="Report not found")

    rpt = report.data
    markdown = rpt.get("markdown_content") or ""
    title = rpt.get("title") or "Report"
    safe_title = re.sub(r"[^a-zA-Z0-9_\- ]", "", title)[:80].strip()

    # Load sections
    sections = (
        admin.table("report_sections")
        .select("title, content, section_index")
        .eq("report_id", id)
        .order("section_index")
        .execute()
    ).data or []

    if body.format == "json":
        payload = {
            "id": rpt["id"],
            "title": title,
            "simulation_id": rpt["simulation_id"],
            "status": rpt.get("status"),
            "sections": [{"title": s["title"], "content": s.get("content") or ""} for s in sections],
            "full_markdown": markdown,
        }
        buf = io.BytesIO(json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"))
        return StreamingResponse(
            buf,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{safe_title}.json"'},
        )

    if body.format == "pdf":
        import markdown as md
        from weasyprint import HTML

        html_body = md.markdown(markdown, extensions=["tables", "fenced_code"])
        full_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; color: #1a1a1a; line-height: 1.6; }}
  h1 {{ color: #2d2d7f; border-bottom: 2px solid #5B5FEE; padding-bottom: 8px; }}
  h2 {{ color: #3d3d9f; margin-top: 32px; }}
  blockquote {{ border-left: 3px solid #5B5FEE; padding-left: 16px; color: #555; margin: 16px 0; }}
  table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
  th {{ background: #f5f5ff; }}
  code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }}
</style>
</head><body>{html_body}</body></html>"""
        pdf_bytes = HTML(string=full_html).write_pdf()
        buf = io.BytesIO(pdf_bytes)
        return StreamingResponse(
            buf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{safe_title}.pdf"'},
        )

    if body.format == "pptx":
        from pptx import Presentation
        from pptx.util import Inches, Pt

        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

        # Title slide
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        slide.shapes.title.text = title
        slide.placeholders[1].text = "Generated by Saibyl"

        # Section slides
        for sec in sections:
            slide = prs.slides.add_slide(prs.slide_layouts[1])
            slide.shapes.title.text = sec["title"]
            content = sec.get("content") or ""
            # Strip markdown formatting for plain text slides
            plain = re.sub(r"[#*_`>]", "", content)
            tf = slide.placeholders[1].text_frame
            tf.text = plain[:3000]
            for para in tf.paragraphs:
                para.font.size = Pt(14)

        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers={"Content-Disposition": f'attachment; filename="{safe_title}.pptx"'},
        )

    raise HTTPException(status_code=400, detail=f"Unsupported format: {body.format}. Use json, pdf, or pptx.")


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
