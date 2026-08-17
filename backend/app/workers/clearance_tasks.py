"""Background execution of one USPTO clearance run (PRD_V3 §11).

One task because the steps are strictly ordered and share a failure story:
plan the queries, run the tracks against the USPTO, build the artifact,
compose the report, persist all of it. A failure anywhere marks the run
`failed` with why — never a row stuck on `running` while the founder watches
a spinner for an error that only reached the logs.

Keys never appear in an error message: the USPTO client masks them before any
exception it raises can carry one, so `error_message` stores the exception
text unredacted.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from app.core.database import get_supabase_admin

logger = structlog.get_logger()

_RISK_TIERS = {"GREEN", "YELLOW", "RED"}


async def run_clearance(run_id: str, organization_id: str) -> None:
    """Execute a queued clearance run end to end and persist what it found."""
    admin = get_supabase_admin()
    try:
        rows = (
            admin.table("clearance_runs")
            .select("*")
            .eq("id", run_id)
            .eq("organization_id", organization_id)
            .execute()
        ).data or []
        if not rows:
            raise RuntimeError(f"clearance run {run_id} not found for this organization")
        run = rows[0]

        admin.table("clearance_runs").update({"status": "running"}).eq(
            "id", run_id
        ).execute()

        # Imported here rather than at module top so this module — and the API
        # router that imports it at startup — loads even when the clearance
        # services are absent, exactly as the API's 503 guard assumes.
        from app.services.clearance.artifact import (
            build_artifact,
            compose_report_markdown,
        )
        from app.services.clearance.query_plan import build_query_plan
        from app.services.clearance.tracks import run_clearance_tracks
        from app.services.clearance.uspto_client import UsptoClient

        item = run["item"]
        tier = run["tier"]
        competitors = run.get("competitors") or []
        # Stamped at creation by the API route, passed through verbatim: every
        # query the tracks run is a statement about the registers as of this
        # date, not as of whenever the worker got scheduled.
        search_date = run.get("search_date")

        client = UsptoClient()
        plan = await build_query_plan(
            item, run.get("type_hint"), run.get("field"), competitors,
            organization_id=organization_id,
        )
        result = await run_clearance_tracks(
            client, plan, item, tier, competitors, search_date=search_date,
            organization_id=organization_id,
        )
        artifact = build_artifact(item, tier, search_date, plan.assumptions, result)
        report = compose_report_markdown(
            artifact, examiner_notes=getattr(result, "examiner_notes", None)
        )

        findings = _findings_rows(run_id, organization_id, artifact)
        if findings:
            admin.table("clearance_findings").insert(findings).execute()

        admin.table("clearance_runs").update({
            "status": "complete",
            "artifact": artifact,
            "report_markdown": report,
            "completed_at": datetime.now(UTC).isoformat(),
        }).eq("id", run_id).execute()

        logger.info(
            "clearance_complete",
            run_id=run_id,
            organization_id=organization_id,
            tier=tier,
            findings=len(findings),
        )
    except Exception as exc:
        logger.exception("clearance_failed", run_id=run_id)
        _record_failure(run_id, exc)


def _findings_rows(
    run_id: str, organization_id: str, artifact: dict[str, Any]
) -> list[dict[str, Any]]:
    """Flatten the artifact's per-reference findings into queryable rows.

    Three sections map to three kinds: trademark conflicts, granted/published
    closest art, and the notable pending applications. The artifact stays the
    source of record; these rows exist so drill-down and a later watch-list can
    query one reference without parsing the blob.
    """
    # Section keys are the ip-clearance-search output contract's, verbatim —
    # "trademark" singular, "pending_landscape" — because the artifact is built
    # to that exact schema and a near-miss key here reads as zero findings.
    sections = (
        ("trademark", (artifact.get("trademark") or {}).get("conflicts")),
        ("patent", (artifact.get("patents") or {}).get("closest_art")),
        ("pending", (artifact.get("pending_landscape") or {}).get("notable_pending")),
    )
    rows: list[dict[str, Any]] = []
    for kind, entries in sections:
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            rows.append({
                "run_id": run_id,
                "organization_id": organization_id,
                "kind": kind,
                "reference_number": _first(
                    entry,
                    "number",
                    "serial_or_reg",
                    "app",
                    "reference_number",
                    "patent_number",
                    "application_number",
                    "serial_number",
                    "registration_number",
                ),
                "title": _first(entry, "title", "mark"),
                "owner": _first(entry, "owner", "assignee", "applicant"),
                "dates": entry.get("dates") or {},
                "status": entry.get("status"),
                "risk": _risk(entry.get("risk")),
                "claim_requirements": entry.get("claim_requirements"),
                "differences": entry.get("differences"),
                # Kept whole so a disputed finding can be reconstructed.
                "raw": entry,
            })
    return rows


def _first(entry: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = entry.get(key)
        if value:
            return value
    return None


def _risk(value: Any) -> str | None:
    """Normalise a risk tier to what the CHECK constraint accepts, or None.

    The database refuses anything outside GREEN/YELLOW/RED, so a variant
    casing or an unexpected tier must degrade to NULL — the original stays in
    `raw` — rather than fail the whole insert.
    """
    tier = str(value or "").strip().upper()
    return tier if tier in _RISK_TIERS else None


def _record_failure(run_id: str, exc: BaseException) -> None:
    """Leave the row saying the run failed and why.

    Without this the frontend cannot distinguish "still searching" from
    "failed", and would poll forever on a run that will never finish.
    """
    try:
        get_supabase_admin().table("clearance_runs").update({
            "status": "failed",
            "error_message": f"{type(exc).__name__}: {exc}",
        }).eq("id", run_id).execute()
    except Exception:
        logger.exception("clearance_failure_record_failed", run_id=run_id)
