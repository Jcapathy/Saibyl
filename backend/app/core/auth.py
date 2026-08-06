
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.database import get_supabase, get_supabase_admin

security = HTTPBearer()


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


