"""The counted half of the website check.

Every test here runs without a browser, without a model and without a network,
which is the entire argument for the module: a finding that needs none of those
things is a finding that cannot drift, cannot hallucinate and costs nothing to
re-run. If any test in this file ever needs a fixture that fakes a model
response, the module has grown something it should not have.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.website.measured import (
    EM_DASHES_PER_1K_LIMIT,
    FONT_FAMILY_LIMIT,
    MEASURED_KEY,
    RADIUS_SCALE_LIMIT,
    measure_page,
)


def _rows(*values: str) -> list[dict]:
    return [{"value": value, "count": 1} for value in values]


def _capture(*, text: str = "", census: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(dom_text=text, style_census=census or {})


def _prose(words: int, *, dashes: int = 0) -> str:
    """Filler with a known word count and a known number of em-dashes."""
    body = " ".join(f"word{i}" for i in range(words))
    if dashes:
        body += " " + " ".join(
            f"A sentence long enough to be quoted back at the founder — "
            f"with an aside number {i} inside it."
            for i in range(dashes)
        )
    return body


def _keys(dimension) -> list[str]:
    return [f.region for f in dimension.findings]


# ── The module answers at all, on nothing ────────────────────────────────────

def test_a_capture_with_nothing_to_measure_returns_nothing():
    """A census can legitimately be empty: `capture` treats a failed census as
    something that must never fail the capture. Scoring that 100 would put a
    perfect mark on a page nothing was measured on and reward it for having
    defeated the census."""
    assert measure_page(_capture()) is None


def test_a_capture_missing_the_attributes_entirely_is_still_safe():
    """`measure_page` takes the capture structurally, so it must not assume the
    fields exist."""
    assert measure_page(SimpleNamespace()) is None


def test_text_alone_is_enough_to_measure_even_with_no_census():
    """The copy checks need no browser measurement, so a census failure must not
    cost the founder the half of the review that still works."""
    dimension = measure_page(_capture(text=_prose(400, dashes=40)))

    assert dimension is not None
    assert dimension.key == MEASURED_KEY
    assert any(f.region == "body copy" for f in dimension.findings)


# ── Em-dash density ──────────────────────────────────────────────────────────

def test_ordinary_editorial_use_of_the_em_dash_is_not_a_finding():
    """The check is about a habit, not about the character. A page allowed to
    fail here for using two em-dashes would be a check nobody could act on."""
    dimension = measure_page(_capture(text=_prose(1000, dashes=3)))

    assert not any(f.region == "body copy" for f in dimension.findings)
    assert "does not lean on the em-dash" in " ".join(dimension.strengths)


def test_a_page_that_uses_an_em_dash_in_most_sentences_is_a_finding():
    dimension = measure_page(_capture(text=_prose(400, dashes=40)))

    body = [f for f in dimension.findings if f.region == "body copy"]
    assert len(body) == 1
    assert "em-dashes" in body[0].quote
    assert "per 1,000" in body[0].quote


def test_the_em_dash_finding_quotes_a_real_sentence_from_the_page():
    """A count with no example is a number the founder has to take on faith."""
    dimension = measure_page(_capture(text=_prose(300, dashes=30)))

    body = next(f for f in dimension.findings if f.region == "body copy")
    assert "For example:" in body.quote


def test_density_is_not_judged_on_a_page_with_almost_no_copy():
    """Three em-dashes in six words is a ratio, not a habit. Reporting it would
    make every short landing page fail for having a punchy tagline."""
    census = {"structure": {"headings": {"h1": 1}, "images": 2}}
    dimension = measure_page(_capture(text="Short — punchy — copy — here.", census=census))

    assert dimension is not None
    assert not any(f.region == "body copy" for f in dimension.findings)


def test_the_threshold_is_the_published_constant_and_not_a_hidden_number():
    """The limit is a constant so it can be argued with; this pins that the code
    actually uses it."""
    just_under = _prose(1000, dashes=EM_DASHES_PER_1K_LIMIT)
    well_over = _prose(1000, dashes=EM_DASHES_PER_1K_LIMIT * 4)

    assert not any(f.region == "body copy" for f in measure_page(_capture(text=just_under)).findings)
    assert any(f.region == "body copy" for f in measure_page(_capture(text=well_over)).findings)


# ── Heading structure ────────────────────────────────────────────────────────

def test_a_page_with_no_top_level_heading_is_told_so():
    dimension = measure_page(
        _capture(census={"structure": {"headings": {"h1": 0, "h2": 4}, "images": 2}})
    )

    finding = next(f for f in dimension.findings if f.region == "page structure")
    assert finding.quote == "h1 elements on the page: 0"
    assert finding.severity == "major"
    assert finding.fix


def test_several_top_level_headings_are_a_lesser_finding_than_none():
    none = measure_page(_capture(census={"structure": {"headings": {"h1": 0}, "images": 1}}))
    many = measure_page(_capture(census={"structure": {"headings": {"h1": 3}, "images": 1}}))

    assert none.findings[0].severity == "major"
    assert many.findings[0].severity == "minor"


def test_one_top_level_heading_is_not_a_finding():
    dimension = measure_page(
        _capture(census={"structure": {"headings": {"h1": 1, "h2": 5}, "images": 3}})
    )

    assert not any(f.region == "page structure" for f in dimension.findings)


def test_a_missing_rung_in_the_outline_is_reported():
    dimension = measure_page(
        _capture(census={"structure": {"headings": {"h1": 1, "h2": 0, "h3": 6}, "images": 1}})
    )

    finding = next(f for f in dimension.findings if "h3" in f.quote)
    assert "h2: 0" in finding.quote


# ── Sprawl checks ────────────────────────────────────────────────────────────

def test_a_radius_scale_is_reported_as_a_strength_rather_than_silence():
    """A check that only ever speaks when something is wrong tells the founder
    nothing about what they got right."""
    dimension = measure_page(
        _capture(census={"shape": {"border_radius": _rows("8px", "16px", "0px")}})
    )

    assert not any(f.region == "components" for f in dimension.findings)
    assert any("scale of 2" in s for s in dimension.strengths)


def test_square_corners_do_not_count_against_the_radius_scale():
    """`0px` is a decision to have no radius, not a rung on the scale."""
    values = ["0px"] * 6 + ["8px", "16px"]
    dimension = measure_page(
        _capture(census={"shape": {"border_radius": _rows(*values)}})
    )

    assert not any(f.region == "components" for f in dimension.findings)


def test_many_different_radii_are_a_finding_with_the_values_quoted():
    values = ["2px", "3px", "5px", "7px", "9px", "11px", "13px"]
    dimension = measure_page(
        _capture(census={"shape": {"border_radius": _rows(*values)}})
    )

    finding = next(f for f in dimension.findings if "corner radii" in f.quote)
    assert "2px" in finding.quote
    assert str(RADIUS_SCALE_LIMIT) in finding.quote


def test_a_count_that_hits_the_census_cap_is_reported_as_at_least():
    """`capture._top` keeps ten rows. Ten measured and forty present look
    identical here, so the report must not claim the exact number."""
    values = [f"{n}px" for n in range(1, 11)]
    dimension = measure_page(
        _capture(census={"shape": {"border_radius": _rows(*values)}})
    )

    finding = next(f for f in dimension.findings if "corner radii" in f.quote)
    assert "at least 10" in finding.quote


def test_a_count_below_the_cap_states_the_exact_number():
    values = [f"{n}px" for n in range(1, 8)]
    dimension = measure_page(
        _capture(census={"shape": {"border_radius": _rows(*values)}})
    )

    finding = next(f for f in dimension.findings if "corner radii" in f.quote)
    assert "at least" not in finding.quote
    assert "7 distinct" in finding.quote


def test_a_deliberate_type_pairing_is_a_strength_and_a_pile_is_a_finding():
    pairing = measure_page(
        _capture(
            census={
                "fonts": {
                    "families": [
                        {"family": "Manrope", "stack": "Manrope, sans-serif", "count": 40},
                        {"family": "Playfair Display", "stack": "Playfair Display", "count": 6},
                        {"family": "DM Mono", "stack": "DM Mono, monospace", "count": 9},
                    ]
                }
            }
        )
    )
    pile = measure_page(
        _capture(
            census={
                "fonts": {
                    "families": [
                        {"family": name, "stack": name, "count": 3}
                        for name in ("Manrope", "Playfair", "DM Mono", "Arial", "Roboto", "Georgia")
                    ]
                }
            }
        )
    )

    assert not any(f.region == "typography" for f in pairing.findings)
    assert any("pairing rather than a pile" in s for s in pairing.strengths)

    finding = next(f for f in pile.findings if "font families" in f.quote)
    assert f"about {FONT_FAMILY_LIMIT}" in finding.quote
    assert "Roboto" in finding.quote or "Georgia" in finding.quote


def test_one_typeface_declared_in_several_stacks_is_still_one_typeface():
    """The bug the first live capture found, and no fixture here could have.

    `_font_families` splits a family out of each font *stack*, so a page that
    writes `Manrope, sans-serif` in one rule and `Manrope, system-ui` in another
    produces two rows naming one typeface. Counting rows reported Saibyl's own
    landing page as using "7 distinct font families: Manrope, DM Mono, Manrope,
    DM Mono, Playfair Display, Playfair Display, Manrope" — three faces, listed
    seven times, on a page whose pairing is deliberate and correct.

    Every synthetic fixture in this file had unique values in it, which is
    exactly why the defect survived to a live run.
    """
    dimension = measure_page(
        _capture(
            census={
                "fonts": {
                    "families": [
                        {"family": "Manrope", "stack": "Manrope, sans-serif", "count": 30},
                        {"family": "DM Mono", "stack": "DM Mono, monospace", "count": 12},
                        {"family": "Manrope", "stack": "Manrope, system-ui", "count": 9},
                        {"family": "Playfair Display", "stack": "Playfair Display, serif", "count": 6},
                        {"family": "DM Mono", "stack": '"DM Mono", ui-monospace', "count": 4},
                        {"family": "Playfair Display", "stack": "Playfair Display", "count": 2},
                        {"family": "Manrope", "stack": '"Manrope", Arial', "count": 1},
                    ]
                }
            }
        )
    )

    assert not any("font families" in f.quote for f in dimension.findings)
    assert any("3 typefaces" in s for s in dimension.strengths)


def test_shadows_ignore_none_which_is_most_elements_on_any_page():
    values = ["none"] * 8 + ["0 1px 2px rgba(0,0,0,.06)"]
    dimension = measure_page(
        _capture(census={"shape": {"box_shadow": _rows(*values)}})
    )

    assert not any("shadows" in f.quote for f in dimension.findings)


# ── Images ───────────────────────────────────────────────────────────────────

def test_a_page_with_no_images_is_raised_without_being_called_wrong():
    """Typographic pages are a real choice. The finding asks whether it was one,
    rather than asserting a defect."""
    dimension = measure_page(
        _capture(census={"structure": {"headings": {"h1": 1}, "images": 0}})
    )

    finding = next(f for f in dimension.findings if f.quote == "img elements on the page: 0")
    assert "can be deliberate" in finding.why


def test_the_image_check_stays_silent_when_the_census_never_ran():
    """Zero images and no census at all are different facts. Reporting the
    second as the first is the zero-that-means-we-did-not-look defect this
    codebase names as the one it produces most often."""
    dimension = measure_page(_capture(text=_prose(200)))

    assert not any("img elements" in f.quote for f in dimension.findings)


# ── Scoring and shape ────────────────────────────────────────────────────────

def test_every_finding_carries_a_receipt_a_reason_and_something_to_do():
    """The wow standard (PRD_V3 §5): every finding ends in something the founder
    can act on. A measured finding has no excuse for missing any of the three."""
    dimension = measure_page(
        _capture(
            text=_prose(400, dashes=40),
            census={
                "structure": {"headings": {"h1": 0, "h3": 3}, "images": 0},
                "shape": {"border_radius": _rows(*[f"{n}px" for n in range(1, 9)])},
            },
        )
    )

    assert dimension.findings
    for finding in dimension.findings:
        assert finding.quote.strip(), finding
        assert finding.why.strip(), finding
        assert finding.fix.strip(), finding


def test_the_score_falls_as_findings_accumulate_and_never_leaves_the_range():
    clean = measure_page(_capture(text=_prose(500)))
    broken = measure_page(
        _capture(
            text=_prose(400, dashes=60),
            census={
                "structure": {"headings": {"h1": 0, "h3": 4}, "images": 0},
                "shape": {
                    "border_radius": _rows(*[f"{n}px" for n in range(1, 11)]),
                    "box_shadow": _rows(*[f"0 {n}px {n}px rgba(0,0,0,.1)" for n in range(1, 11)]),
                },
                "color": {"text": _rows(*[f"#0000{n:02x}" for n in range(1, 11)])},
                "fonts": {
                    "families": [
                        {"family": f"Face{n}", "stack": f"Face{n}", "count": 2} for n in range(8)
                    ]
                },
            },
        )
    )

    assert clean.score == 100
    assert 0 <= broken.score < 50


def test_the_same_capture_measured_twice_gives_the_same_answer():
    """The property the whole module is for."""
    capture = _capture(
        text=_prose(400, dashes=30),
        census={"structure": {"headings": {"h1": 2}, "images": 0}},
    )

    first = measure_page(capture)
    second = measure_page(capture)

    assert first.model_dump() == second.model_dump()
