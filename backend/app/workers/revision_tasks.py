"""Background execution of one page revision (PRD_V3 §4d).

One task because the steps are strictly ordered and share a failure story:
re-capture the page the check judged, hand it with its critique to the
revision loop (which revises, re-judges, and repeats internally), store the
winning round's page and screenshots, persist all of it. A failure anywhere
marks the revision `failed` with a sentence a founder can read — never a row
stuck on `generating` while they watch a spinner for an error that only
reached the logs.

The capture and revision services write their error messages for the founder,
so those pass through to the row verbatim. Anything else lands as one generic
sentence, with the detail in the logs — a stack trace on the row is not a
failure story, it is a leak.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from app.core.database import get_supabase_admin

logger = structlog.get_logger()

# What the founder sees when the failure is ours rather than the page's.
GENERIC_FAILURE_MESSAGE = (
    "Something went wrong while revising this page. Try again in a few minutes."
)

# The revision builds on a finished check; a queued, running, or failed one
# has no critique to revise against, and saying so beats a mystery failure.
UNFINISHED_CHECK_MESSAGE = (
    "The check this revision builds on hasn't finished, so there was "
    "nothing to revise. Wait for the check to complete, then try again."
)

# The admired-site failure wording, byte-for-byte what `website_tasks` uses:
# the founder must learn *which* of the two addresses defeated the revision,
# and the same failure must read the same in both places.
REFERENCE_FAILURE_PREFIX = "We couldn't read the site you admire — "
BLOCKED_REFERENCE_MESSAGE = (
    "that site blocked automated readers, so there was "
    "nothing real to measure against. Try another site you "
    "admire."
)

# The bot-wall floor from `website_tasks`, mirrored value-for-value: a capture
# whose extracted text is this short is a CAPTCHA page wearing a 200, not the
# admired design (found live when linear.app returned an 18KB not-Linear).
MIN_REFERENCE_DOM_CHARS = 400


async def run_page_revision(revision_id: str, organization_id: str) -> None:
    """Execute a queued page revision end to end and persist what it produced."""
    admin = get_supabase_admin()
    try:
        rows = (
            admin.table("page_revisions")
            .select("*")
            .eq("id", revision_id)
            .eq("organization_id", organization_id)
            .execute()
        ).data or []
        if not rows:
            raise RuntimeError(
                f"page revision {revision_id} not found for this organization"
            )
        revision = rows[0]

        snapshot_rows = (
            admin.table("website_snapshots")
            .select("*")
            .eq("id", revision["snapshot_id"])
            .eq("organization_id", organization_id)
            .execute()
        ).data or []
        snapshot = snapshot_rows[0] if snapshot_rows else None
        # The API refuses to create a revision of an unfinished check, but the
        # worker re-checks: the check could have been a different status when
        # this row was queued, and a loop fed no critique revises against air.
        if (
            snapshot is None
            or snapshot.get("status") != "complete"
            or not snapshot.get("critique")
        ):
            _record_failure(revision_id, UNFINISHED_CHECK_MESSAGE)
            return

        admin.table("page_revisions").update({"status": "generating"}).eq(
            "id", revision_id
        ).execute()

        # Imported here rather than at module top so this module — and the API
        # router that imports it at startup — loads even when the website
        # services are absent, exactly as the website worker does for its
        # services.
        from app.services.website.capture import WebsiteCaptureError, capture_website
        from app.services.website.revise import RevisionError, generate_revision
        from app.services.website.store import upload_revision

        # Rebuild the original capture by re-fetching the page. The check kept
        # the page's screenshots in storage but not the capture object the
        # revision loop needs (DOM, computed styles, screenshot bytes in
        # memory), and a re-fetch is the honest current "before": revising a
        # week-old rendering of a page that has since changed would prescribe
        # fixes for problems the founder may already have fixed. Its failure
        # is the capture service's own founder-readable sentence.
        try:
            capture = await capture_website(snapshot["url"])
        except WebsiteCaptureError as exc:
            _record_failure(revision_id, str(exc))
            return

        # The check's design DNA, when its gallery row landed — the revision
        # loop keeps the page recognisably the founder's rather than restyling
        # it. The gallery is a byproduct that may be absent, so None is a
        # working input here, not an error.
        dna = _load_design_dna(snapshot, organization_id=organization_id)

        # The admired site, when the founder named one on the check: the
        # revision is judged by the same panel against the same reference, or
        # the after-score would not be comparable to the before-score.
        reference = None
        if snapshot.get("reference_url"):
            try:
                reference = await capture_website(snapshot["reference_url"])
            except WebsiteCaptureError as exc:
                _record_failure(revision_id, REFERENCE_FAILURE_PREFIX + str(exc))
                return
            if len(reference.dom_text or "") < MIN_REFERENCE_DOM_CHARS:
                _record_failure(
                    revision_id,
                    REFERENCE_FAILURE_PREFIX + BLOCKED_REFERENCE_MESSAGE,
                )
                return

        critique = snapshot["critique"]
        # The loop revises, re-judges, and repeats internally, so the row
        # stays `generating` throughout — 'judging' exists in the status
        # vocabulary for a future loop that reports its phases, but a status
        # the worker flips mid-call would be theatre, not state.
        try:
            result = await generate_revision(
                capture,
                critique,
                dna,
                reference=reference,
                organization_id=organization_id,
            )
        except RevisionError as exc:
            # The revision service's messages are founder-readable by
            # contract, so the row carries them whole.
            _record_failure(revision_id, str(exc))
            return

        paths = await upload_revision(
            organization_id=organization_id,
            revision_id=revision_id,
            html=result.html,
            capture=result.capture_after,
        )

        admin.table("page_revisions").update({
            "status": "complete",
            "rounds": len(result.rounds),
            "best_round": result.best_round,
            # The before comes from the check the founder already read, not
            # from the loop's own re-judge of the original: the delta must be
            # measured against the number the revision was ordered to beat.
            "scores_before": _scores_from_critique(critique),
            # Same lifter both sides: the generator's own scores_after is flat
            # ({overall, <dim>: n}) while the before nests dimensions — the
            # first live gate printed every after-dimension as None because of
            # the asymmetry. critique_after is a full critique, so lift it the
            # identical way.
            "scores_after": _scores_from_critique(result.critique_after or {}),
            "critique_after": result.critique_after,
            "fix_prompts": result.fix_prompts,
            "html_path": paths["html"],
            "screenshot_desktop_path": paths["desktop"],
            "screenshot_mobile_path": paths["mobile"],
            "completed_at": datetime.now(UTC).isoformat(),
        }).eq("id", revision_id).execute()

        logger.info(
            "page_revision_complete",
            revision_id=revision_id,
            organization_id=organization_id,
            rounds=len(result.rounds),
            best_round=result.best_round,
        )
    except Exception:
        logger.exception("page_revision_failed", revision_id=revision_id)
        _record_failure(revision_id, GENERIC_FAILURE_MESSAGE)


def _load_design_dna(
    snapshot: dict[str, Any], *, organization_id: str
) -> dict[str, Any] | None:
    """The check's design-gallery row, or None when the byproduct never landed."""
    rows = (
        get_supabase_admin()
        .table("design_gallery")
        .select("*")
        .eq("snapshot_id", snapshot["id"])
        .eq("organization_id", organization_id)
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def _scores_from_critique(critique: dict[str, Any]) -> dict[str, Any]:
    """The stored critique's numbers, lifted into the before/after shape.

    Overall plus per-dimension, keyed the way the critique keys them, so the
    before and after columns of the presentation line up dimension for
    dimension without either side renaming anything.
    """
    return {
        "overall": critique.get("overall_score"),
        "dimensions": {
            str(dim.get("key")): dim.get("score")
            for dim in critique.get("dimensions") or []
            if dim.get("key")
        },
    }


def _record_failure(revision_id: str, message: str) -> None:
    """Leave the row saying the revision failed and why.

    Without this the frontend cannot distinguish "still generating" from
    "failed", and would poll forever on a revision that will never finish.
    """
    try:
        get_supabase_admin().table("page_revisions").update({
            "status": "failed",
            "error_message": message,
        }).eq("id", revision_id).execute()
    except Exception:
        logger.exception(
            "page_revision_failure_record_failed", revision_id=revision_id
        )
