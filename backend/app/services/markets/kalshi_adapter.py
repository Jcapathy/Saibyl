# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# fetch_market(ticker: str, api_key: str) -> dict
# search_markets(query: str, api_key: str, limit: int) -> list[dict]
# get_orderbook(ticker: str, api_key: str) -> dict
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import httpx
import structlog

logger = structlog.get_logger()

BASE_URL = "https://trading-api.kalshi.com/trade-api/v2"


async def fetch_market(ticker: str, api_key: str) -> dict:
    """Fetch Kalshi market details by ticker."""
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{BASE_URL}/markets/{ticker}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()
        market = response.json().get("market", {})

        return {
            "platform": "kalshi",
            "external_id": market.get("ticker", ticker),
            "external_url": f"https://kalshi.com/markets/{ticker}",
            "title": market.get("title", ""),
            "description": market.get("subtitle", ""),
            "resolution_rules": market.get("rules_primary", ""),
            "closes_at": market.get("close_time"),
            "market_type": _detect_type(market),
            "outcomes": _extract_outcomes(market),
            "volume_usd": market.get("volume", 0),
            "open_interest_usd": market.get("open_interest", 0),
            "status": "open" if market.get("status") == "active" else market.get("status", "open"),
        }


async def search_markets(query: str, api_key: str, limit: int = 20) -> list[dict]:
    """Search Kalshi markets by keyword."""
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{BASE_URL}/markets",
            params={"status": "open", "limit": limit},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()
        markets = response.json().get("markets", [])

        # Client-side filter by query
        query_lower = query.lower()
        filtered = [m for m in markets if query_lower in (m.get("title", "") + m.get("subtitle", "")).lower()]

        return [
            {
                "external_id": m.get("ticker"),
                "title": m.get("title"),
                "current_probability": m.get("yes_bid", 0) / 100 if m.get("yes_bid") else None,
                "volume_usd": m.get("volume"),
                "closes_at": m.get("close_time"),
                "url": f"https://kalshi.com/markets/{m.get('ticker')}",
            }
            for m in filtered[:limit]
        ]


async def get_orderbook(ticker: str, api_key: str) -> dict:
    """Fetch current orderbook for price data."""
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{BASE_URL}/markets/{ticker}/orderbook",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()
        return response.json().get("orderbook", {})


def _detect_type(market: dict) -> str:
    if market.get("can_close_early"):
        return "binary"
    return "binary"


def _extract_outcomes(market: dict) -> list[dict]:
    yes_price = market.get("yes_bid", 50) / 100 if market.get("yes_bid") else 0.5
    return [
        {"label": "Yes", "current_probability": yes_price},
        {"label": "No", "current_probability": 1 - yes_price},
    ]
