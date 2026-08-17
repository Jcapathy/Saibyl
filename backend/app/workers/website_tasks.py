"""Background execution of one website check (PRD_V3 §4a–c).

One task because the steps are strictly ordered and share a failure story:
capture the rendered page, store its screenshots, run the critic panel, store
the page's text as a document, persist all of it. A failure anywhere marks the
snapshot `failed` with a sentence a founder can read — never a row stuck on
`capturing` while they watch a spinner for an error that only reached the logs.

The capture and critic services write their error messages for the founder
("the page took longer than 45 seconds to answer"), so those pass through to
the row verbatim. Anything else lands as one generic sentence, with the detail
in the logs — a stack trace on the row is not a failure story, it is a leak.
"""
from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from typing import Any

import structlog
from fastapi import UploadFile

from app.core.database import get_supabase_admin

logger = structlog.get_logger()

# How much of the page's extracted text the stored document carries. Enough for
# any landing page; a cap because the DOM text of an app-shell page can run to
# megabytes, and the document exists to be read downstream, not archived.
PAGE_EXCERPT_CHARS = 15_000

# What the founder sees when the failure is ours rather than the page's.
GENERIC_FAILURE_MESSAGE = (
    "Something went wrong while checking this page. Try again in a few minutes."
)


async def run_website_check(snapshot_id: str, organization_id: str) -> None:
    """Execute a queued website check end to end and persist what it found."""
    admin = get_supabase_admin()
    try:
        rows = (
            admin.table("website_snapshots")
            .select("*")
            .eq("id", snapshot_id)
            .eq("organization_id", organization_id)
            .execute()
        ).data or []
        if not rows:
            raise RuntimeError(
                f"website check {snapshot_id} not found for this organization"
            )
        snapshot = rows[0]

        admin.table("website_snapshots").update({"status": "capturing"}).eq(
            "id", snapshot_id
        ).execute()

        # Imported here rather than at module top so this module — and the API
        # router that imports it at startup — loads even when the website
        # services are absent, exactly as the clearance worker does for its
        # services.
        from app.services.website.capture import WebsiteCaptureError, capture_website
        from app.services.website.critics import CriticError, run_critic_gauntlet
        from app.services.website.store import upload_screenshots

        try:
            capture = await capture_website(snapshot["url"])
        except WebsiteCaptureError as exc:
            # The capture service's messages are founder-readable by contract,
            # so the row carries them whole.
            _record_failure(snapshot_id, str(exc))
            return

        paths = await upload_screenshots(
            organization_id=organization_id,
            snapshot_id=snapshot_id,
            capture=capture,
        )

        admin.table("website_snapshots").update({
            "final_url": capture.final_url,
            "title": capture.title,
            "dom_chars": len(capture.dom_text or ""),
            "screenshot_desktop_path": paths["desktop"],
            "screenshot_mobile_path": paths["mobile"],
            "status": "judging",
        }).eq("id", snapshot_id).execute()

        try:
            critique = await run_critic_gauntlet(
                capture, organization_id=organization_id
            )
        except CriticError as exc:
            _record_failure(snapshot_id, str(exc))
            return

        document_id = await _store_page_document(
            snapshot, organization_id=organization_id, capture=capture
        )

        admin.table("website_snapshots").update({
            "critique": critique.model_dump(),
            "document_id": document_id,
            "status": "complete",
            "completed_at": datetime.now(UTC).isoformat(),
        }).eq("id", snapshot_id).execute()

        logger.info(
            "website_check_complete",
            snapshot_id=snapshot_id,
            organization_id=organization_id,
            document_id=document_id,
        )
    except Exception:
        logger.exception("website_check_failed", snapshot_id=snapshot_id)
        _record_failure(snapshot_id, GENERIC_FAILURE_MESSAGE)


async def _store_page_document(
    snapshot: dict[str, Any], *, organization_id: str, capture: Any
) -> str:
    """Store the captured page as a small markdown document; return its id.

    Through `documents.store_upload` — the same path every real file takes — so
    extraction, the subject brief and audience synthesis all consume the page
    without a second intake path. The idea brief set this pattern (PRD_V3 §3);
    the kind here is 'website_url', which records that the text was fetched
    from the founder's live page rather than uploaded.
    """
    from app.api.documents import store_upload

    content = _compose_page_markdown(capture).encode("utf-8")
    upload = UploadFile(file=BytesIO(content), size=len(content), filename="website.md")
    doc = await store_upload(
        project_id=snapshot["project_id"],
        org_id=organization_id,
        file=upload,
        material_kind="website_url",
        source_url=capture.final_url or capture.url,
    )
    return doc["id"]


def _compose_page_markdown(capture: Any) -> str:
    """The captured page as one small markdown document.

    Title, where it was fetched from, the meta description when the page has
    one, and the extracted text up to `PAGE_EXCERPT_CHARS`. Deliberately small:
    this is the page as a reader would take it in, not an archive of the DOM.
    """
    title = (capture.title or "").strip() or capture.url
    meta = capture.meta or {}
    description = str(meta.get("description") or meta.get("og:description") or "").strip()
    excerpt = (capture.dom_text or "")[:PAGE_EXCERPT_CHARS]

    parts = [f"# {title}", "", f"Source: {capture.final_url or capture.url}"]
    if description:
        parts += ["", description]
    parts += ["", excerpt]
    return "\n".join(parts) + "\n"


def _record_failure(snapshot_id: str, message: str) -> None:
    """Leave the row saying the check failed and why.

    Without this the frontend cannot distinguish "still checking" from
    "failed", and would poll forever on a check that will never finish.
    """
    try:
        get_supabase_admin().table("website_snapshots").update({
            "status": "failed",
            "error_message": message,
        }).eq("id", snapshot_id).execute()
    except Exception:
        logger.exception("website_check_failure_record_failed", snapshot_id=snapshot_id)
