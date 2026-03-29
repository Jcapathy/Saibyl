# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# dispatch_webhook(org_id, event_type, payload) -> None
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import hashlib
import hmac
import uuid
from uuid import UUID

import httpx
import structlog

from app.core.database import get_supabase_admin

logger = structlog.get_logger()

WEBHOOK_EVENTS = [
    "simulation.started",
    "simulation.round_complete",
    "simulation.complete",
    "simulation.failed",
    "simulation.stopped",
    "report.started",
    "report.section_complete",
    "report.complete",
    "report.failed",
]

MAX_FAILURE_COUNT = 10


def _sign_payload(payload_bytes: bytes, secret: str) -> str:
    """HMAC-SHA256 sign the payload."""
    return "sha256=" + hmac.new(
        secret.encode(), payload_bytes, hashlib.sha256
    ).hexdigest()


async def dispatch_webhook(org_id: UUID, event_type: str, payload: dict) -> None:
    """Dispatch webhook to all active endpoints for the org matching the event type."""
    admin = get_supabase_admin()

    webhooks = admin.table("webhooks").select("*").eq(
        "organization_id", str(org_id)
    ).eq("is_active", True).execute().data

    if not webhooks:
        return

    import json
    payload_bytes = json.dumps(payload, default=str).encode()

    async with httpx.AsyncClient(timeout=10.0) as client:
        for wh in webhooks:
            # Check if webhook subscribes to this event type
            if event_type not in (wh.get("events") or []):
                continue

            delivery_id = str(uuid.uuid4())
            signature = _sign_payload(payload_bytes, wh["secret"])

            headers = {
                "Content-Type": "application/json",
                "X-Saibyl-Signature": signature,
                "X-Saibyl-Event": event_type,
                "X-Saibyl-Delivery": delivery_id,
            }
            # Add custom headers
            custom = wh.get("custom_headers") or {}
            headers.update(custom)

            try:
                response = await client.post(
                    wh["url"],
                    content=payload_bytes,
                    headers=headers,
                )
                success = 200 <= response.status_code < 300

                if success:
                    admin.table("webhooks").update({
                        "last_triggered_at": "now()",
                        "failure_count": 0,
                    }).eq("id", wh["id"]).execute()
                else:
                    new_count = (wh.get("failure_count") or 0) + 1
                    updates = {"failure_count": new_count}
                    if new_count >= MAX_FAILURE_COUNT:
                        updates["is_active"] = False
                        logger.warning("webhook_disabled", webhook_id=wh["id"], url=wh["url"])
                    admin.table("webhooks").update(updates).eq("id", wh["id"]).execute()

                logger.info(
                    "webhook_delivered",
                    webhook_id=wh["id"],
                    event=event_type,
                    status=response.status_code,
                    delivery_id=delivery_id,
                )

            except Exception as e:
                new_count = (wh.get("failure_count") or 0) + 1
                updates = {"failure_count": new_count}
                if new_count >= MAX_FAILURE_COUNT:
                    updates["is_active"] = False
                admin.table("webhooks").update(updates).eq("id", wh["id"]).execute()
                logger.error("webhook_failed", webhook_id=wh["id"], error=str(e))
