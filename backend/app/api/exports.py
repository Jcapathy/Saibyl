"""Export endpoints.

These used to hand the work to `asyncio.create_task` behind a wrapper that
logged and swallowed every exception, then return `{"status": "started"}`. Three
things followed from that, and all three are the same mistake:

* A failed export was indistinguishable from a successful one. The PDF path had
  been broken since `simulation_analytics` was refactored, and the API kept
  reporting success for it.
* Even a *successful* export was unreachable. `run_export_report` returns the
  signed download URL, and `create_task` throws the return value away, so
  nothing the caller could do would get them the file.
* A fire-and-forget task holds no reference, so it can be garbage-collected
  mid-flight.

So the export is awaited and its URL returned. It is a database read plus a
render — seconds, not minutes — and the typesetting itself runs off the event
loop. A failure is now an HTTP error with a reason in it.
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_org
from app.core.database import get_supabase_admin
from app.services.export.pdf_exporter import ExportError
from app.workers.export_tasks import run_export_report, run_export_simulation

log = structlog.get_logger()

router = APIRouter(tags=["exports"])

FORMATS = ("pdf", "pptx", "json")


class ExportRequest(BaseModel):
    format: str = "pdf"  # pdf | pptx | json


async def _run(coro, *, kind: str, **context: object) -> dict:
    """Await an export, turning every failure into a stated HTTP error."""
    try:
        result = await coro
    except ExportError as exc:
        log.warning("export_failed", kind=kind, reason=str(exc), **context)
        raise HTTPException(status_code=500, detail=f"Export failed: {exc}") from exc
    except Exception as exc:
        log.exception("export_failed", kind=kind, **context)
        raise HTTPException(
            status_code=500, detail="Export failed while generating the file."
        ) from exc

    if not result.get("download_url"):
        log.warning("export_no_url", kind=kind, **context)
        raise HTTPException(
            status_code=500,
            detail="Export produced a file but no download URL could be signed.",
        )
    return result


@router.post("/reports/{report_id}/export")
async def export_report(
    report_id: str, body: ExportRequest, auth: dict = Depends(get_current_org)
):
    """Render a report and return a signed download URL for the file."""
    if body.format not in FORMATS:
        raise HTTPException(400, "Format must be pdf, pptx, or json")

    admin = get_supabase_admin()
    report = (
        admin.table("reports")
        .select("id, simulations!inner(organization_id)")
        .eq("id", report_id)
        .execute()
    )
    if not report.data or report.data[0]["simulations"]["organization_id"] != auth["org_id"]:
        raise HTTPException(404, "Report not found")

    return await _run(
        run_export_report(report_id, body.format),
        kind="report",
        report_id=report_id,
        format=body.format,
    )


@router.post("/simulations/{simulation_id}/export")
async def export_simulation(simulation_id: str, auth: dict = Depends(get_current_org)):
    """Export the full simulation record as gzipped JSON."""
    admin = get_supabase_admin()
    sim = (
        admin.table("simulations")
        .select("id")
        .eq("id", simulation_id)
        .eq("organization_id", auth["org_id"])
        .limit(1)
        .execute()
    )
    if not sim.data:
        raise HTTPException(404, "Simulation not found")

    return await _run(
        run_export_simulation(simulation_id),
        kind="simulation",
        simulation_id=simulation_id,
    )
