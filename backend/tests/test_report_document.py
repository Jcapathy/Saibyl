"""The exported document's honesty rules, as properties of the HTML it produces.

Each test here corresponds to a defect this product shipped, not to a style
preference. `build_report_html` is pure, so every one of them is checkable
without a database, a renderer or a browser.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest

from app.services.export.markdown_lite import markdown_to_html
from app.services.export.report_document import (
    SUPPORTED_SCHEMA_VERSION,
    DocumentSection,
    ReportDocumentInput,
    build_report_html,
    load_artifact,
)
from tests.analysis_fixtures import (
    REPORT_ID,
    SECTION_MARKDOWN,
    SIMULATION_ID,
    make_analysis,
    make_scoreboard,
)


def _doc(
    *,
    analysis=None,
    schema_version: int | None = SUPPORTED_SCHEMA_VERSION,
    sections: list[DocumentSection] | None = None,
) -> ReportDocumentInput:
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
        schema_version=schema_version if analysis is not None else None,
        artifact=analysis.model_dump(mode="json") if analysis is not None else None,
        sections=sections
        if sections is not None
        else [
            DocumentSection("Executive Summary", "The swarm turned on cost, not speed."),
            DocumentSection("Platform Dynamics", SECTION_MARKDOWN),
            DocumentSection("Strategic Implications", "Lead with cost. Publish the price."),
        ],
    )


def _figures(html: str) -> list[str]:
    return re.findall(r"<svg\b.*?</svg>", html, flags=re.DOTALL)


# ── the artifact gate ────────────────────────────────────────────────


def test_unknown_schema_version_renders_nothing_measured():
    """Matching the viewer: an unreadable format renders no figures at all.

    Not "the fields the two formats happen to share" — that is how a Founder-lens
    run loses its adversarial disclosure while still looking complete.
    """
    doc = _doc(analysis=make_analysis(), schema_version=SUPPORTED_SCHEMA_VERSION + 1)
    html = build_report_html(doc)

    assert not _figures(html), "an unknown artifact format must draw no figures"
    assert "Incumbent power user" not in html
    assert f"format {SUPPORTED_SCHEMA_VERSION + 1}" in html
    assert f"reads formats 1 to {SUPPORTED_SCHEMA_VERSION}" in html


def test_missing_artifact_says_so_and_draws_nothing():
    html = build_report_html(_doc(analysis=None))
    assert not _figures(html)
    assert "has not been analysed" in html
    # The narrative still prints; it is the *figures* that require measurement.
    assert "Lead with cost" in html


def test_invalid_artifact_is_refused_rather_than_partially_rendered():
    analysis, reason = load_artifact(SUPPORTED_SCHEMA_VERSION, {"simulation_id": "x"})
    assert analysis is None
    assert "did not validate" in reason


@pytest.mark.parametrize("version", [0, -1, SUPPORTED_SCHEMA_VERSION + 1, 99])
def test_out_of_range_versions_are_all_refused(version):
    analysis, reason = load_artifact(version, make_analysis().model_dump(mode="json"))
    assert analysis is None
    assert str(version) in reason


# ── unmeasured is absent, not zero ───────────────────────────────────


def test_unmeasured_round_is_absent_from_the_arc():
    """Round 4 has `n = 0`. A zero-height column would read as "neutral"."""
    html = build_report_html(_doc(analysis=make_analysis()))
    arc = next(f for f in _figures(html) if "R1" in f and "R5" in f)
    assert ">R4<" not in arc, "an unmeasured round must not be plotted"
    assert ">R3<" in arc and ">R5<" in arc


def test_unmeasured_platform_is_absent_from_every_figure_and_table():
    """LinkedIn was configured and never spoke. It is not a neutral platform."""
    html = build_report_html(_doc(analysis=make_analysis()))
    figures = "".join(_figures(html))
    assert "LinkedIn" not in figures
    assert "Reddit" in figures and "Hacker News" in figures


def test_no_fabricated_sentiment_zero_anywhere():
    """The `"sentiment": 0.0` heatmap class of defect, checked directly.

    Every valence figure drawn must come from an interval the fixture actually
    measured; none of them is 0.00, so a rendered "+0.00" can only have been
    invented.
    """
    analysis = make_analysis()
    html = build_report_html(_doc(analysis=analysis))
    values = re.findall(r">([+−]\d\.\d\d)<", "".join(_figures(html)))
    assert values, "the figures should carry direct value labels"

    measured = {
        f"{'+' if v >= 0 else '−'}{abs(v):.2f}"
        for interval in (
            [p.valence for p in analysis.sentiment_timeline]
            + [s.valence for s in analysis.by_platform]
            + [s.valence for s in analysis.by_archetype]
            + [s.valence for s in analysis.by_cohort]
            + [analysis.headline.valence]
        )
        if interval.n > 0
        for v in (interval.mean, interval.lower, interval.upper)
    }
    unaccounted = set(values) - measured
    assert not unaccounted, f"figures show values with no measurement behind them: {unaccounted}"
    # Zero-width intervals are the sentinel for "nothing was measured"; none of
    # them survives into a label.
    assert "+0.00" not in values


# ── intervals travel with their means ────────────────────────────────


def test_every_plotted_mean_carries_its_band():
    analysis = make_analysis()
    html = build_report_html(_doc(analysis=analysis))
    figures = "".join(_figures(html))

    for slice_ in analysis.by_platform:
        if slice_.valence.n == 0:
            continue
        for bound in (slice_.valence.lower, slice_.valence.upper):
            rendered = f"{'+' if bound >= 0 else '−'}{abs(bound):.2f}"
            assert rendered in figures, f"missing bound {rendered}"


def test_headline_mean_is_never_printed_without_its_interval():
    analysis = make_analysis()
    html = build_report_html(_doc(analysis=analysis))
    mean = f"−{abs(analysis.headline.valence.mean):.2f}"
    assert mean in html
    lower = f"−{abs(analysis.headline.valence.lower):.2f}"
    upper = f"−{abs(analysis.headline.valence.upper):.2f}"
    assert lower in html and upper in html
    assert "95% CI" in html
    assert f"n={analysis.headline.valence.n}" in html


def test_single_agent_slice_is_labelled_as_an_anecdote():
    analysis = make_analysis()
    html = build_report_html(_doc(analysis=analysis))
    figures = "".join(_figures(html))
    # The CFO archetype has n=1 and a band spanning the whole scale; both the
    # count and the full-scale band must be visible.
    assert "Skeptical CFO" in figures
    assert "n=1" in figures


# ── ordering is not ranking ──────────────────────────────────────────


def test_no_winner_means_no_implied_winner():
    analysis = make_analysis(scoreboard=make_scoreboard(with_winner=False))
    html = build_report_html(_doc(analysis=analysis))

    assert "No winner" in html
    assert "not a ranking" in html
    assert "— winner" not in html, "no row may be marked as the winner"
    assert "No marker is emphasised" in html


def test_named_winner_is_stated_and_marked():
    analysis = make_analysis(scoreboard=make_scoreboard(with_winner=True))
    html = build_report_html(_doc(analysis=analysis))

    assert "Winner: Cost-first framing" in html
    assert "Cost-first framing — winner" in html
    assert "person by person" in html
    assert "No winner" not in html


def test_scoreboard_rates_carry_their_intervals():
    analysis = make_analysis(scoreboard=make_scoreboard(with_winner=True))
    html = build_report_html(_doc(analysis=analysis))
    # 41.0% with a 6-point half-width becomes 35.0% to 47.0%.
    assert "41.0%" in html
    assert "35.0% to 47.0%" in html
    assert "Blank cells are unmeasured, not zero." in html


# ── page furniture and fragmentation ─────────────────────────────────


def test_page_geometry_is_us_letter_with_real_margins():
    html = build_report_html(_doc(analysis=make_analysis()))
    assert "size: Letter" in html
    assert re.search(r"@page\s*\{[^}]*margin:\s*0\.\d+in", html)


def test_running_header_and_footer_live_in_margin_boxes():
    html = build_report_html(_doc(analysis=make_analysis()))
    for box in ("@top-left", "@top-right", "@bottom-left", "@bottom-center", "@bottom-right"):
        assert box in html
    assert 'content: "Page " counter(page) " of " counter(pages)' in html
    assert "Northwind Capital · Series B positioning test" in html
    assert "content: string(section)" in html
    # The running head takes the section *name*, not the whole heading: setting
    # it from the `h2` swept the "Section 4" label in and printed
    # "SECTION 4OBJECTIONS".
    assert "h2.section-title .name {\n    string-set: section content(text);" in html
    assert '<span class="name">Objections</span>' in html
    # A running head that wraps stops being page furniture and starts being
    # content in the margin.
    assert html.count("white-space: nowrap;\n        overflow: hidden;") == 2


def test_cover_is_a_distinct_page_with_no_furniture():
    html = build_report_html(_doc(analysis=make_analysis()))
    cover_rule = re.search(r"@page cover \{(.*?)\n\}", html, flags=re.DOTALL)
    assert cover_rule, "the cover needs its own named page"
    body = cover_rule.group(1)
    assert body.count("content: none;") == 6, "every margin box must be suppressed"
    assert "page: cover" in html


def test_nothing_atomic_may_split_across_a_page():
    html = build_report_html(_doc(analysis=make_analysis()))
    for rule in (
        "figure {",
        ".callout {",
        ".metrics {",
        "blockquote {",
    ):
        block = html.split(rule, 1)[1].split("}", 1)[0]
        assert "break-inside: avoid" in block, f"{rule} must not split"


def test_headings_never_sit_alone_at_the_foot_of_a_page():
    html = build_report_html(_doc(analysis=make_analysis()))
    block = html.split("h1, h2, h3, h4, h5, h6 {", 1)[1].split("}", 1)[0]
    assert "break-after: avoid" in block
    assert "orphans: 3" in html and "widows: 3" in html


def test_tables_repeat_their_header_across_pages():
    html = build_report_html(_doc(analysis=make_analysis()))
    assert "display: table-header-group" in html
    assert "font-variant-numeric: tabular-nums" in html


def test_contents_page_lists_every_section_with_a_resolved_page_number():
    html = build_report_html(_doc(analysis=make_analysis(scoreboard=make_scoreboard(with_winner=True))))
    assert "target-counter(attr(href), page)" in html

    anchors = re.findall(r'<li[^>]*>.*?<a href="#([a-z-]+)">', html)
    sections = re.findall(r'<section class="doc-section" id="([a-z-]+)"', html)
    listed = [s for s in sections if s != "contents"]
    assert anchors == listed, "contents and body must not drift apart"
    assert "executive-summary" in anchors
    assert "methodology" in anchors


def test_executive_summary_stands_alone_before_the_numbered_sections():
    html = build_report_html(_doc(analysis=make_analysis()))
    exec_at = html.index('id="executive-summary"')
    scope_at = html.index('id="scope"')
    assert exec_at < scope_at
    assert 'Section 1</span><span class="name">Scope and method</span>' in html
    # `.doc-section` forces a page break before each section, so the summary
    # cannot share a page with what follows it.
    assert "break-before: page" in html


# ── charts are vector and readable in greyscale ──────────────────────


def test_figures_are_inline_vector_not_raster():
    html = build_report_html(_doc(analysis=make_analysis()))
    assert _figures(html), "the document should carry figures"
    assert "<img" not in html
    assert "data:image/png;base64" not in html


def test_no_figure_encodes_meaning_in_colour():
    """Every ink in a figure is neutral, so a greyscale print is the same image.

    Chroma rather than HSV saturation: saturation is unstable at low lightness
    and would let a near-black blue through while flagging a legitimate dark
    grey.
    """
    html = build_report_html(
        _doc(analysis=make_analysis(scoreboard=make_scoreboard(with_winner=True)))
    )
    figures = "".join(_figures(html))
    colours = set(re.findall(r"#[0-9a-fA-F]{6}", figures))
    assert colours, "figures should declare their inks explicitly"
    for colour in colours:
        r, g, b = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
        chroma = (max(r, g, b) - min(r, g, b)) / 255
        assert chroma <= 0.12, f"{colour} carries hue; a greyscale print would lose it"


def test_hatching_is_drawn_wherever_the_rectangle_sits():
    """The texture must not depend on where on the canvas the mark landed.

    It did: the candidate lines were generated around the SVG origin rather than
    around the rectangle, so any bar not at the top-left clipped to nothing and
    the greyscale distinction disappeared without any error.
    """
    from app.services.export.vector_charts import _hatch

    at_origin = _hatch(0, 0, 40, 30).count("<line")
    far_away = _hatch(360, 240, 40, 30).count("<line")
    assert at_origin > 5
    # Where the grid of candidate lines falls relative to the rectangle can add
    # or drop one line at an edge; a rectangle away from the origin producing
    # *none* is the bug.
    assert abs(far_away - at_origin) <= 1


def test_negative_columns_are_distinguished_by_texture_not_colour():
    html = build_report_html(_doc(analysis=make_analysis()))
    arc = next(f for f in _figures(html) if "R1" in f)
    # Hatching is drawn as real line geometry, so it survives any renderer that
    # does not implement `<pattern>`.
    assert arc.count("<line") > 10
    assert 'fill="#ffffff"' in arc, "negative columns are hollow, then hatched"


# ── narrative typesetting ────────────────────────────────────────────


def test_markdown_tables_become_real_tables_with_aligned_numerals():
    html = markdown_to_html(SECTION_MARKDOWN)
    assert "<table class=\"md-table\">" in html
    assert "<thead>" in html
    assert html.count("<tr>") == 3
    assert '<td class="num">-0.58</td>' in html
    assert '<td class="txt">Reddit</td>' in html


def test_markdown_lists_and_emphasis_survive():
    html = markdown_to_html(SECTION_MARKDOWN)
    assert "<ul>" in html and html.count("<li>") == 3
    assert "<strong>load-bearing</strong>" in html
    assert "<blockquote>" in html
    assert "<br>" not in html, "line breaks are not a substitute for typesetting"


def test_markdown_headings_are_demoted_under_the_section_title():
    html = markdown_to_html("## Subsection\n\nBody.", heading_base=3)
    assert "<h4>Subsection</h4>" in html
    assert "<h2" not in html


def test_markdown_escapes_html_in_agent_text():
    html = markdown_to_html("Agents said <script>alert(1)</script> repeatedly.")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


# ── required disclosures ─────────────────────────────────────────────


def test_adversarial_cohort_is_disclosed_on_the_cover_and_in_the_method():
    html = build_report_html(_doc(analysis=make_analysis()))
    cover = html.split('<section class="doc-section" id="contents"', 1)[0]
    assert "built to argue against you" in cover
    assert html.count("Who was arguing against you") >= 1
    assert "Some of this room was built to argue against you" in html


def test_document_states_that_every_agent_is_synthetic():
    html = build_report_html(_doc(analysis=make_analysis()))
    assert "Everybody in this run is synthetic" in html


def test_methodology_states_where_the_numbers_come_from():
    html = build_report_html(_doc(analysis=make_analysis()))
    assert "read from one artifact" in html
    assert "computed across <em>people</em>" in html
    assert "absent, not zero" in html or "unmeasured values" in html
