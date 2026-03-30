from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_org
from app.core.database import get_supabase_admin
from app.core.security import validate_external_url
from app.services.markets.encryption import encrypt_key
from app.services.markets.market_importer import import_from_url, refresh_market, search_markets

router = APIRouter(tags=["markets"])


class ImportRequest(BaseModel):
    url: str


class SearchRequest(BaseModel):
    query: str
    platform: str = "polymarket"
    limit: int = 20


class SaveKeyRequest(BaseModel):
    platform: str
    api_key: str


# ── Market CRUD ──────────────────────────────────────────

@router.post("/import")
async def import_market(body: ImportRequest, auth: dict = Depends(get_current_org)):
    """Import a market from URL (auto-detects Kalshi/Polymarket)."""
    validate_external_url(body.url)
    try:
        result = await import_from_url(body.url, auth["org_id"])
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/search")
async def search(query: str, platform: str = "polymarket", limit: int = 20, auth: dict = Depends(get_current_org)):
    """Search markets on a platform."""
    try:
        results = await search_markets(query, platform, auth["org_id"], limit)
        return results
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("")
async def list_markets(auth: dict = Depends(get_current_org)):
    """List org's imported markets."""
    admin = get_supabase_admin()
    result = admin.table("prediction_markets").select("*").eq(
        "organization_id", auth["org_id"]
    ).order("created_at", desc=True).execute()
    return result.data


@router.get("/{market_id}")
async def get_market(market_id: str, auth: dict = Depends(get_current_org)):
    """Get market details + prediction history."""
    admin = get_supabase_admin()
    market = admin.table("prediction_markets").select("*").eq(
        "id", market_id
    ).eq("organization_id", auth["org_id"]).single().execute()
    if not market.data:
        raise HTTPException(404, "Market not found")

    predictions = admin.table("market_predictions").select("*").eq(
        "market_id", market_id
    ).order("created_at", desc=True).execute()

    return {**market.data, "predictions": predictions.data}


@router.delete("/{market_id}")
async def delete_market(market_id: str, auth: dict = Depends(get_current_org)):
    """Remove an imported market."""
    admin = get_supabase_admin()
    admin.table("prediction_markets").delete().eq(
        "id", market_id
    ).eq("organization_id", auth["org_id"]).execute()
    return {"message": "Market removed"}


@router.post("/{market_id}/refresh")
async def refresh(market_id: str, auth: dict = Depends(get_current_org)):
    """Re-fetch latest prices for a market."""
    try:
        result = await refresh_market(market_id)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── Predictions ──────────────────────────────────────────

@router.post("/{market_id}/predict")
async def run_prediction(market_id: str, auth: dict = Depends(get_current_org)):
    """Run a new prediction simulation for a market."""
    import asyncio
    from app.workers.market_tasks import run_market_prediction

    async def _safe_task(coro, name: str):
        try:
            await coro
        except Exception:
            import structlog
            structlog.get_logger().exception("background_task_failed", task=name)

    asyncio.create_task(_safe_task(run_market_prediction(market_id, auth["org_id"]), "market_prediction"))
    return {"status": "started"}


@router.get("/{market_id}/predictions")
async def list_predictions(market_id: str, auth: dict = Depends(get_current_org)):
    """List all prediction runs for a market."""
    admin = get_supabase_admin()
    result = admin.table("market_predictions").select("*").eq(
        "market_id", market_id
    ).eq("organization_id", auth["org_id"]).order("created_at", desc=True).execute()
    return result.data


@router.get("/predictions/{prediction_id}")
async def get_prediction(prediction_id: str, auth: dict = Depends(get_current_org)):
    """Get a single prediction result."""
    admin = get_supabase_admin()
    result = admin.table("market_predictions").select("*").eq(
        "id", prediction_id
    ).eq("organization_id", auth["org_id"]).single().execute()
    if not result.data:
        raise HTTPException(404, "Prediction not found")
    return result.data


# ── API Key Management ───────────────────────────────────

@router.post("/keys")
async def save_api_key(body: SaveKeyRequest, auth: dict = Depends(get_current_org)):
    """Save encrypted API key for a platform (e.g., Kalshi)."""
    admin = get_supabase_admin()
    encrypted = encrypt_key(body.api_key)
    preview = body.api_key[-4:]

    admin.table("market_api_keys").upsert({
        "organization_id": auth["org_id"],
        "platform": body.platform,
        "encrypted_key": encrypted,
        "key_preview": f"...{preview}",
    }, on_conflict="organization_id").execute()

    return {"platform": body.platform, "key_preview": f"...{preview}", "message": "Key saved"}


@router.delete("/keys/{platform}")
async def delete_api_key(platform: str, auth: dict = Depends(get_current_org)):
    """Remove stored API key for a platform."""
    admin = get_supabase_admin()
    admin.table("market_api_keys").delete().eq(
        "organization_id", auth["org_id"]
    ).eq("platform", platform).execute()
    return {"message": f"{platform} key removed"}


@router.get("/keys")
async def list_api_keys(auth: dict = Depends(get_current_org)):
    """List stored key platforms (no actual key values)."""
    admin = get_supabase_admin()
    result = admin.table("market_api_keys").select(
        "platform, key_preview, created_at"
    ).eq("organization_id", auth["org_id"]).execute()
    return result.data
