# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# get_current_user(credentials) -> dict           [async]
# get_current_org(user) -> dict                   [async]
# require_can_spend(auth) -> dict                 [async] — money leaves the balance
# require_can_destroy(auth) -> dict               [async] — work is deleted for good
# SPENDING_ROLES, DESTRUCTIVE_ROLES
# ─────────────────────────────────────────────────────────
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.database import get_supabase, get_supabase_admin

log = structlog.get_logger()

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


# ---------------------------------------------------------------------------
# Role gates — who may spend the balance, and who may delete what it bought
# ---------------------------------------------------------------------------
#
# `get_current_org` has always returned `role`, and until now nothing outside
# `organizations.py` and two billing routes read it. That meant a `viewer` —
# the role whose entire name is the contract — could order a 5,000-credit page
# revision, a 3,000-credit family-office shortlist, or call `POST /gtm/purge`
# and delete every candidate the org had ever paid to discover.
#
# Two gates, because there are two different acts here and one line does not
# fit both.
#
# **Spending: owner, admin, member.** A member is the ordinary invited
# teammate — `InviteMemberBody` only offers `member` and `viewer`, and `member`
# is the default — so a member who cannot spend cannot use the product at all,
# and every invitation becomes decorative. Spending the balance *is* using the
# product: `RunCaps` says so directly ("caps exist to stop accidents, not to
# ration — the credit balance rations"), and the balance is granted to the org,
# not to a person. Note the deliberate seam with `POST /billing/checkout` and
# `/billing/portal`, which are already owner/admin: buying credits commits the
# org's money to Stripe, spending them commits capacity the org already owns.
# Those are different decisions and they get different gates.
#
# **Destruction: owner and admin.** The asymmetry is recoverability, and it is
# the whole argument. A member who spends 3,000 credits by mistake has bought
# something: there is an artifact, a `credits_charged` row, and a top-up that
# undoes the damage with money. A member who calls `DELETE /simulations/{id}`
# has destroyed the artifact *and* the money that bought it — that route
# cascades through `report_sections`, `reports`, `simulation_events` and
# `simulation_agents` — and nothing undoes it. Irreversible removal of shared
# work is an administrative act, and it belongs with the same pair that already
# governs membership and billing.
#
# **A viewer does neither.** That is not a judgement call; it is what the word
# means, and it is the promise made to whoever assigned the role.
SPENDING_ROLES: tuple[str, ...] = ("owner", "admin", "member")
DESTRUCTIVE_ROLES: tuple[str, ...] = ("owner", "admin")


def _role_gate(
    allowed: tuple[str, ...], act: str, refusal: str
) -> Callable[[dict], Awaitable[dict]]:
    """Build the dependency that admits `allowed` and refuses everyone else.

    A dependency rather than a helper the route calls, so that a route cannot
    hold `auth` without having passed the gate — the check is not something a
    new handler has to remember to write, it is the only way to get the value
    it needs. That is the same reasoning `capital/schema` uses for validating
    by types instead of by convention.

    **Allowlist, and `.get` rather than `[]`.** `organization_members.role` is
    a bare `TEXT` column with no CHECK constraint, so an unrecognised string is
    storable; an allowlist refuses it, a denylist would wave it through. And a
    caller that assembled an auth dict without a role has not proved anything
    about its permissions, so it is refused rather than crashed on — 403 is the
    honest answer to "we cannot tell", and a KeyError would be a 500 that reads
    as our fault.

    403 rather than the 404 `require_platform_admin` uses: that gate hides a
    surface that must not confirm its own existence, while this one refuses a
    legitimate member of the org at a route they can see in the UI. Telling
    them which role they need is the point.
    """
    async def _dependency(auth: dict = Depends(get_current_org)) -> dict:  # noqa: D103
        role = auth.get("role")
        if role not in allowed:
            log.warning(
                "role_refused",
                act=act,
                role=role,
                org_id=auth.get("org_id"),
                user_id=(auth.get("user") or {}).get("id"),
            )
            raise HTTPException(status_code=403, detail=refusal)
        return auth

    # Named, so a traceback and the generated OpenAPI schema say which gate
    # refused rather than pointing at three identical `_dependency` closures.
    _dependency.__name__ = f"require_can_{act}"
    _dependency.__qualname__ = _dependency.__name__
    return _dependency


require_can_spend = _role_gate(
    SPENDING_ROLES,
    "spend",
    "Your access to this workspace is view-only, so you can't start work that "
    "spends its credits. Ask an owner or admin to run it.",
)

require_can_destroy = _role_gate(
    DESTRUCTIVE_ROLES,
    "destroy",
    "Only an owner or admin can delete this — it cannot be undone. Ask one of "
    "them, or ask to be made an admin.",
)


