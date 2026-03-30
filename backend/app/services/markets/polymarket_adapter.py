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

        # Build outcomes — handle both token-based and list-based response formats
        outcomes = []
        tokens = market.get("tokens", [])
        if tokens:
            # Full market detail response (has tokens with token_ids)
            for token in tokens:
                prob = await _get_token_probability(token.get("token_id", ""))
                outcomes.append({
                    "label": token.get("outcome", ""),
                    "current_probability": prob,
                    "token_id": token.get("token_id"),
                })
        else:
            # Slug/search response (outcomes as string list, outcomePrices as string list)
            outcome_labels = market.get("outcomes", [])
            outcome_prices = market.get("outcomePrices", [])
            if isinstance(outcome_labels, str):
                import json as _json
                try:
                    outcome_labels = _json.loads(outcome_labels)
                except Exception:
                    outcome_labels = []
            if isinstance(outcome_prices, str):
                import json as _json
                try:
                    outcome_prices = _json.loads(outcome_prices)
                except Exception:
                    outcome_prices = []
            for i, label in enumerate(outcome_labels):
                prob = float(outcome_prices[i]) if i < len(outcome_prices) else 0.5
                outcomes.append({
                    "label": label,
                    "current_probability": prob,
                })

        # Handle field name variations between response formats
        condition_id = market.get("condition_id") or market.get("conditionId") or condition_id_or_slug
        slug = market.get("slug", condition_id_or_slug)
        volume = market.get("volume_num") or market.get("volume") or 0
        liquidity = market.get("liquidity_num") or market.get("liquidity") or 0
        end_date = market.get("end_date_iso") or market.get("endDate")
        num_outcomes = len(tokens) if tokens else len(outcomes)

        # Extract market context from event metadata (Polymarket AI-generated context)
        market_context = ""
        events = market.get("events") or []
        if events and isinstance(events, list):
            event_meta = events[0].get("eventMetadata") or {}
            market_context = event_meta.get("context_description", "")

        return {
            "platform": "polymarket",
            "external_id": condition_id,
            "external_url": f"https://polymarket.com/event/{slug}",
            "title": market.get("question", ""),
            "description": market.get("description", ""),
            "resolution_rules": market.get("resolution_source") or market.get("resolutionSource", ""),
            "market_context": market_context,
            "closes_at": end_date,
            "market_type": "binary" if num_outcomes == 2 else "multi",
            "outcomes": outcomes,
            "volume_usd": float(volume) if volume else 0,
            "open_interest_usd": float(liquidity) if liquidity else 0,
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
