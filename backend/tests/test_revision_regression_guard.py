"""A higher mean may not be bought by giving a dimension up.

**The case these exist for, verbatim from the record.** On 2026-08-27 a
revision of saibyl.com took `measured` from 35 to 73 by deleting things while
`design` — a model actually looking at the page — fell from 95 to 72. The mean
rose 5, the loop declared a win, and the founder was handed a page he described
as having "not really much to it".

`taste.py` closed the half of that defect that was a gameable rubric. This
closes the other half: the arithmetic that let the trade look like a win. With
nine dimensions each is about a ninth of the mean, so the trade got cheaper
rather than dearer.
"""
from __future__ import annotations

from app.services.website.capture import WebsiteCapture
from app.services.website.claims import UnsupportedClaim
from app.services.website.critics import CriticDimension, CritiqueResult
from app.services.website.revise import (
    DIMENSION_REGRESSION_LIMIT,
    _is_better,
    _regressions,
    _Round,
)

ORIGINAL = {
    "overall": 75,
    "hierarchy": 80,
    "design": 95,
    "measured": 35,
    "standard": 60,
}


def _render() -> WebsiteCapture:
    """The rendered revision. Never read by the ranking, but the model wants one."""
    return WebsiteCapture(
        url="https://example.com",
        final_url="https://example.com",
        title="A page",
        dom_text="words",
        meta={},
        screenshot_desktop=b"png",
        screenshot_mobile=b"png",
    )


def _round(number: int, overall: int, regressions=None) -> _Round:
    """A judged round. `html` and `render` are never read by the ranking."""
    return _Round(
        number=number,
        html="<html></html>",
        render=_render(),
        verdict=CritiqueResult(
            overall_score=overall,
            page_takeaway="a takeaway",
            dimensions=[CriticDimension(key="design", score=overall, findings=[], strengths=[])],
        ),
        claims=[],
        regressions=regressions or [],
    )


# ── what counts as giving a dimension up ────────────────────────────────────


def test_the_2026_08_27_trade_is_recognised_as_a_regression():
    """`design` 95 -> 72 is -23. The limit is 20, the largest drift ever
    measured on an unchanged page, so this clears it and noise never does."""
    given_up = _regressions({"design": 72, "measured": 73, "hierarchy": 80}, ORIGINAL)

    assert given_up == [("design", 23)]


def test_a_fall_inside_the_measured_noise_band_is_not_a_regression():
    """Vision dimensions moved 4-20 points across a model change and an effort
    change with nothing on the page to cause it. Blocking on that would block
    every revision."""
    given_up = _regressions({"design": 95 - DIMENSION_REGRESSION_LIMIT}, ORIGINAL)

    assert given_up == []


def test_a_dimension_that_rose_is_never_a_regression():
    assert _regressions({"measured": 90, "design": 95}, ORIGINAL) == []


def test_a_dimension_absent_from_the_revision_is_skipped_not_read_as_zero():
    """`measured`, `standard` and `found` each return None when there was
    nothing to judge. Reading that absence as a fall to zero would block every
    revision of a page that defeats measurement."""
    assert _regressions({"design": 95}, ORIGINAL) == []


def test_the_overall_is_not_itself_a_dimension():
    """It is the mean of the others. Counting it would double-weight whichever
    dimensions moved."""
    assert _regressions({"overall": 10, "design": 95}, ORIGINAL) == []


def test_the_worst_regression_is_reported_first():
    given_up = _regressions({"design": 40, "hierarchy": 50, "standard": 20}, ORIGINAL)

    assert [key for key, _ in given_up] == ["design", "standard", "hierarchy"]
    assert [drop for _, drop in given_up] == [55, 40, 30]


# ── how the ranking uses it ─────────────────────────────────────────────────


def test_a_round_that_holds_everything_beats_one_that_scores_higher_by_giving_up():
    """The whole point. The higher mean does not win."""
    holds = _round(2, overall=72)
    trades = _round(1, overall=80, regressions=[("design", 23)])

    assert _is_better(holds, trades) is True
    assert _is_better(trades, holds) is False


def test_among_rounds_that_hold_everything_the_score_still_decides():
    assert _is_better(_round(2, overall=80), _round(1, overall=72)) is True
    assert _is_better(_round(2, overall=70), _round(1, overall=72)) is False


def test_fewer_regressions_wins_even_when_both_rounds_gave_something_up():
    one = _round(1, overall=90, regressions=[("design", 23), ("copy", 25)])
    two = _round(2, overall=60, regressions=[("design", 23)])

    assert _is_better(two, one) is True


def test_an_invented_certification_still_outranks_everything_below_it():
    """The tiers are ordered. A round that fabricates nothing wins even if it
    gave a dimension up and scored lower."""
    honest = _Round(
        number=2,
        html="<html></html>",
        render=_render(),
        verdict=CritiqueResult(overall_score=50, page_takeaway="t", dimensions=[]),
        claims=[],
        regressions=[("design", 30)],
    )
    fabricating = _Round(
        number=1,
        html="<html></html>",
        render=_render(),
        verdict=CritiqueResult(overall_score=95, page_takeaway="t", dimensions=[]),
        claims=[
            UnsupportedClaim(kind="certification", text="SOC 2", quote="We are SOC 2 certified.")
        ],
        regressions=[],
    )

    assert _is_better(honest, fabricating) is True


def test_the_first_round_is_always_taken_so_the_loop_has_a_result():
    """A first round that regresses is still reported, with the regression
    recorded. The guard stops a *later* round from winning by giving up, it
    does not leave the founder with nothing."""
    assert _is_better(_round(1, overall=40, regressions=[("design", 40)]), None) is True
