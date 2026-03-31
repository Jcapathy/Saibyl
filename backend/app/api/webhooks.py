from __future__ import annotations

import re
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from app.core.auth import get_current_org
from app.core.database import get_supabase_admin
from app.core.security import validate_external_url

router = APIRouter(tags=["webhooks"])

_FORBIDDEN_HEADERS = frozenset({
    "host", "authorization", "cookie", "transfer-encoding",
    "content-length", "content-type", "connection", "upgrade",
})


def _validate_custom_headers(v: dict) -> dict:
    for key in v:
        if key.lower() in _FORBIDDEN_HEADERS:
            raise ValueError(f"Header '{key}' is not allowed as a custom header")
        if not re.match(r"^[a-zA-Z0-9-]+$", key):
            raise ValueError(f"Header name '{key}' contains invalid characters")
    return v


class CreateWebhookRequest(BaseModel):
    url: str
    events: list[str]
    custom_headers: dict = {}

    @field_validator("custom_headers")
    @classmethod
    def check_headers(cls, v: dict) -> dict:
        return _validate_custom_headers(v)


class UpdateWebhookRequest(BaseModel):
    url: str | None = None
    events: list[str] | None = None
    is_active: bool | None = None
    custom_headers: dict | None = None

    @field_validator("custom_headers")
    @classmethod
    def check_headers(cls, v: dict | None) -> dict | None:
        if v is not None:
            return _validate_custom_headers(v)
        return v


@router.get("")
async def list_webhooks(auth: dict = Depends(get_current_org)):
    """List org's webhooks."""
    admin = get_supabase_admin()
    result = admin.table("webhooks").select("*").eq(
        "organization_id", auth["org_id"]
    ).order("created_at", desc=True).execute()
    # Mask the secret
    for wh in result.data:
        wh["secret"] = wh["secret"][:8] + "..." if wh.get("secret") else None
    return result.data


@router.post("")
async def create_webhook(body: CreateWebhookRequest, auth: dict = Depends(get_current_org)):
    """Create a new webhook endpoint."""
    validate_external_url(body.url)
    admin = get_supabase_admin()
    wh_secret = secrets.token_hex(32)

    result = admin.table("webhooks").insert({
        "organization_id": auth["org_id"],
        "created_by": auth["user"]["id"],
        "url": body.url,
        "events": body.events,
        "secret": wh_secret,
        "custom_headers": body.custom_headers,
    }).execute()

    data = result.data[0]
    data["secret"] = wh_secret  # show full secret once on creation
    return data


@router.patch("/{webhook_id}")
async def update_webhook(
    webhook_id: str, body: UpdateWebhookRequest, auth: dict = Depends(get_current_org)
):
    """Update a webhook."""
    admin = get_supabase_admin()
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "Nothing to update")
    if body.url is not None:
        validate_external_url(body.url)

    result = admin.table("webhooks").update(updates).eq(
        "id", webhook_id
    ).eq("organization_id", auth["org_id"]).execute()

    if not result.data:
        raise HTTPException(404, "Webhook not found")
    return result.data[0]


@router.delete("/{webhook_id}")
async def delete_webhook(webhook_id: str, auth: dict = Depends(get_current_org)):
    """Delete a webhook."""
    admin = get_supabase_admin()
    result = admin.table("webhooks").delete().eq(
        "id", webhook_id
    ).eq("organization_id", auth["org_id"]).execute()

    if not result.data:
        raise HTTPException(404, "Webhook not found")
    return {"message": "Webhook deleted"}
