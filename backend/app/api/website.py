"""Website checks and page revisions (PRD_V3 §4a–d).

A founder submits their live page's URL. The pipeline captures the rendered
page, a panel of critics judges it, and the page's own text is stored as a
document so the audience reacts to the page itself. Once a check completes,
the founder can order the fixed version: a revision regenerates the page
through revise-and-re-judge rounds and lands the new HTML, its screenshots,
and the before/after scores. Checks and revisions are created here, charged
here, and executed by `workers.website_tasks` / `workers.revision_tasks`; the
capture, the critics, and the revision loop live in `services/website`, not
in this module.

Route order is load-bearing: each static list path is registered before its
parameterised sibling (`/check` before `/check/{snapshot_id}`, `/revision`
before `/revision/{revision_id}`), because a static path shadowed by a
parameterised one has shipped twice in this codebase.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import urlsplit

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from app.core.auth import get_current_org
from app.core.database import get_supabase_admin
from app.core.tasks import spawn
from app.services.billing.agent_pricing import (
    deduct_credits,
    get_credit_balance,
    website_check_credits,
    website_revision_credits,
)
from app.workers.revision_tasks import run_page_revision
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


def _mark_page_revision_failed(
    revision_id: str, name: str
) -> Callable[[Exception], None]:
    """`on_failure` for `spawn`: the same never-a-spinner rule for revisions."""
    def _mark(exc: Exception) -> None:
        get_supabase_admin().table("page_revisions").update({
            "status": "failed",
            "error_message": f"[{name}] {type(exc).__name__}: {exc}",
        }).eq("id", revision_id).execute()
    return _mark


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class CreateWebsiteCheckBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: str
    url: str = Field(min_length=1, max_length=MAX_URL_LENGTH)
    # A site the founder admires; the critics judge their page against it.
    reference_url: str | None = Field(None, max_length=MAX_URL_LENGTH)


class CreatePageRevisionBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    snapshot_id: str


def _looks_like_web_address(url: str) -> bool:
    """The same shape guard for both addresses; depth stays in the capture."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(parts.netloc)


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

    if not _looks_like_web_address(body.url):
        raise HTTPException(
            status_code=400,
            detail=(
                "That doesn't look like a web address. It needs to start "
                "with http:// or https://."
            ),
        )
    if body.reference_url and not _looks_like_web_address(body.reference_url):
        raise HTTPException(
            status_code=400,
            detail=(
                "The address of the site you admire doesn't look like a web "
                "address. It needs to start with http:// or https://."
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
            "reference_url": body.reference_url,
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
            "id, project_id, url, reference_url, final_url, title, status, "
            "credits_charged, dom_chars, document_id, error_message, "
            "created_at, completed_at, critique",
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

    # Each check's design-gallery row, when the worker managed to leave one —
    # one batched query, not one per item. `design_gallery_id` is None until
    # then; the gallery is a byproduct, so its absence is not an error state.
    gallery_by_snapshot: dict[str, str] = {}
    if items:
        gallery_rows = (
            admin.table("design_gallery")
            .select("id, snapshot_id")
            .eq("organization_id", auth["org_id"])
            .in_("snapshot_id", [item["id"] for item in items])
            .execute()
        ).data or []
        gallery_by_snapshot = {g["snapshot_id"]: g["id"] for g in gallery_rows}
    for item in items:
        item["design_gallery_id"] = gallery_by_snapshot.get(item["id"])

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
    row = rows[0]

    gallery = (
        admin.table("design_gallery")
        .select("id")
        .eq("snapshot_id", snapshot_id)
        .eq("organization_id", auth["org_id"])
        .limit(1)
        .execute()
    ).data or []
    row["design_gallery_id"] = gallery[0]["id"] if gallery else None
    return row


# ---------------------------------------------------------------------------
# Page revisions (PRD_V3 §4d)
# ---------------------------------------------------------------------------

# Which stored image each `which` value names, per surface. One table per
# route so the validation sentence can list exactly the choices that exist
# there — the after-images live on the revision, the before-images (and the
# admired site's frame) on the check it fixed.
_REVISION_IMAGES = {
    "after_desktop": "screenshot_desktop_path",
    "after_mobile": "screenshot_mobile_path",
}
_CHECK_IMAGES = {
    "desktop": "screenshot_desktop_path",
    "mobile": "screenshot_mobile_path",
    "reference": "reference_screenshot_path",
}


@router.post("/revision")
async def create_page_revision(
    body: CreatePageRevisionBody, auth: dict = Depends(get_current_org)
):
    """Create a page revision, charge it, and hand it to the worker."""
    log.info(
        "create_page_revision",
        org_id=auth["org_id"],
        snapshot_id=body.snapshot_id,
    )

    admin = get_supabase_admin()

    owned = (
        admin.table("website_snapshots")
        .select("id, project_id, status")
        .eq("id", body.snapshot_id)
        .eq("organization_id", auth["org_id"])
        .limit(1)
        .execute()
    ).data or []
    if not owned:
        raise HTTPException(status_code=404, detail="We couldn't find that check.")
    snapshot = owned[0]
    if snapshot.get("status") != "complete":
        raise HTTPException(
            status_code=409,
            detail=(
                "That check hasn't finished yet. A page can only be revised "
                "once its critique is complete."
            ),
        )

    credits = website_revision_credits()
    balance, _granted, _plan = get_credit_balance(auth["org_id"])
    if balance < credits:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Not enough credits. This revision needs {credits:,}; "
                f"you have {balance:,}."
            ),
        )
    # Charged at create, not at completion — the same rule as every run:
    # deducting later would let one revision's worth of credits start ten.
    deduct_credits(auth["org_id"], credits)

    row = (
        admin.table("page_revisions")
        .insert({
            "organization_id": auth["org_id"],
            "project_id": snapshot.get("project_id"),
            "snapshot_id": body.snapshot_id,
            "status": "queued",
            "credits_charged": credits,
            "created_at": datetime.now(UTC).isoformat(),
        })
        .execute()
    ).data[0]

    spawn(
        run_page_revision(row["id"], auth["org_id"]), "page_revision",
        on_failure=_mark_page_revision_failed(row["id"], "page_revision"),
    )
    for heavy in ("scores_before", "scores_after", "critique_after", "fix_prompts"):
        row.pop(heavy, None)
    return row


@router.get("/revision")
async def list_page_revisions(
    snapshot_id: str | None = Query(None),
    auth: dict = Depends(get_current_org),
):
    """The org's revisions, newest first, without the bodies.

    The score objects are fetched only to lift the two overall numbers out of
    them; they are dropped before the response, for the same reason the check
    list drops critiques — a list carrying full verdicts is a detail view
    pretending to be an index.
    """
    admin = get_supabase_admin()
    query = (
        admin.table("page_revisions")
        .select(
            "id, project_id, snapshot_id, status, rounds, best_round, "
            "credits_charged, error_message, created_at, completed_at, "
            "scores_before, scores_after",
            count="exact",
        )
        .eq("organization_id", auth["org_id"])
    )
    if snapshot_id:
        query = query.eq("snapshot_id", snapshot_id)
    result = query.order("created_at", desc=True).limit(LIST_LIMIT).execute()

    items = []
    for row in result.data or []:
        before = row.pop("scores_before", None) or {}
        after = row.pop("scores_after", None) or {}
        items.append({
            **row,
            "overall_before": before.get("overall"),
            "overall_after": after.get("overall"),
        })
    return {"items": items, "total": result.count, "limit": LIST_LIMIT}


@router.get("/revision/{revision_id}")
async def get_page_revision(revision_id: str, auth: dict = Depends(get_current_org)):
    """One revision, whole — critique_after and fix_prompts once complete."""
    row = _org_owned_row(
        "page_revisions", revision_id, auth["org_id"],
        missing="We couldn't find that revision.",
    )
    return row


@router.get("/revision/{revision_id}/html")
async def get_page_revision_html(
    revision_id: str, auth: dict = Depends(get_current_org)
):
    """The revised page itself, served as HTML for download or copy."""
    row = _org_owned_row(
        "page_revisions", revision_id, auth["org_id"],
        missing="We couldn't find that revision.",
    )
    if row.get("status") != "complete" or not row.get("html_path"):
        raise HTTPException(
            status_code=409,
            detail="This revision isn't finished yet — the new page isn't ready.",
        )
    return Response(
        content=await _read_stored(row["html_path"]), media_type="text/html"
    )


@router.get("/revision/{revision_id}/screenshot")
async def get_page_revision_screenshot(
    revision_id: str,
    which: str = Query(...),
    auth: dict = Depends(get_current_org),
):
    """One of the revision's rendered after-images, as a PNG."""
    return await _stream_stored_image(
        table="page_revisions",
        row_id=revision_id,
        org_id=auth["org_id"],
        images=_REVISION_IMAGES,
        which=which,
        missing="We couldn't find that revision.",
    )


@router.get("/check/{snapshot_id}/screenshot")
async def get_website_check_screenshot(
    snapshot_id: str,
    which: str = Query(...),
    auth: dict = Depends(get_current_org),
):
    """One of the check's stored images — the before side of any comparison."""
    return await _stream_stored_image(
        table="website_snapshots",
        row_id=snapshot_id,
        org_id=auth["org_id"],
        images=_CHECK_IMAGES,
        which=which,
        missing="We couldn't find that check.",
    )


def _org_owned_row(
    table: str, row_id: str, org_id: str, *, missing: str
) -> dict:
    """Fetch one row the org owns, or refuse with the caller's sentence."""
    rows = (
        get_supabase_admin()
        .table(table)
        .select("*")
        .eq("id", row_id)
        .eq("organization_id", org_id)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status_code=404, detail=missing)
    return rows[0]


async def _stream_stored_image(
    *,
    table: str,
    row_id: str,
    org_id: str,
    images: dict[str, str],
    which: str,
    missing: str,
) -> Response:
    """The shared passthrough: validate `which`, find the path, stream the PNG.

    One helper for both surfaces because the UI renders before and after side
    by side, and two passthroughs that drift apart would serve the two halves
    of one comparison differently.
    """
    if which not in images:
        choices = ", ".join(images)
        raise HTTPException(
            status_code=400,
            detail=f"Say which image you want — one of: {choices}.",
        )
    row = _org_owned_row(table, row_id, org_id, missing=missing)
    path = row.get(images[which])
    if not path:
        raise HTTPException(
            status_code=404, detail="That image hasn't been stored yet."
        )
    return Response(content=await _read_stored(path), media_type="image/png")


async def _read_stored(path: str) -> bytes:
    """Read stored bytes through the website store.

    Imported here rather than at module top so this router loads even when
    the website services are absent — the same lazy-import discipline the
    workers follow.
    """
    from app.services.website.store import read_stored

    return await read_stored(path)
