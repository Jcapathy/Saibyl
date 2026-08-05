"""The PDF export produces a real file, or fails loudly.

The defect this replaces: the export raised inside a fire-and-forget task, the
API answered `{"status": "started"}`, and no file was ever written. "No
exception" is therefore not a sufficient assertion — the exporter used to throw
one and the product still reported success. These tests count bytes and pages.

`render_pdf` needs WeasyPrint, which needs pango, cairo and gdk-pixbuf from the
host. The backend image installs them (`backend/Dockerfile`) and Render runs
that image, so these run in CI and in the container. On a bare Windows
workstation they skip with the reason stated rather than silently passing.
"""
from __future__ import annotations

import dataclasses
import io
import sys
import types
from datetime import UTC, datetime

import pytest

from app.services.export.pdf_exporter import (
    MIN_PDF_BYTES,
    ExportError,
    render_pdf,
)
from app.services.export.report_document import (
    DocumentSection,
    ReportDocumentInput,
    build_report_html,
)
from tests.analysis_fixtures import (
    REPORT_ID,
    SECTION_MARKDOWN,
    SIMULATION_ID,
    make_analysis,
    make_scoreboard,
)

pypdf = pytest.importorskip("pypdf", reason="pypdf is needed to inspect the output")


def _weasyprint_available() -> bool:
    try:
        import weasyprint  # noqa: F401
    except Exception:
        return False
    return True


requires_weasyprint = pytest.mark.skipif(
    not _weasyprint_available(),
    reason=(
        "WeasyPrint could not load its native libraries (pango/cairo/"
        "gdk-pixbuf). It is installed in the backend image; a PDF cannot be "
        "rendered here."
    ),
)


def _document() -> ReportDocumentInput:
    analysis = make_analysis(scoreboard=make_scoreboard(with_winner=True))
    return ReportDocumentInput(
        org_name="Northwind Capital",
        simulation_name="Series B positioning test",
        report_title="Predictive intelligence report",
        prediction_goal="Will growth-stage buyers switch off the incumbent?",
        generated_at=datetime(2026, 8, 3, 15, 0, tzinfo=UTC),
        report_id=REPORT_ID,
        simulation_id=SIMULATION_ID,
        platforms=["reddit", "hacker_news", "linkedin"],
        max_rounds=5,
        variants=3,
        agent_count=25,
        run_started="01 August 2026",
        schema_version=analysis.schema_version,
        artifact=analysis.model_dump(mode="json"),
        sections=[
            DocumentSection("Executive Summary", "The swarm turned on cost, not speed."),
            DocumentSection("Platform Dynamics", SECTION_MARKDOWN),
            DocumentSection("Archetype Response", SECTION_MARKDOWN),
            DocumentSection("Strategic Implications", "Lead with cost. Publish the price."),
        ],
    )


@requires_weasyprint
def test_export_produces_a_multi_page_pdf():
    pdf = render_pdf(build_report_html(_document()))

    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 40_000, f"only {len(pdf)} bytes — that is not a real report"

    reader = pypdf.PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) >= 5, f"only {len(reader.pages)} pages"

    # US Letter, in PDF points, within a rounding point.
    box = reader.pages[0].mediabox
    assert abs(float(box.width) - 612) < 1.5
    assert abs(float(box.height) - 792) < 1.5


@requires_weasyprint
def test_page_furniture_is_present_on_body_pages_and_absent_from_the_cover():
    pdf = render_pdf(build_report_html(_document()))
    reader = pypdf.PdfReader(io.BytesIO(pdf))
    total = len(reader.pages)

    cover = reader.pages[0].extract_text()
    assert "SAIBYL" in cover
    assert "Page 1 of" not in cover, "the cover carries no folio"

    body = reader.pages[2].extract_text()
    assert f"of {total}" in body, "the folio must know the document's length"
    assert "NORTHWIND CAPITAL" in body.upper(), "running header names the client"
    assert "CONFIDENTIAL" in body.upper()


@requires_weasyprint
def test_contents_page_carries_resolved_page_numbers():
    pdf = render_pdf(build_report_html(_document()))
    reader = pypdf.PdfReader(io.BytesIO(pdf))
    contents = reader.pages[1].extract_text()

    assert "Contents" in contents
    assert "Executive summary" in contents
    assert "Scope and method" in contents
    # `target-counter` resolved to a real folio rather than leaving the leader
    # dangling with nothing after it.
    digits = [line for line in contents.splitlines() if line.strip().rstrip(".").strip()[-1:].isdigit()]
    assert digits, "no contents entry resolved to a page number"


@requires_weasyprint
def test_a_run_with_no_artifact_still_produces_a_document_that_says_why():
    bare = dataclasses.replace(_document(), schema_version=None, artifact=None)
    pdf = render_pdf(build_report_html(bare))
    assert len(pdf) > MIN_PDF_BYTES

    reader = pypdf.PdfReader(io.BytesIO(pdf))
    text = " ".join(page.extract_text() for page in reader.pages)
    assert "has not been analysed" in text


def test_a_stub_render_is_an_error_not_a_success(monkeypatch):
    """The floor that turns "wrote nothing" into a failure the caller sees."""
    import app.services.export.pdf_exporter as exporter

    class _Stub:
        def __init__(self, *args, **kwargs):
            pass

        def write_pdf(self):
            return b"%PDF-1.7\n%%EOF\n"

    module = types.ModuleType("weasyprint")
    module.HTML = _Stub
    monkeypatch.setitem(sys.modules, "weasyprint", module)

    with pytest.raises(ExportError, match="below the"):
        exporter.render_pdf("<html><body>hi</body></html>")


def test_non_pdf_bytes_are_an_error(monkeypatch):
    import app.services.export.pdf_exporter as exporter

    class _Stub:
        def __init__(self, *args, **kwargs):
            pass

        def write_pdf(self):
            return b"<html>not a pdf</html>" * 500

    module = types.ModuleType("weasyprint")
    module.HTML = _Stub
    monkeypatch.setitem(sys.modules, "weasyprint", module)

    with pytest.raises(ExportError, match="not a PDF"):
        exporter.render_pdf("<html><body>hi</body></html>")
