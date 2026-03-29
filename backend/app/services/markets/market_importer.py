# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# import_from_url(url, org_id) -> dict
# search_markets(query, platform, org_id, limit) -> list[dict]
# refresh_market(market_id) -> dict
# ─────────────────────────────────────────────────────────
from __future__ import annotations

from uuid import UUID

import structlog

from app.core.database import get_supabase_admin
from app.services.markets import kalshi_adapter, polymarket_adapter
from app.services.markets.encryption import decrypt_key

logger = structlog.get_logger()


def _detect_platform(url: str) -> str:
    if "kalshi.com" in url:
        return "kalshi"
    if "polymarket.com" in url:
        return "polymarket"
    raise ValueError(f"Unsupported market URL: {url}")


def _extract_id_from_url(url: str, platform: str) -> str:
    """Extract market ID or ticker from URL."""
    parts = url.rstrip("/").split("/")
    if platform == "kalshi":
        # https://kalshi.com/markets/TICKER or /events/.../markets/TICKER
        return parts[-1]
    elif platform == "polymarket":
        # https://polymarket.com/event/SLUG
        return parts[-1]
    return parts[-1]


async def _get_kalshi_key(org_id: UUID) -> str | None:
    """Get decrypted Kalshi API key for org."""
    admin = get_supabase_admin()
    result = admin.table("market_api_keys").select("encrypted_key").eq(
        "organization_id", str(org_id)
    ).eq("platform", "kalshi").execute().data
    if result:
        return decrypt_key(result[0]["encrypted_key"])
    return None


async def import_from_url(url: str, org_id: UUID) -> dict:
    """Import a market from URL, auto-detecting platform."""
    admin = get_supabase_admin()
    platform = _detect_platform(url)
    external_id = _extract_id_from_url(url, platform)

    if platform == "kalshi":
        api_key = await _get_kalshi_key(org_id)
        if not api_key:
            raise ValueError("Kalshi API key not configured. Add it in Settings > Integrations.")
        market_data = await kalshi_adapter.fetch_market(external_id, api_key)
    elif platform == "polymarket":
        market_data = await polymarket_adapter.fetch_market(external_id)
    else:
        raise ValueError(f"Unsupported platform: {platform}")

    # Upsert into prediction_markets
    result = admin.table("prediction_markets").upsert({
        "organization_id": str(org_id),
        **market_data,
    }, on_conflict="organization_id,platform,external_id").execute()

    logger.info("market_imported", platform=platform, external_id=external_id)
    return result.data[0]


async def search_markets(
    query: str, platform: str, org_id: UUID, limit: int = 20
) -> list[dict]:
    """Search markets on a given platform."""
    if platform == "kalshi":
        api_key = await _get_kalshi_key(org_id)
        if not api_key:
            raise ValueError("Kalshi API key required")
        return await kalshi_adapter.search_markets(query, api_key, limit)
    elif platform == "polymarket":
        return await polymarket_adapter.search_markets(query, limit)
    else:
        raise ValueError(f"Unsupported platform: {platform}")


async def refresh_market(market_id: UUID) -> dict:
    """Refresh market prices and status."""
    admin = get_supabase_admin()
    market = admin.table("prediction_markets").select("*").eq(
        "id", str(market_id)
    ).single().execute().data

    org_id = market["organization_id"]
    platform = market["platform"]
    external_id = market["external_id"]

    if platform == "kalshi":
        api_key = await _get_kalshi_key(org_id)
        if not api_key:
            raise ValueError("Kalshi API key required")
        updated = await kalshi_adapter.fetch_market(external_id, api_key)
    elif platform == "polymarket":
        updated = await polymarket_adapter.fetch_market(external_id)
    else:
        raise ValueError(f"Unsupported platform: {platform}")

    from datetime import UTC, datetime
    admin.table("prediction_markets").update({
        "outcomes": updated["outcomes"],
        "volume_usd": updated["volume_usd"],
        "open_interest_usd": updated["open_interest_usd"],
        "status": updated["status"],
        "last_fetched_at": datetime.now(UTC).isoformat(),
    }).eq("id", str(market_id)).execute()

    logger.info("market_refreshed", market_id=str(market_id))
    return admin.table("prediction_markets").select("*").eq("id", str(market_id)).single().execute().data
