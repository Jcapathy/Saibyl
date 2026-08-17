"""Website checks (PRD_V3 §4a–c): what a stranger sees when they land there.

A founder submits their live page's URL. The pipeline captures the rendered
page, a panel of critics judges it, and the page's own text is stored as a
document so the audience reacts to the page itself. The check is created here,
charged here, and executed by `workers.website_tasks`; the capture and the
critics live in `services/website`, not in this module.

Route order is load-bearing: the static list path is registered before
`/check/{snapshot_id}`, because a static path shadowed by a parameterised one
has shipped twice in this codebase.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import urlsplit

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.core.auth import get_current_org
from app.core.database import get_supabase_admin
from app.core.tasks import spawn
from app.services.billing.agent_pricing import (
    deduct_credits,
    get_credit_balance,
    website_check_credits,
)
from app.workers.website_tasks import run_website_check

log = structlog.get_logger()

router = APIRouter(tags=["website"])

LIST_LIMIT = 20

# Shape guard only. The deep validation — private addresses, redirects to
# them, schemes in disguise — lives in the capture service, which is the one
# place that actually opens the connection.
MAX_URL_LENGTH = 2048


def _mark_website_check_failed(
    snapshot_id: str, name: str
) -> Callable[[Exception], None]:
    """`on_failure` for `spawn`: a check whose worker died must say so.

    Without this the row stays `queued`/`capturing` forever and the founder
    watches a spinner for a failure that was logged and never surfaced.
    """
    def _mark(exc: Exception) -> None:
        get_supabase_admin().table("website_snapshots").update({
            "status": "failed",
            "error_message": f"[{name}] {type(exc).__name__}: {exc}",
        }).eq("id", snapshot_id).execute()
    return _mark


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class CreateWebsiteCheckBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: str
    url: str = Field(min_length=1, max_length=MAX_URL_LENGTH)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/check")
async def create_website_check(
    body: CreateWebsiteCheckBody, auth: dict = Depends(get_current_org)
):
    """Create a website check, charge it, and hand it to the worker."""
    log.info(
        "create_website_check",
        org_id=auth["org_id"],
        url=body.url[:120],
    )

    admin = get_supabase_admin()

    owned = (
        admin.table("projects")
        .select("id")
        .eq("id", body.project_id)
        .eq("organization_id", auth["org_id"])
        .execute()
    )
    if not owned.data:
        raise HTTPException(status_code=404, detail="We couldn't find that workspace.")

    try:
        parts = urlsplit(body.url)
        url_ok = parts.scheme in ("http", "https") and bool(parts.netloc)
    except ValueError:
        url_ok = False
    if not url_ok:
        raise HTTPException(
            status_code=400,
            detail=(
                "That doesn't look like a web address. It needs to start "
                "with http:// or https://."
            ),
        )

    credits = website_check_credits()
    balance, _granted, _plan = get_credit_balance(auth["org_id"])
    if balance < credits:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Not enough credits. This check needs {credits:,}; "
                f"you have {balance:,}."
            ),
        )
    # Charged at create, not at completion — the same rule as every run:
    # deducting later would let one check's worth of credits start ten.
    deduct_credits(auth["org_id"], credits)

    row = (
        admin.table("website_snapshots")
        .insert({
            "organization_id": auth["org_id"],
            "project_id": body.project_id,
            "url": body.url,
            "status": "queued",
            "credits_charged": credits,
            "created_at": datetime.now(UTC).isoformat(),
        })
        .execute()
    ).data[0]

    spawn(
        run_website_check(row["id"], auth["org_id"]), "website_check",
        on_failure=_mark_website_check_failed(row["id"], "website_check"),
    )
    row.pop("critique", None)
    return row


@router.get("/check")
async def list_website_checks(
    project_id: str | None = Query(None),
    auth: dict = Depends(get_current_org),
):
    """The org's checks, newest first, without the critique bodies.

    The critique is fetched only to lift the overall score out of it; it is
    dropped before the response, because a list of 20 checks each carrying a
    full critique is a detail view pretending to be an index.
    """
    admin = get_supabase_admin()
    query = (
        admin.table("website_snapshots")
        .select(
            "id, project_id, url, final_url, title, status, credits_charged, "
            "dom_chars, document_id, error_message, created_at, completed_at, "
            "critique",
            count="exact",
        )
        .eq("organization_id", auth["org_id"])
    )
    if project_id:
        query = query.eq("project_id", project_id)
    result = query.order("created_at", desc=True).limit(LIST_LIMIT).execute()

    items = []
    for row in result.data or []:
        critique = row.pop("critique", None) or {}
        items.append({**row, "overall_score": critique.get("overall_score")})
    return {"items": items, "total": result.count, "limit": LIST_LIMIT}


@router.get("/check/{snapshot_id}")
async def get_website_check(snapshot_id: str, auth: dict = Depends(get_current_org)):
    """One check, with its full critique once complete."""
    admin = get_supabase_admin()
    rows = (
        admin.table("website_snapshots")
        .select("*")
        .eq("id", snapshot_id)
        .eq("organization_id", auth["org_id"])
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status_code=404, detail="We couldn't find that check.")
    return rows[0]
