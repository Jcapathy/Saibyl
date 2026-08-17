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
