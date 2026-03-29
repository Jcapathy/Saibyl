from __future__ import annotations

import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_org
from app.core.database import get_supabase_admin

router = APIRouter(tags=["api-keys"])


class CreateKeyRequest(BaseModel):
    name: str
    scopes: list[str] = ["simulations:read", "simulations:write"]


class UpdateKeyRequest(BaseModel):
    name: str | None = None
    scopes: list[str] | None = None


def _generate_api_key(environment: str = "live") -> tuple[str, str, str]:
    """Returns (full_key, key_hash, key_prefix)."""
    raw = secrets.token_urlsafe(32)
    full_key = f"sk_{environment}_{raw}"
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    key_prefix = full_key[:12]
    return full_key, key_hash, key_prefix


@router.get("")
async def list_keys(auth: dict = Depends(get_current_org)):
    """List org's API keys (prefix only, never full key)."""
    admin = get_supabase_admin()
    keys = admin.table("api_keys").select(
        "id, name, key_prefix, scopes, last_used_at, expires_at, revoked_at, created_at"
    ).eq("organization_id", auth["org_id"]).order("created_at", desc=True).execute()
    return keys.data


@router.post("")
async def create_key(body: CreateKeyRequest, auth: dict = Depends(get_current_org)):
    """Create a new API key. Returns the full key ONCE."""
    if auth["role"] not in ("owner", "admin"):
        raise HTTPException(403, "Only owners/admins can create API keys")

    admin = get_supabase_admin()
    env = "test" if auth["org"].get("plan") == "trialing" else "live"
    full_key, key_hash, key_prefix = _generate_api_key(env)

    result = admin.table("api_keys").insert({
        "organization_id": auth["org_id"],
        "created_by": auth["user"]["id"],
        "name": body.name,
        "key_hash": key_hash,
        "key_prefix": key_prefix,
        "scopes": body.scopes,
    }).execute()

    return {
        "id": result.data[0]["id"],
        "key": full_key,  # shown only once
        "key_prefix": key_prefix,
        "name": body.name,
        "scopes": body.scopes,
        "message": "Save this key — it will not be shown again.",
    }


@router.delete("/{key_id}")
async def revoke_key(key_id: str, auth: dict = Depends(get_current_org)):
    """Revoke an API key."""
    admin = get_supabase_admin()
    from datetime import UTC, datetime

    result = admin.table("api_keys").update({
        "revoked_at": datetime.now(UTC).isoformat(),
    }).eq("id", key_id).eq("organization_id", auth["org_id"]).execute()

    if not result.data:
        raise HTTPException(404, "API key not found")
    return {"message": "Key revoked"}


@router.patch("/{key_id}")
async def update_key(key_id: str, body: UpdateKeyRequest, auth: dict = Depends(get_current_org)):
    """Update API key name or scopes."""
    admin = get_supabase_admin()
    updates = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.scopes is not None:
        updates["scopes"] = body.scopes
    if not updates:
        raise HTTPException(400, "Nothing to update")

    result = admin.table("api_keys").update(updates).eq(
        "id", key_id
    ).eq("organization_id", auth["org_id"]).execute()

    if not result.data:
        raise HTTPException(404, "API key not found")
    return result.data[0]
