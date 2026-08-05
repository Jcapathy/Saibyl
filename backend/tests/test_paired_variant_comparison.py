"""The paired winner test — DECISIONS §16b.

The claim being guarded is narrow and easy to lose: computing the correct
statistic for a within-subject design is **not** the same as lowering the bar.
Both are 95%. One of them matches the design that produced the data.

The numbers in `test_the_aaa_control_run_is_reproduced` are from a real live
run — `7379d04e`, identical copy in all three arenas — and they are here so
that a future change which quietly makes the estimator more eager fails against
measured reality rather than against a hand-made fixture.
"""
from __future__ import annotations

import math

from app.services.intelligence.analysis_schema import Interval, VariantScore
from app.services.intelligence.variant_scoreboard import (
    _MIN_PAIRED_AGENTS,
    _paired_verdict,
    _proportion_interval,
)

# Valence is required on VariantScore and irrelevant to the paired objective
# test — the comparison is on conversion, not sentiment. Held at a neutral
# placeholder so a change in these tests can never be read as a claim about it.
_NEUTRAL = Interval(mean=0.0, lower=0.0, upper=0.0, n=0)


def _score(key: str, hits: int, n: int) -> VariantScore:
    return VariantScore(
        variant_key=key,
        label=key.upper(),
        content="",
        objective_rate=_proportion_interval(hits, n),
        valence=_NEUTRAL,
    )


def _run(top_hits: set[str], second_hits: set[str], agents: set[str]):
    ranked = [
        _score("a", len(top_hits), len(agents)),
        _score("b", len(second_hits), len(agents)),
    ]
    return _paired_verdict(
        ranked,
        {"a": top_hits, "b": second_hits},
        {"a": set(agents), "b": set(agents)},
    )


# ---------------------------------------------------------------------------
# The control: identical behaviour must never produce a winner
# ---------------------------------------------------------------------------

def test_identical_arenas_never_name_a_winner():
    """Every agent behaves the same way in both arenas: no evidence, no winner."""
    agents = {f"agent-{i}" for i in range(40)}
    hits = {f"agent-{i}" for i in range(10)}

    winner, verdict, paired = _run(hits, hits, agents)

    assert winner is None
    assert paired is not None
    assert paired.mean_difference == 0.0
    assert paired.discordant_agents == 0
    assert paired.separates is False


def test_the_aaa_control_run_is_reproduced():
    """The live A/A/A control, replayed. 27 agents, 5 converting in each arena,
    and the flips cancelling exactly — which is what produced three identical
    18.5% rates that looked far too clean to accept without checking.

    8 of 27 agents were discordant between arenas a and b. A rule that named a
    winner here would be telling a founder to spend money on nothing.
    """
    agents = {f"a{i}" for i in range(27)}
    # 5 convert in each, with 8 discordant and the difference summing to zero:
    # 1 shared converter, 4 unique to each side.
    top = {"a0", "a1", "a2", "a3", "a4"}
    second = {"a0", "a5", "a6", "a7", "a8"}

    winner, verdict, paired = _run(top, second, agents)

    assert winner is None, "the A/A/A control must not name a winner"
    assert paired is not None
    assert paired.mean_difference == 0.0
    assert paired.discordant_agents == 8
    assert paired.lower < 0 < paired.upper


# ---------------------------------------------------------------------------
# It must still be able to find something
# ---------------------------------------------------------------------------

def test_a_large_consistent_difference_is_named():
    """A rule that never fires is not conservative, it is not a test.

    Every agent that converts on the runner-up also converts on the leader,
    plus 20 more — the unambiguous case.
    """
    agents = {f"a{i}" for i in range(60)}
    second = {f"a{i}" for i in range(10)}
    top = {f"a{i}" for i in range(30)}

    winner, verdict, paired = _run(top, second, agents)

    assert winner == "a"
    assert paired is not None and paired.separates is True
    assert "leads" in verdict


def test_a_difference_inside_the_noise_refuses_and_says_what_it_would_take():
    """The refusal is the product, and it should be actionable.

    Required n scales as 1/delta^2, so the verdict can state a real number
    instead of "more agents".
    """
    agents = {f"a{i}" for i in range(30)}
    second = {"a0", "a1", "a2"}
    top = {"a0", "a1", "a2", "a3", "a4"}

    winner, verdict, paired = _run(top, second, agents)

    assert winner is None
    assert paired is not None and paired.separates is False
    assert "agents would resolve" in verdict


# ---------------------------------------------------------------------------
# Failing safe is the whole reason this is allowed to be more powerful
# ---------------------------------------------------------------------------

def test_an_unpaired_run_produces_no_paired_comparison():
    """Pairing is only valid while arenas share a swarm.

    If they ever stop, the paired estimator is not conservative — it is wrong,
    because its interval assumes a correlation that no longer exists. It must
    decline rather than narrow.
    """
    ranked = [_score("a", 20, 30), _score("b", 5, 30)]
    winner, verdict, paired = _paired_verdict(
        ranked,
        {"a": {f"x{i}" for i in range(20)}, "b": {f"y{i}" for i in range(5)}},
        # Disjoint swarms: no agent appears in both arenas.
        {"a": {f"x{i}" for i in range(30)}, "b": {f"y{i}" for i in range(30)}},
    )

    assert paired is None, "disjoint swarms must not yield a paired comparison"
    assert winner is None


def test_a_tiny_shared_swarm_declines_rather_than_reporting_precision():
    agents = {f"a{i}" for i in range(_MIN_PAIRED_AGENTS - 1)}
    winner, verdict, paired = _run({"a0"}, set(), agents)

    assert paired is None
    assert winner is None


def test_a_single_variant_is_not_a_comparison():
    winner, verdict, paired = _paired_verdict([_score("a", 5, 20)], {}, {})
    assert (winner, verdict, paired) == (None, "", None)


# ---------------------------------------------------------------------------
# The bar did not move
# ---------------------------------------------------------------------------

def test_the_interval_is_a_two_sided_95_percent_band():
    """Same standard as the unpaired rule, applied to the paired design.

    Recomputed here from the definition rather than asserted against a stored
    number, so a change to the estimator's internals cannot quietly widen the
    z-value.
    """
    agents = {f"a{i}" for i in range(50)}
    second = {f"a{i}" for i in range(8)}
    top = {f"a{i}" for i in range(20)}

    _, _, paired = _run(top, second, agents)
    assert paired is not None

    diffs = [
        (1 if a in top else 0) - (1 if a in second else 0) for a in sorted(agents)
    ]
    n = len(diffs)
    mean_d = sum(diffs) / n
    var = sum((d - mean_d) ** 2 for d in diffs) / (n - 1)
    margin = 1.96 * math.sqrt(var / n)

    assert paired.mean_difference == round(mean_d, 4)
    assert paired.lower == round(mean_d - margin, 4)
    assert paired.upper == round(mean_d + margin, 4)


def test_the_schema_mirror_moved_with_the_bump():
    """A bump without the frontend mirror blanks every report in the product."""
    from pathlib import Path

    from app.services.intelligence.analysis_schema import SCHEMA_VERSION

    mirror = (
        Path(__file__).resolve().parents[2]
        / "frontend" / "src" / "lib" / "analysis.ts"
    )
    if not mirror.exists():
        return
    text = mirror.read_text(encoding="utf-8")
    assert f"SUPPORTED_SCHEMA_VERSION = {SCHEMA_VERSION}" in text, (
        f"backend SCHEMA_VERSION is {SCHEMA_VERSION} but the frontend mirror "
        "does not match — the viewer refuses unknown versions, so every report "
        "would render blank."
    )
