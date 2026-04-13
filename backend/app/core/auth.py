import hashlib
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.core.database import get_supabase, get_supabase_admin

security = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> dict:
    """Validate JWT from httpOnly cookie or Authorization header and return user data."""
    # 1. Try httpOnly cookie first
    token = request.cookies.get("saibyl_access_token")

    # 2. Fall back to Authorization header (for API clients, Swagger, etc.)
    if not token and credentials:
        token = credentials.credentials

    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    supabase = get_supabase()
    try:
        response = supabase.auth.get_user(token)
        if response.user is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"id": response.user.id, "email": response.user.email}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Authentication failed")


async def get_current_org(
    user: dict = Depends(get_current_user),
) -> dict:
    """Return the user's active organization."""
    admin = get_supabase_admin()
    result = (
        admin.table("organization_members")
        .select("organization_id, role, organizations(id, name, slug, plan)")
        .eq("user_id", user["id"])
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=403, detail="No organization found")
    member = result.data[0]
    return {
        "org_id": member["organization_id"],
        "role": member["role"],
        "org": member["organizations"],
        "user": user,
    }


async def verify_api_key(
    api_key: str | None = Security(api_key_header),
) -> dict:
    """Validate API key for developer access."""
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    admin = get_supabase_admin()
    result = (
        admin.table("api_keys")
        .select("id, organization_id, scopes, expires_at, revoked_at")
        .eq("key_hash", key_hash)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=401, detail="Invalid API key")

    key_record = result.data[0]

    if key_record.get("revoked_at"):
        raise HTTPException(status_code=401, detail="Invalid API key")

    if key_record.get("expires_at"):
        expires = datetime.fromisoformat(key_record["expires_at"])
        if expires < datetime.now(UTC):
            raise HTTPException(status_code=401, detail="Invalid API key")

    # Update last_used_at
    admin.table("api_keys").update(
        {"last_used_at": datetime.now(UTC).isoformat()}
    ).eq("id", key_record["id"]).execute()

    return {
        "key_id": key_record["id"],
        "org_id": key_record["organization_id"],
        "scopes": key_record["scopes"],
    }
