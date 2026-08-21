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

Two byproducts ride the same run. When the founder named a site they admire,
it is captured too and the critics judge against it — that capture failing
fails the run, because it is part of what was ordered. And every completed
check distils the page's design into `design_gallery` — that failing never
fails the run, because the critique is the deliverable and the gallery is the
platform's own byproduct.
"""
from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from typing import Any

import structlog
from fastapi import UploadFile

from app.core.database import get_supabase_admin
from app.services.billing.agent_pricing import refund_credits

logger = structlog.get_logger()

# How much of the page's extracted text the stored document carries. Enough for
# any landing page; a cap because the DOM text of an app-shell page can run to
# megabytes, and the document exists to be read downstream, not archived.
PAGE_EXCERPT_CHARS = 15_000

# What the founder sees when the failure is ours rather than the page's.
GENERIC_FAILURE_MESSAGE = (
    "Something went wrong while checking this page. Try again in a few minutes."
)

# A founder may name a site they admire; the critics judge against it. If that
# site can't be captured, the run fails with this in front of the capture
# service's own founder-readable sentence — the founder must learn *which* of
# the two addresses defeated the check.
REFERENCE_FAILURE_PREFIX = "We couldn't read the site you admire — "

# The bucket `services/website/store` uploads to. Mirrored rather than
# imported: this module must import without the website services present (the
# lazy-import discipline in `run_website_check`), and a top-level import for
# one constant would break that.
SCREENSHOT_BUCKET = "project-media"


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
            # Nothing was spent. The page never loaded, so no critic ran and
            # no model was called — and the founder was being told to try
            # again at the same price for work we had not done. Observed in
            # production on a site that was merely slow to wake.
            #
            # Refunded only on THIS path. A check that dies later has consumed
            # real compute, and a rule that quietly sometimes pays is worse
            # than one that says plainly when it does.
            refund_credits(
                organization_id,
                int(snapshot.get("credits_charged") or 0),
                reason="website_capture_failed_before_any_model_call",
            )
            return

        # The admired site, when the founder named one. Captured before any
        # storage write: a check that will fail on its reference should fail
        # before it has half-landed. Its failure fails the run — the founder
        # asked to be judged against this site, and a verdict that silently
        # dropped the comparison would not be the check they paid for.
        reference_capture = None
        if snapshot.get("reference_url"):
            try:
                reference_capture = await capture_website(snapshot["reference_url"])
            except WebsiteCaptureError as exc:
                _record_failure(snapshot_id, REFERENCE_FAILURE_PREFIX + str(exc))
                return
            # Bot walls return a tiny challenge page with a 200: the fetch
            # "succeeds" and the critics would measure a CAPTCHA instead of the
            # admired design. Found live when linear.app returned an 18KB
            # not-Linear. A near-empty reference is a failed reference.
            if len(reference_capture.dom_text or "") < 400:
                _record_failure(
                    snapshot_id,
                    REFERENCE_FAILURE_PREFIX
                    + "that site blocked automated readers, so there was "
                    "nothing real to measure against. Try another site you "
                    "admire.",
                )
                return

        paths = await upload_screenshots(
            organization_id=organization_id,
            snapshot_id=snapshot_id,
            capture=capture,
        )
        reference_screenshot_path = None
        if reference_capture is not None:
            reference_screenshot_path = await _upload_reference_screenshot(
                organization_id=organization_id,
                snapshot_id=snapshot_id,
                capture=reference_capture,
            )

        capture_update = {
            "final_url": capture.final_url,
            "title": capture.title,
            "dom_chars": len(capture.dom_text or ""),
            "screenshot_desktop_path": paths["desktop"],
            "screenshot_mobile_path": paths["mobile"],
            "status": "judging",
        }
        if reference_screenshot_path:
            capture_update["reference_screenshot_path"] = reference_screenshot_path
        admin.table("website_snapshots").update(capture_update).eq(
            "id", snapshot_id
        ).execute()

        try:
            critique = await run_critic_gauntlet(
                capture,
                reference=reference_capture,
                organization_id=organization_id,
            )
        except CriticError as exc:
            _record_failure(snapshot_id, str(exc))
            return

        await _store_design_gallery_row(
            snapshot,
            organization_id=organization_id,
            capture=capture,
            overall_score=critique.model_dump().get("overall_score"),
            paths=paths,
        )

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


async def _upload_reference_screenshot(
    *, organization_id: str, snapshot_id: str, capture: Any
) -> str:
    """Store the admired site's desktop PNG beside the snapshot's own pair.

    `upload_screenshots` (services/website/store) owns the founder's page at
    both viewports; the reference contributes one desktop frame, under the same
    org-scoped prefix, named so nothing that globs the snapshot's own
    screenshots ever confuses the two.
    """
    path = f"website/{organization_id}/{snapshot_id}/reference-desktop.png"
    bucket = get_supabase_admin().storage.from_(SCREENSHOT_BUCKET)
    bucket.upload(path, capture.screenshot_desktop, {"content-type": "image/png"})
    logger.info(
        "website_reference_screenshot_stored",
        organization_id=organization_id,
        snapshot_id=snapshot_id,
        desktop_bytes=len(capture.screenshot_desktop),
    )
    return path


async def _store_design_gallery_row(
    snapshot: dict[str, Any],
    *,
    organization_id: str,
    capture: Any,
    overall_score: int | None,
    paths: dict[str, str],
) -> None:
    """Distil the page's design into the gallery; never fail the check for it.

    The critique is the paid deliverable; the gallery row is the byproduct
    that accumulates into the before/after showcase (PRD_V3 §4 — flagged, not
    built). So every failure here — the DNA extraction, the insert itself —
    is logged whole and swallowed: a founder's check must not fail because
    the platform's byproduct did.
    """
    try:
        from app.services.website.design_dna import extract_design_dna

        dna = await extract_design_dna(capture, organization_id=organization_id)
        get_supabase_admin().table("design_gallery").insert({
            "organization_id": organization_id,
            "project_id": snapshot.get("project_id"),
            "snapshot_id": snapshot["id"],
            "url": capture.final_url or snapshot["url"],
            "characterization": dna.characterization,
            "summary": dna.summary,
            "style_tags": dna.style_tags,
            "maturity_level": dna.maturity_level,
            "maturity_rationale": dna.maturity_rationale,
            "tokens": dna.tokens.model_dump(),
            "census": getattr(capture, "style_census", None) or {},
            "design_md": dna.design_md,
            "overall_score": overall_score,
            "screenshot_desktop_path": paths["desktop"],
            "screenshot_mobile_path": paths["mobile"],
            "reference_url": snapshot.get("reference_url"),
            "created_at": datetime.now(UTC).isoformat(),
        }).execute()
        logger.info(
            "design_gallery_row_stored",
            snapshot_id=snapshot["id"],
            organization_id=organization_id,
            maturity_level=dna.maturity_level,
        )
    except Exception:
        logger.exception(
            "design_gallery_store_failed",
            snapshot_id=snapshot["id"],
            organization_id=organization_id,
        )


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
