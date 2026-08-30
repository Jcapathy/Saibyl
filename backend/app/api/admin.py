"""Platform-owner surfaces (PRD_V3 §4): the design gallery across every org.

Every website check leaves a design-gallery row behind; this router is where
the platform owner reads them as one feed — the raw material for the future
before/after showcase (flagged, not built). It is a read model only: nothing
here writes, charges, or mutates.

Access is by configuration, not by a role table: `ADMIN_ORGANIZATION_ID` names
the platform owner's own org, and only that org's owners and admins get an
answer. Everyone else — and everyone when the setting is empty — gets a 404,
never a 403: a surface that spans tenants must not confirm its own existence
by refusing (the crisis flag set this precedent in `api/simulations.py`).
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.auth import get_current_org
from app.core.config import settings
from app.core.database import get_supabase_admin

log = structlog.get_logger()

router = APIRouter(tags=["admin"])

LIST_LIMIT_DEFAULT = 50
LIST_LIMIT_MAX = 200


async def require_platform_admin(auth: dict = Depends(get_current_org)) -> dict:
    """Admit the platform owner's org (owner/admin role); 404 everyone else.

    One exit for all three refusals — setting empty, wrong org, wrong role —
    so a probe learns nothing from which condition it tripped.
    """
    if (
        not settings.admin_organization_id
        or auth["org_id"] != settings.admin_organization_id
        or auth.get("role") not in ("owner", "admin")
    ):
        raise HTTPException(status_code=404, detail="Not available.")
    return auth


@router.get("/design-gallery")
async def list_design_gallery(
    limit: int = Query(LIST_LIMIT_DEFAULT, ge=1, le=LIST_LIMIT_MAX),
    offset: int = Query(0, ge=0),
    auth: dict = Depends(require_platform_admin),
):
    """The gallery as one cross-org feed, newest first, without the bodies.

    `design_md`, `census` and `tokens` stay out of the list on purpose — a
    feed of 50 entries each carrying a full design document is a detail view
    pretending to be an index. The org's display name rides along so the feed
    reads as "whose site" without a second lookup.
    """
    log.info("admin_list_design_gallery", limit=limit, offset=offset)
    admin = get_supabase_admin()
    result = (
        admin.table("design_gallery")
        .select(
            "id, organization_id, snapshot_id, url, characterization, "
            "style_tags, maturity_level, overall_score, "
            "screenshot_desktop_path, screenshot_mobile_path, reference_url, "
            "created_at, organizations(name)",
            count="exact",
        )
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )

    items = []
    for row in result.data or []:
        org = row.pop("organizations", None) or {}
        items.append({**row, "organization_name": org.get("name")})

    # Each item's latest complete revision, when one exists — one batched
    # query, not one per item. `revision` is None until a revision lands; the
    # feed becomes before/after-ready the moment one does, without the reader
    # joining anything.
    revision_by_snapshot: dict[str, dict] = {}
    snapshot_ids = [item["snapshot_id"] for item in items if item.get("snapshot_id")]
    if snapshot_ids:
        revision_rows = (
            admin.table("page_revisions")
            .select("id, snapshot_id, scores_after, screenshot_desktop_path, created_at")
            .eq("status", "complete")
            .in_("snapshot_id", snapshot_ids)
            .order("created_at", desc=True)
            .execute()
        ).data or []
        for rev in revision_rows:
            # Newest first, so the first row seen per snapshot is the latest.
            revision_by_snapshot.setdefault(rev["snapshot_id"], rev)
    for item in items:
        item["revision"] = _revision_summary(
            revision_by_snapshot.get(item.get("snapshot_id"))
        )
    return {"items": items, "total": result.count, "limit": limit, "offset": offset}


def _revision_summary(revision: dict | None) -> dict | None:
    """The three fields a before/after card needs, or None when there is no after."""
    if not revision:
        return None
    return {
        "id": revision["id"],
        "overall_after": (revision.get("scores_after") or {}).get("overall"),
        "screenshot_desktop_path": revision.get("screenshot_desktop_path"),
    }


@router.get("/design-gallery/{item_id}")
async def get_design_gallery_item(
    item_id: str, auth: dict = Depends(require_platform_admin)
):
    """One gallery entry, whole: design_md, census, tokens and all."""
    log.info("admin_get_design_gallery_item", item_id=item_id)
    admin = get_supabase_admin()
    rows = (
        admin.table("design_gallery")
        .select("*, organizations(name)")
        .eq("id", item_id)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(
            status_code=404, detail="We couldn't find that gallery entry."
        )
    row = rows[0]
    org = row.pop("organizations", None) or {}

    revision = None
    if row.get("snapshot_id"):
        revision_rows = (
            admin.table("page_revisions")
            .select("id, snapshot_id, scores_after, screenshot_desktop_path, created_at")
            .eq("status", "complete")
            .eq("snapshot_id", row["snapshot_id"])
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        ).data or []
        revision = revision_rows[0] if revision_rows else None
    return {
        **row,
        "organization_name": org.get("name"),
        "revision": _revision_summary(revision),
    }


# ═══════════════════════════════════════════════════════════════════════════
#  The founder's console: who signed up, and what they hold.
#
#  Added 2026-08-30. Everything above is a read model over the design gallery;
#  everything below answers "how is the business doing", and one endpoint moves
#  credits.
#
#  **Same gate, deliberately.** `require_platform_admin` already spans tenants
#  and already refuses with a 404 rather than a 403, so a probe cannot confirm
#  the surface exists. A second admin mechanism — an email allow-list, a role
#  column — would be two things to keep in step and two ways to be wrong.
# ═══════════════════════════════════════════════════════════════════════════

#: One grant's ceiling. Not a policy about generosity — a guard against a typo.
#: 30,000 and 3,000,000 differ by two keystrokes, and only one of them is
#: recoverable by a conversation.
MAX_GRANT_CREDITS = 500_000


class GrantRequest(BaseModel):
    organization_id: str
    credits: int = Field(gt=0, le=MAX_GRANT_CREDITS)
    #: Required. A grant nobody can explain in three months is the state the
    #: `credit_grants` table exists to prevent.
    reason: str = Field(min_length=3, max_length=500)


def _all(admin, table: str, columns: str, limit: int = 2000) -> list[dict]:
    """Read a table, or log and return nothing.

    One unreadable table must not empty the whole console — somebody checking
    signups should still see them when an unrelated module is having a bad day.
    """
    try:
        return (admin.table(table).select(columns).limit(limit).execute().data) or []
    except Exception:
        log.warning("admin_read_failed", table=table, exc_info=True)
        return []


@router.get("/overview")
async def overview(auth: dict = Depends(require_platform_admin)):
    """The numbers a founder actually checks."""
    admin = get_supabase_admin()
    orgs = _all(admin, "organizations", "id, credits_balance")
    members = _all(admin, "organization_members", "user_id")
    topups = _all(admin, "credit_topups", "amount_cents, status")
    paid = [t for t in topups if t.get("status") == "paid"]

    return {
        "organizations": len(orgs),
        "people": len({m.get("user_id") for m in members if m.get("user_id")}),
        "credits_outstanding": sum(int(o.get("credits_balance") or 0) for o in orgs),
        "credits_comped": sum(
            int(g.get("credits") or 0) for g in _all(admin, "credit_grants", "credits")
        ),
        # Paid rows only. A pending checkout is not revenue.
        "revenue_cents": sum(int(t.get("amount_cents") or 0) for t in paid),
        "purchases": len(paid),
        # Signups beside work done — the pair that says whether growth is real.
        "website_checks": len(_all(admin, "website_snapshots", "id")),
        "runs": len(_all(admin, "simulations", "id")),
        "page_revisions": len(_all(admin, "page_revisions", "id")),
    }


@router.get("/people")
async def people(auth: dict = Depends(require_platform_admin)):
    """Every signup, newest first, with what they have done.

    Shaped for a mailer: the address, plus the fields that let somebody segment
    on it. A list of emails with no activity attached is a list nobody can use.
    Activity counts per organisation, because that is how the product bills and
    how the work is owned.
    """
    admin = get_supabase_admin()
    try:
        users = admin.auth.admin.list_users()
    except Exception:
        log.warning("admin_list_users_failed", exc_info=True)
        raise HTTPException(500, "We could not read the account list.") from None

    orgs = {
        str(o["id"]): o
        for o in _all(admin, "organizations", "id, name, plan, credits_balance")
    }
    org_of = {
        str(m["user_id"]): str(m["organization_id"])
        for m in _all(admin, "organization_members", "user_id, organization_id")
        if m.get("user_id")
    }

    activity: dict[str, dict[str, int]] = {}
    for table, key in (
        ("website_snapshots", "checks"),
        ("simulations", "runs"),
        ("page_revisions", "revisions"),
    ):
        for row in _all(admin, table, "organization_id"):
            org_id = str(row.get("organization_id"))
            activity.setdefault(org_id, {}).setdefault(key, 0)
            activity[org_id][key] += 1

    items = []
    for user in users:
        uid = str(getattr(user, "id", "") or "")
        org_id = org_of.get(uid)
        org = orgs.get(org_id or "", {})
        acts = activity.get(org_id or "", {})
        items.append({
            "user_id": uid,
            "email": getattr(user, "email", None),
            "signed_up_at": str(getattr(user, "created_at", "") or ""),
            "last_sign_in_at": str(getattr(user, "last_sign_in_at", "") or "") or None,
            "organization_id": org_id,
            "organization": org.get("name"),
            "plan": org.get("plan"),
            "credits_balance": org.get("credits_balance"),
            "checks": acts.get("checks", 0),
            "runs": acts.get("runs", 0),
            "revisions": acts.get("revisions", 0),
        })

    items.sort(key=lambda p: p["signed_up_at"], reverse=True)
    log.info("admin_people_listed", people=len(items))
    return {"items": items}


@router.post("/credits")
async def grant_credits(
    body: GrantRequest, auth: dict = Depends(require_platform_admin)
):
    """Add credits to one organisation, and record who did it and why.

    **Balance only, never the `grant_credits` RPC.** That RPC also sets
    `credits_granted = amount` and restarts `credit_cycle_start`, which rewrites
    the org's tier record and makes the UI read "33,250 of 30,000". This does
    what `apply_credit_topup` does for a real purchase: the balance moves and
    the grant record does not.

    **And never `credit_topups`.** That table is real revenue, and a comped
    grant written there overstates it.
    """
    admin = get_supabase_admin()
    rows = (
        admin.table("organizations")
        .select("id, name, credits_balance")
        .eq("id", body.organization_id)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(404, "We couldn't find that organisation.")

    org = rows[0]
    before = int(org.get("credits_balance") or 0)
    after = before + body.credits

    admin.table("organizations").update({"credits_balance": after}).eq(
        "id", body.organization_id
    ).execute()

    # Written after the balance moves, carrying the resulting figure. A grant's
    # meaning is what the account held immediately afterwards, and the balance
    # moves for other reasons — runs, top-ups, refunds — so deriving it later
    # would be arithmetic over a moving target.
    admin.table("credit_grants").insert({
        "organization_id": body.organization_id,
        "credits": body.credits,
        "reason": body.reason,
        "granted_by_email": (auth.get("user") or {}).get("email"),
        "balance_after": after,
    }).execute()

    log.info(
        "admin_credits_granted",
        organization_id=body.organization_id,
        credits=body.credits,
        balance_after=after,
    )
    return {
        "organization": org.get("name"),
        "credits_granted": body.credits,
        "balance_before": before,
        "balance_after": after,
    }


@router.get("/grants")
async def grants(auth: dict = Depends(require_platform_admin)):
    """Every comped grant, newest first.

    The answer to "why does this account have these credits" — which, before
    `credit_grants` existed, was a balance and a shrug.
    """
    admin = get_supabase_admin()
    rows = _all(
        admin,
        "credit_grants",
        "id, organization_id, credits, reason, granted_by_email, balance_after, created_at",
    )
    names = {
        str(o["id"]): o.get("name") for o in _all(admin, "organizations", "id, name")
    }
    for row in rows:
        row["organization"] = names.get(str(row.get("organization_id")))
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return {"items": rows}
