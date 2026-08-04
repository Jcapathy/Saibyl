"""The scoreboard as the report writer sees it.

Phase 1's bug #5 was the report writing its own numbers. The Marketing-lens
shape of that bug is subtler and worse: the writer does not invent a figure, it
invents a *conclusion*. Handed six ranked rows with no instruction, a model
describes the top one as the winner — because that is what a ranked list reads
like — and the entire reason for computing intervals is that an ordering drawn
from overlapping bands is not a result.
"""
from __future__ import annotations

from app.services.intelligence.report_agent import build_lens_context


def _board(winner=None, verdict="", variants=None):
    # `is None`, not `or` — an empty list is a case under test here, and `or`
    # would quietly substitute the default for it.
    if variants is None:
        variants = [
            {
                "variant_key": "a",
                "label": "Bold",
                "objective_rate": {"mean": 0.31, "lower": 0.2, "upper": 0.42, "n": 40},
                "virality": {"score": 71.0},
            },
            {
                "variant_key": "b",
                "label": "Safe",
                "objective_rate": {"mean": 0.27, "lower": 0.17, "upper": 0.37, "n": 40},
                "virality": {"score": 44.0},
            },
        ]
    return {
        "objective": "clicks",
        "winner_variant_key": winner,
        "verdict": verdict,
        "variants": variants,
    }


def test_no_winner_is_a_prohibition_not_a_hint():
    context = build_lens_context({}, {"scoreboard": _board()})

    assert "NO WINNER IS SUPPORTED" in context
    assert "MUST NOT name a winner" in context
    assert "not separate them" in context


def test_a_supported_winner_may_be_stated():
    context = build_lens_context({}, {"scoreboard": _board(winner="a")})

    assert "A winner IS supported" in context
    assert "MUST NOT name a winner" not in context


def test_virality_is_kept_on_its_own_axis():
    context = build_lens_context({}, {"scoreboard": _board()})

    assert "SEPARATE axis" in context
    assert "Never blend them" in context


def test_unmeasured_components_must_not_be_narrated_as_zero():
    context = build_lens_context({}, {"scoreboard": _board()})
    assert "do not describe it as zero" in context


def test_pooled_sentiment_must_not_be_attributed_to_a_variant():
    context = build_lens_context({}, {"scoreboard": _board()})
    assert "pool every arena" in context


def test_the_flags_reach_the_writer():
    board = _board()
    board["variants"][0]["viral_but_off_message"] = True
    board["variants"][1]["converts_but_wont_travel"] = True

    context = build_lens_context({}, {"scoreboard": board})

    assert "VIRAL BUT OFF-MESSAGE" in context
    assert "CONVERTS BUT WON'T TRAVEL" in context


def test_intervals_and_agent_counts_are_given_not_just_means():
    """A writer handed only means will compare them as though they were exact."""
    context = build_lens_context({}, {"scoreboard": _board()})

    assert "95% CI" in context
    assert "n=40 agents" in context


def test_a_single_arena_run_gets_no_scoreboard_block():
    assert "VARIANT SCOREBOARD" not in build_lens_context({}, {"scoreboard": None})
    assert "VARIANT SCOREBOARD" not in build_lens_context({}, {})
    assert build_lens_context({}, None) == ""


def test_an_empty_variant_list_is_not_rendered():
    context = build_lens_context({}, {"scoreboard": _board(variants=[])})
    assert "VARIANT SCOREBOARD" not in context
