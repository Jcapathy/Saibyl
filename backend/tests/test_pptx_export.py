"""The deck carries charts, and its numbers come from the artifact.

`V1_AUDIT` item 36: "PPTX ships with zero charts". It did — all three of its
`simulation_analytics` calls read keys the refactored tool stopped returning,
and the whole block was wrapped in a `try` that logged a warning and continued.
The deck was produced, uploaded and downloaded with the chart slides simply
missing.

So the assertion is a *count of pictures*, not "no exception".
"""
from __future__ import annotations

import asyncio
import io

import pytest

pptx = pytest.importorskip("pptx", reason="python-pptx is a deployment dependency")

from app.services.export import pptx_exporter  # noqa: E402
from app.services.export.chart_renderer import (  # noqa: E402
    ChartRow,
    render_interval_rows_png,
    render_sentiment_arc_png,
)
from tests.analysis_fixtures import (  # noqa: E402
    REPORT_ID,
    SIMULATION_ID,
    make_analysis,
    make_scoreboard,
)

PICTURE = 13  # MSO_SHAPE_TYPE.PICTURE


def _rows() -> list[ChartRow]:
    return [
        ChartRow(label="1", mean=-0.08, lower=-0.29, upper=0.13, n=22),
        ChartRow(label="2", mean=-0.52, lower=-0.68, upper=-0.36, n=24),
    ]


def test_chart_renderers_produce_real_pngs():
    arc = render_sentiment_arc_png(_rows())
    rows = render_interval_rows_png(_rows(), "Test")
    for png in (arc, rows):
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        assert len(png) > 10_000, "a 200 dpi chart is not a few hundred bytes"


def test_chart_renderers_refuse_an_empty_series():
    """Rather than drawing an empty axis that reads as "nothing happened"."""
    with pytest.raises(ValueError):
        render_sentiment_arc_png([])
    with pytest.raises(ValueError):
        render_interval_rows_png([], "Test")


class _Table:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        return type("R", (), {"data": self._rows, "count": len(self._rows)})()


class _Admin:
    def __init__(self, tables: dict[str, list[dict]]):
        self._tables = tables

    def table(self, name: str):
        return _Table(self._tables.get(name, []))


@pytest.fixture
def _deck_rows(monkeypatch):
    analysis = make_analysis(scoreboard=make_scoreboard(with_winner=False))
    admin = _Admin(
        {
            "reports": [
                {
                    "id": REPORT_ID,
                    "simulation_id": SIMULATION_ID,
                    "title": "Predictive intelligence report",
                }
            ],
            "simulations": [
                {
                    "id": SIMULATION_ID,
                    "name": "Series B positioning test",
                    "prediction_goal": "Will buyers switch?",
                    "platforms": ["reddit", "hacker_news"],
                    "max_rounds": 5,
                    "variants": 3,
                }
            ],
            "report_sections": [
                {"section_index": 0, "title": "Executive Summary", "content": "Cost, not speed."}
            ],
        }
    )
    monkeypatch.setattr(pptx_exporter, "get_supabase_admin", lambda: admin)
    monkeypatch.setattr(
        "app.services.intelligence.analysis_builder.get_analysis",
        lambda _sim: {
            "build_status": "complete",
            "schema_version": analysis.schema_version,
            "artifact": analysis.model_dump(mode="json"),
        },
    )
    return analysis


def test_deck_carries_chart_slides(_deck_rows):
    data = asyncio.run(pptx_exporter.export_report_pptx(REPORT_ID))
    assert data[:2] == b"PK", "a .pptx is a zip"

    deck = pptx.Presentation(io.BytesIO(data))
    slides = list(deck.slides)
    assert len(slides) >= 8, f"only {len(slides)} slides"

    pictures = [
        shape
        for slide in slides
        for shape in slide.shapes
        if shape.shape_type == PICTURE
    ]
    assert len(pictures) >= 4, f"only {len(pictures)} chart slides — audit 36 again"


def test_deck_states_the_verdict_and_the_disclosure(_deck_rows):
    data = asyncio.run(pptx_exporter.export_report_pptx(REPORT_ID))
    deck = pptx.Presentation(io.BytesIO(data))
    text = "\n".join(
        shape.text_frame.text
        for slide in deck.slides
        for shape in slide.shapes
        if shape.has_text_frame
    )

    assert "no winner" in text.lower()
    assert "not a ranking" in text
    assert "built to argue against you" in text, "PRD §4 disclosure must be on its own slide"
    assert "95% CI" in text, "a mean without its band does not leave this product"
    assert "unmeasured values are absent, not zero" in text
