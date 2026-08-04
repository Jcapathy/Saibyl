import hashlib
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.core.database import get_supabase, get_supabase_admin

security = HTTPBearer()
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> dict:
    """Validate Supabase JWT and return user data."""
    supabase = get_supabase()
    try:
        response = supabase.auth.get_user(credentials.credentials)
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
    """Return the user's active organization.

    Ordering is load-bearing, not cosmetic. `.limit(1)` with no `.order()`
    leaves the row to Postgres' plan, so a user in two orgs could be answered
    with a different org on two consecutive requests — writing a simulation into
    one org and then failing to read it back from the other.

    The choice is oldest membership first: for the overwhelming majority of
    users that is the org created for them at signup, and it is stable for the
    lifetime of the membership. `organization_id` breaks ties, because two rows
    can share a `joined_at` timestamp and the ordering has to be total.

    This is determinism, not org selection. Letting a user *choose* their active
    org is the Phase 4 switcher, and it belongs in a request header or the
    `user_profiles.default_organization_id` column, not here.
    """
    admin = get_supabase_admin()
    result = (
        admin.table("organization_members")
        .select("organization_id, role, organizations(id, name, slug, plan)")
        .eq("user_id", user["id"])
        .order("joined_at", desc=False)
        .order("organization_id", desc=False)
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
