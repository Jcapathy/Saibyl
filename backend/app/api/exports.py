from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_org
from app.workers.export_tasks import task_export_report, task_export_simulation

router = APIRouter(tags=["exports"])


class ExportRequest(BaseModel):
    format: str = "pdf"  # pdf | pptx | json


@router.post("/reports/{report_id}/export")
async def export_report(report_id: str, body: ExportRequest, auth: dict = Depends(get_current_org)):
    """Queue report export as background task."""
    if body.format not in ("pdf", "pptx", "json"):
        raise HTTPException(400, "Format must be pdf, pptx, or json")

    task = task_export_report.delay(report_id, body.format)
    return {"task_id": task.id, "status": "queued", "format": body.format}


@router.post("/simulations/{simulation_id}/export")
async def export_simulation(simulation_id: str, auth: dict = Depends(get_current_org)):
    """Queue simulation data export (JSON) as background task."""
    task = task_export_simulation.delay(simulation_id)
    return {"task_id": task.id, "status": "queued", "format": "json"}


@router.get("/export-tasks/{task_id}")
async def get_export_task_status(task_id: str, auth: dict = Depends(get_current_org)):
    """Check export task status."""
    from celery.result import AsyncResult

    result = AsyncResult(task_id)

    if result.state == "PENDING":
        return {"task_id": task_id, "status": "queued"}
    elif result.state == "STARTED":
        return {"task_id": task_id, "status": "processing"}
    elif result.state == "SUCCESS":
        data = result.result or {}
        return {
            "task_id": task_id,
            "status": "complete",
            "download_url": data.get("download_url"),
            "file_size_bytes": data.get("file_size_bytes"),
            "format": data.get("format"),
        }
    elif result.state == "FAILURE":
        return {"task_id": task_id, "status": "failed", "error": str(result.result)}
    else:
        return {"task_id": task_id, "status": result.state}
