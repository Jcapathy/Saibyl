# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# fetch_market(condition_id: str) -> dict
# search_markets(query: str, limit: int) -> list[dict]
# get_midpoint(token_id: str) -> float
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import httpx
import structlog

logger = structlog.get_logger()

GAMMA_URL = "https://gamma-api.polymarket.com"
CLOB_URL = "https://clob.polymarket.com"


async def fetch_market(condition_id_or_slug: str) -> dict:
    """Fetch Polymarket market by condition ID or slug."""
    async with httpx.AsyncClient(timeout=15) as client:
        # Try direct condition ID lookup first
        try:
            response = await client.get(f"{GAMMA_URL}/markets/{condition_id_or_slug}")
            response.raise_for_status()
            market = response.json()
        except httpx.HTTPStatusError:
            # Fallback: search by slug
            response = await client.get(
                f"{GAMMA_URL}/markets",
                params={"slug": condition_id_or_slug, "_limit": 1},
            )
            response.raise_for_status()
            results = response.json()
            if isinstance(results, list) and results:
                market = results[0]
            elif isinstance(results, dict) and results.get("data"):
                market = results["data"][0]
            else:
                raise ValueError(f"Market not found: {condition_id_or_slug}")

        outcomes = []
        for token in market.get("tokens", []):
            prob = await _get_token_probability(token.get("token_id", ""))
            outcomes.append({
                "label": token.get("outcome", ""),
                "current_probability": prob,
                "token_id": token.get("token_id"),
            })

        return {
            "platform": "polymarket",
            "external_id": market.get("condition_id", condition_id),
            "external_url": f"https://polymarket.com/event/{market.get('slug', condition_id)}",
            "title": market.get("question", ""),
            "description": market.get("description", ""),
            "resolution_rules": market.get("resolution_source", ""),
            "closes_at": market.get("end_date_iso"),
            "market_type": "binary" if len(market.get("tokens", [])) == 2 else "multi",
            "outcomes": outcomes,
            "volume_usd": market.get("volume_num", 0),
            "open_interest_usd": market.get("liquidity_num", 0),
            "status": "open" if market.get("active") else "closed",
        }


async def search_markets(query: str, limit: int = 20) -> list[dict]:
    """Search Polymarket markets by keyword."""
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{GAMMA_URL}/markets",
            params={"_q": query, "active": True, "_limit": limit},
        )
        response.raise_for_status()
        markets = response.json()

        if isinstance(markets, dict):
            markets = markets.get("data", [])

        return [
            {
                "external_id": m.get("condition_id"),
                "title": m.get("question"),
                "current_probability": None,  # requires CLOB call per market
                "volume_usd": m.get("volume_num"),
                "closes_at": m.get("end_date_iso"),
                "url": f"https://polymarket.com/event/{m.get('slug', '')}",
            }
            for m in (markets if isinstance(markets, list) else [])[:limit]
        ]


async def _get_token_probability(token_id: str) -> float:
    """Get midpoint price for a token from CLOB."""
    if not token_id:
        return 0.5
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{CLOB_URL}/midpoint",
                params={"token_id": token_id},
            )
            response.raise_for_status()
            data = response.json()
            return float(data.get("mid", 0.5))
    except Exception:
        return 0.5


async def get_midpoint(token_id: str) -> float:
    """Public wrapper for midpoint price."""
    return await _get_token_probability(token_id)
