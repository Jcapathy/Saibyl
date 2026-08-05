# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# export_report_pdf(report_id) -> bytes
# build_document_input(report_id) -> ReportDocumentInput
# render_pdf(html: str) -> bytes
# ExportError
# MIN_PDF_BYTES
# ─────────────────────────────────────────────────────────
"""PDF export: assemble the document's inputs, typeset them, verify the result.

Three things went wrong here before, and each has a structural answer now.

**It produced nothing and said it had succeeded.** `simulation_analytics` was
refactored to return the measurement artifact's shape and none of its three
callers here were updated: `sentiment_curve` became a list of dicts while this
module still indexed it as a dict keyed by round, and `platform_events` and
`persona_events` became `platforms` and `archetypes` while this module still
read the old keys. The first raised `TypeError`, the API's fire-and-forget
wrapper swallowed it, and the caller was told the export had started and never
learnt otherwise. The fix is to read the artifact directly — one typed shape,
validated on the way in — and to *check the bytes* before claiming success.

**It rendered a fabricated number.** The heatmap was built with
`"sentiment": 0.0` hardcoded for every cell. It is gone, along with the heatmap:
there is no persona × platform sentiment field in the artifact, so under this
document's rules there is no such chart to draw.

**It hardcoded `variant="a"`.** Every analytics call asked for the first arena,
on precisely the matched-swarm runs the scoreboard exists to compare. The
artifact is per-simulation and carries every arena in `scoreboard`, so reading
it removes the parameter rather than fixing its value.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import structlog

from app.services.export.report_document import (
    DocumentSection,
    ReportDocumentInput,
    build_report_html,
)

logger = structlog.get_logger()

# The database and the report agent are imported inside `build_document_input`
# rather than at module scope. Typesetting is the expensive, fragile part of
# this file and it depends on none of that: keeping the imports local means
# `render_pdf` can be exercised — and its output counted — without standing up
# Supabase or loading a model client.

# A WeasyPrint document with a cover, a contents page and one body page does not
# come out under 6 KB. Anything smaller means the renderer produced a stub, and
# a stub must fail loudly rather than be uploaded and handed to a customer as
# their report.
MIN_PDF_BYTES = 6_000


class ExportError(RuntimeError):
    """An export that did not produce a usable file.

    Raised rather than returned. The whole class of defect this replaces is a
    success response with no file behind it, and that only happens when a
    failure has somewhere quiet to go.
    """


def _row(table: str, column: str, value: str, select: str = "*") -> dict:
    from app.core.database import get_supabase_admin

    admin = get_supabase_admin()
    result = (
        admin.table(table).select(select).eq(column, value).limit(1).execute()
    )
    rows = result.data or []
    if not rows:
        raise ExportError(f"{table}: no row with {column}={value}")
    return rows[0]


def build_document_input(report_id: str | UUID) -> ReportDocumentInput:
    """Read every row the document needs and shape it for the typesetter.

    Separated from rendering so the document can be built and asserted on
    without a PDF engine, and so a missing row fails here — named — rather than
    as a `KeyError` three layers down inside a template.
    """
    from app.core.database import get_supabase_admin
    from app.services.intelligence.report_agent import clean_report_output

    admin = get_supabase_admin()
    report_id = str(report_id)

    report = _row("reports", "id", report_id)
    simulation_id = str(report["simulation_id"])
    simulation = _row("simulations", "id", simulation_id)
    organization = _row(
        "organizations", "id", str(report["organization_id"]), select="name"
    )

    sections = (
        admin.table("report_sections")
        .select("section_index, title, content")
        .eq("report_id", report_id)
        .order("section_index")
        .execute()
    ).data or []

    # The artifact, read the same way the viewer reads it: the stored
    # `schema_version` travels with the payload so the document can refuse an
    # unknown format instead of rendering the fields it recognises.
    from app.services.intelligence.analysis_builder import get_analysis

    stored = get_analysis(simulation_id) or {}
    artifact = stored.get("artifact") if stored.get("build_status") == "complete" else None
    schema_version = stored.get("schema_version") if artifact else None

    agent_count = simulation.get("agent_count")
    if agent_count is None:
        counted = (
            admin.table("simulation_agents")
            .select("id", count="exact")
            .eq("simulation_id", simulation_id)
            .limit(1)
            .execute()
        )
        agent_count = counted.count or None

    run_started = simulation.get("created_at")
    if run_started:
        try:
            run_started = datetime.fromisoformat(
                str(run_started).replace("Z", "+00:00")
            ).strftime("%d %B %Y")
        except ValueError:
            run_started = str(run_started)

    return ReportDocumentInput(
        org_name=organization.get("name") or "",
        simulation_name=simulation.get("name") or "Simulation",
        report_title=report.get("title") or "Predictive intelligence report",
        prediction_goal=simulation.get("prediction_goal") or "",
        generated_at=datetime.now(UTC),
        report_id=report_id,
        simulation_id=simulation_id,
        platforms=list(simulation.get("platforms") or []),
        max_rounds=simulation.get("max_rounds"),
        variants=int(simulation.get("variants") or 1),
        agent_count=agent_count,
        run_started=run_started,
        schema_version=schema_version,
        artifact=artifact,
        sections=[
            DocumentSection(
                title=section.get("title") or "",
                content=clean_report_output(section.get("content") or ""),
            )
            for section in sections
        ],
    )


def render_pdf(html: str) -> bytes:
    """Typeset the document. Raises `ExportError` rather than returning a stub."""
    try:
        from weasyprint import HTML
    except Exception as exc:  # pragma: no cover - deployment dependency
        # Not just `ImportError`. When the package is installed but its native
        # libraries are not, the import raises `OSError` from `ffi.dlopen`, and
        # catching only `ImportError` would let a deployment fault surface as a
        # stack trace instead of a stated export failure.
        raise ExportError(
            "WeasyPrint is unavailable, so no PDF can be produced. It needs "
            "pango, cairo and gdk-pixbuf, which the backend image installs."
        ) from exc

    pdf_bytes = HTML(string=html).write_pdf()
    if not pdf_bytes or len(pdf_bytes) < MIN_PDF_BYTES:
        raise ExportError(
            f"PDF rendering produced {len(pdf_bytes or b'')} bytes, below the "
            f"{MIN_PDF_BYTES}-byte floor for a real document."
        )
    if not pdf_bytes.startswith(b"%PDF-"):
        raise ExportError("PDF rendering produced bytes that are not a PDF.")
    return pdf_bytes


async def export_report_pdf(report_id: str | UUID) -> bytes:
    """The print-quality report for one report row, as PDF bytes."""
    document = build_document_input(report_id)
    html = build_report_html(document)
    # Typesetting is CPU-bound and takes long enough on a multi-page document to
    # be felt by every other request on the worker. Off the event loop.
    pdf_bytes = await asyncio.to_thread(render_pdf, html)
    logger.info(
        "pdf_exported",
        report_id=str(report_id),
        simulation_id=document.simulation_id,
        bytes=len(pdf_bytes),
        measured=document.artifact is not None,
        sections=len(document.sections),
    )
    return pdf_bytes
