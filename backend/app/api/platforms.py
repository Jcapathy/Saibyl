from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends

from app.core.auth import get_current_org
from app.services.platforms.registry import list_available_platforms, load_all_adapters

log = structlog.get_logger()

router = APIRouter(tags=["platforms"])


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/")
async def list_platforms(auth: dict = Depends(get_current_org)):
    """List all available simulation platforms."""
    log.info("list_platforms", org_id=auth["org_id"])
    load_all_adapters()
    platforms = list_available_platforms()
    return [p.model_dump() for p in platforms]
