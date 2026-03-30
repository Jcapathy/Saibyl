# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# fetch_market(ticker: str, api_key: str) -> dict
# search_markets(query: str, api_key: str, limit: int) -> list[dict]
# get_orderbook(ticker: str, api_key: str) -> dict
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import base64
import time
from datetime import datetime, UTC

import httpx
import structlog
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

logger = structlog.get_logger()

BASE_URL = "https://trading-api.kalshi.com/trade-api/v2"


def _parse_key_data(api_key: str) -> tuple[str, str]:
    """Parse combined key data: 'KEY_ID|||PEM_KEY' format."""
    if "|||" in api_key:
        key_id, pem = api_key.split("|||", 1)
        return key_id.strip(), pem.strip()
    raise ValueError("Kalshi credentials must include both Key ID and RSA private key")


def _sign_request(private_key_pem: str, timestamp: int, method: str, path: str) -> str:
    """RSA-sign a Kalshi API request."""
    message = f"{timestamp}{method}{path}".encode()
    private_key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    signature = private_key.sign(message, padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(signature).decode()


def _auth_headers(api_key: str, method: str, path: str) -> dict:
    """Build Kalshi RSA auth headers."""
    key_id, pem = _parse_key_data(api_key)
    ts = int(time.time())
    sig = _sign_request(pem, ts, method, path)
    return {
        "KALSHI-ACCESS-KEY": key_id,
        "KALSHI-ACCESS-SIGNATURE": sig,
        "KALSHI-ACCESS-TIMESTAMP": str(ts),
    }


async def fetch_market(ticker: str, api_key: str) -> dict:
    """Fetch Kalshi market details by ticker."""
    path = f"/trade-api/v2/markets/{ticker}"
    headers = _auth_headers(api_key, "GET", path)
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(f"{BASE_URL}/markets/{ticker}", headers=headers)
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
    path = "/trade-api/v2/markets"
    headers = _auth_headers(api_key, "GET", path)
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{BASE_URL}/markets",
            params={"status": "open", "limit": limit},
            headers=headers,
        )
        response.raise_for_status()
        markets = response.json().get("markets", [])

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
    path = f"/trade-api/v2/markets/{ticker}/orderbook"
    headers = _auth_headers(api_key, "GET", path)
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(f"{BASE_URL}/markets/{ticker}/orderbook", headers=headers)
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
