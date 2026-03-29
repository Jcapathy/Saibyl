from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends

from app.core.auth import get_current_org
from app.services.engine.personas.pack_loader import get_pack, list_available_packs

log = structlog.get_logger()

router = APIRouter(tags=["persona-packs"])


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def list_packs(auth: dict = Depends(get_current_org)):
    """List all available persona packs."""
    log.info("list_persona_packs", org_id=auth["org_id"])
    packs = list_available_packs()
    return [p.model_dump() for p in packs]


@router.get("/{pack_id}")
async def get_pack_details(pack_id: str, auth: dict = Depends(get_current_org)):
    """Get details of a specific persona pack."""
    log.info("get_persona_pack", pack_id=pack_id, org_id=auth["org_id"])
    pack = get_pack(pack_id)
    return pack.model_dump()
