from __future__ import annotations

import asyncio

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_org
from app.workers.export_tasks import run_export_report, run_export_simulation

log = structlog.get_logger()

router = APIRouter(tags=["exports"])


async def _safe_task(coro, name: str):
    try:
        await coro
    except Exception:
        log.exception("background_task_failed", task=name)


class ExportRequest(BaseModel):
    format: str = "pdf"  # pdf | pptx | json


@router.post("/reports/{report_id}/export")
async def export_report(report_id: str, body: ExportRequest, auth: dict = Depends(get_current_org)):
    """Queue report export as background task."""
    if body.format not in ("pdf", "pptx", "json"):
        raise HTTPException(400, "Format must be pdf, pptx, or json")

    asyncio.create_task(_safe_task(run_export_report(report_id, body.format), "export_report"))
    return {"status": "started", "format": body.format}


@router.post("/simulations/{simulation_id}/export")
async def export_simulation(simulation_id: str, auth: dict = Depends(get_current_org)):
    """Queue simulation data export (JSON) as background task."""
    asyncio.create_task(_safe_task(run_export_simulation(simulation_id), "export_simulation"))
    return {"status": "started", "format": "json"}
