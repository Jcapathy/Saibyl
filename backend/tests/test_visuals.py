"""The graphics kit: the model chooses, this module draws.

Hand-drawn SVG is a quality lottery and the stake is the one property this
product sells — that the page does not look machine-made. So the primitives
fix proportion, radius, depth and motion, and take the founder's palette from
their own design brief.

Two rules are load-bearing and both were learned the hard way on 2026-08-30:
**a graphic with nothing in it draws nothing** (a labelled placeholder was
found passing the imagery requirement and buying 27 points), and **nothing here
is raster** (a picture would raise the visual score and lower `found`).
"""
from __future__ import annotations

import json

from app.services.website.visuals import (
    PRIMITIVES,
    VISUAL_CATALOGUE,
    Palette,
    palette_from_brief,
    render_visuals,
)

BLUE = Palette(ink="#14294a", muted="#60718e", accent="#286cf0", accent_soft="#5268e9")


def _marker(name: str, payload: dict) -> str:
    return f"<!--saibyl:{name} {json.dumps(payload)}-->"


def _page(body: str) -> str:
    return f"<!doctype html><html><head><title>x</title></head><body>{body}</body></html>"


# ── drawing ─────────────────────────────────────────────────────────────────


def test_a_bar_chart_is_drawn_from_the_founders_own_numbers():
    html, drawn = render_visuals(
        _page(
            _marker(
                "bar_chart",
                {"title": "Hours", "rows": [{"label": "Chasing", "value": 9},
                                            {"label": "Working", "value": 4}]},
            )
        ),
        palette=BLUE,
    )

    assert drawn == ["bar_chart"]
    assert "<svg" in html
    # The labels survive as text, which is the whole reason this is not a
    # picture: a crawler reads them.
    assert "Chasing" in html and "Working" in html
    assert "#286cf0" in html, "the founder's accent, not a default"


def test_every_primitive_draws_something_from_a_full_payload():
    payloads = {
        "bar_chart": {"rows": [{"label": "a", "value": 2}, {"label": "b", "value": 1}]},
        "step_diagram": {"steps": ["one", "two", "three"]},
        "stat_band": {"stats": [{"value": "3 min", "label": "to draft"},
                                {"value": "$0", "label": "to start"}]},
        "device_frame": {"heading": "A headline", "action": "Start"},
    }
    assert set(payloads) == set(PRIMITIVES), "a primitive shipped without a test"
    for name, payload in payloads.items():
        html, drawn = render_visuals(_page(_marker(name, payload)), palette=BLUE)
        assert drawn == [name], name
        assert "saibyl:" not in html, name


# ── a graphic with nothing in it draws nothing ──────────────────────────────


def test_an_empty_payload_draws_nothing_and_leaves_the_marker():
    """The imagery requirement must not be buyable with an empty frame. One
    day earlier a labelled placeholder was found doing exactly that."""
    for name, payload in (
        ("bar_chart", {"rows": []}),
        ("step_diagram", {"steps": ["only one"]}),
        ("stat_band", {"stats": [{"value": "1", "label": "lonely"}]}),
        ("device_frame", {"lines": ["no heading"]}),
    ):
        html, drawn = render_visuals(_page(_marker(name, payload)), palette=BLUE)
        assert drawn == [], name
        assert "<svg" not in html, name


def test_a_row_without_a_number_is_not_charted():
    html, drawn = render_visuals(
        _page(_marker("bar_chart", {"rows": [{"label": "a", "value": "lots"}]})),
        palette=BLUE,
    )

    assert drawn == []


# ── degrading safely ────────────────────────────────────────────────────────


def test_a_malformed_payload_leaves_the_page_intact():
    """A marker that cannot be drawn stays where it is and renders as a
    comment: invisible to the reader, harmless to the layout. Substituting an
    apology would put a defect on the founder's page to report one in ours."""
    page = _page("<h1>Real</h1><!--saibyl:bar_chart {not json}--><p>Copy</p>")
    html, drawn = render_visuals(page, palette=BLUE)

    assert drawn == []
    assert "<h1>Real</h1>" in html and "<p>Copy</p>" in html


def test_an_unknown_primitive_is_left_alone():
    html, drawn = render_visuals(_page(_marker("hero_photo", {"a": 1})), palette=BLUE)

    assert drawn == []
    assert "saibyl:hero_photo" in html


def test_a_page_with_no_markers_is_returned_untouched():
    page = _page("<h1>Nothing to draw</h1>")

    assert render_visuals(page, palette=BLUE) == (page, [])


# ── the properties the product depends on ───────────────────────────────────


def test_nothing_drawn_is_raster_or_remote():
    """A picture would raise the visual score and lower `found`, and the
    rewrite's hard requirements forbid an external image outright."""
    html, _ = render_visuals(
        _page(
            _marker("bar_chart", {"rows": [{"label": "a", "value": 1}]} | {"rows": [
                {"label": "a", "value": 2}, {"label": "b", "value": 1}]})
            + _marker("device_frame", {"heading": "Hi", "action": "Go"})
        ),
        palette=BLUE,
    )

    assert "<img" not in html
    assert "url(http" not in html
    assert "data:image" not in html


def test_the_shared_style_collapses_motion_and_lands_once():
    body = "".join(
        _marker("step_diagram", {"steps": ["a", "b"]}) for _ in range(3)
    )
    html, drawn = render_visuals(_page(body), palette=BLUE)

    assert len(drawn) == 3
    assert html.count('id="saibyl-visuals"') == 1, "the style block was injected twice"
    assert "prefers-reduced-motion" in html
    assert ".01ms" in html, "the duration, not `none` — animationend must still fire"


def test_nothing_drawn_declares_itself_a_stand_in():
    """The census refuses to count anything saying "placeholder", so a
    primitive using that word would draw a graphic that does not count."""
    html, _ = render_visuals(
        _page(_marker("device_frame", {"heading": "Real headline", "action": "Go"})),
        palette=BLUE,
    )

    assert "placeholder" not in html.casefold()


def test_founder_copy_is_escaped_rather_than_injected():
    html, drawn = render_visuals(
        _page(_marker("device_frame", {"heading": "<script>alert(1)</script>"})),
        palette=BLUE,
    )

    assert drawn == ["device_frame"]
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# ── the palette is the founder's ────────────────────────────────────────────


def test_the_palette_is_read_from_the_founders_own_brief():
    brief = {
        "tokens": {
            "palette": [
                {"hex": "#0f172a", "role": "ink"},
                {"hex": "#e11d48", "role": "primary"},
            ]
        }
    }
    palette = palette_from_brief(brief)

    assert palette.ink == "#0f172a"
    assert palette.accent == "#e11d48"


def test_an_unreadable_brief_falls_back_to_neutral_not_to_ours():
    """A rewrite whose brief could not be read should look unbranded, never
    like Saibyl. A kit that painted every page one blue would be the single
    template this product exists to name."""
    neutral = palette_from_brief(None)

    assert neutral == Palette()
    assert neutral.accent != "#286cf0"


def test_a_junk_colour_is_ignored_rather_than_rendered():
    brief = {"tokens": {"palette": [{"hex": "not-a-colour", "role": "primary"}]}}

    assert palette_from_brief(brief).accent == Palette().accent


# ── the catalogue the model reads ───────────────────────────────────────────


def test_the_catalogue_names_every_primitive_and_forbids_invention():
    for name in PRIMITIVES:
        assert name in VISUAL_CATALOGUE, f"{name} is undocumented to the model"
    assert "never with hand-written SVG" in VISUAL_CATALOGUE
    assert "Do not invent" in VISUAL_CATALOGUE
    assert "at most three graphics" in VISUAL_CATALOGUE
