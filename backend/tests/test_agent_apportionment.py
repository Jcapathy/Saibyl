"""`run_prepare_agents` must build exactly the swarm the customer paid for.

Credits are charged **at start**, from the agent count the customer selected
(HANDOFF §4.3) — otherwise one balance funds ten concurrent runs. So a run that
allocates fewer agents than were requested has already taken the money for a
swarm it will not build, and nothing downstream notices: the run completes, the
report renders, and the only trace is a smaller `n` behind every confidence
interval in the artifact.

The old arithmetic did exactly that. `max(1, round(weight / total_weight * n))`
per archetype, against a `remaining` counter that truncated whatever was left,
allocated **45 agents for a 48-agent run** at three buyer archetypes and a
four-strong incumbent cohort; the same shape at 30 agents realised a 20%
adversarial cohort against 30% configured, 10 percentage points out on a single
pack. `apportion` is largest-remainder (Hamilton) and the properties below are
what that buys.

These are property sweeps rather than a handful of examples on purpose: the
defect was invisible at the shape the product was demoed on (96 agents, 30%,
which happened to land on 96) and appeared two configurations over.
"""
from __future__ import annotations

import random

import pytest
import structlog
from structlog.testing import capture_logs

from app.workers import simulation_tasks
from app.workers.simulation_tasks import apportion


@pytest.fixture
def capturable_logger(monkeypatch):
    """Make `capture_logs` able to see the module logger, in any test order.

    `setup_logging()` configures a **new** processors list and `create_app()`
    calls it every time; `capture_logs` mutates whichever list is current *in
    place*. With `cache_logger_on_first_use=True`, a module logger first used
    before the last `create_app()` stays bound to the previous list — it still
    logs, and `capture_logs` still returns `[]`. Binding a fresh proxy inside
    the test removes the order dependency.
    """
    monkeypatch.setattr(
        simulation_tasks, "logger", structlog.get_logger("app.workers.simulation_tasks")
    )

# Enough shapes to cross every rounding boundary, small enough to stay fast.
_TOTALS = [0, 1, 2, 3, 5, 7, 12, 25, 26, 30, 48, 96, 97, 100, 150, 200, 201, 999]
_WEIGHT_SETS = [
    [1.0],
    [1.0, 1.0],
    [0.5, 0.5],
    [0.4, 0.35, 0.25],
    [0.28, 0.245, 0.175, 0.15, 0.15],  # the live Founder-lens shape
    [0.7, 0.1, 0.1, 0.1],
    [0.9, 0.05, 0.03, 0.02],
    [1.0] * 7,
    [1.0] * 12,
    [0.001, 0.999],
    [1e-6, 1.0, 1.0],
    [3.0, 2.0, 1.0, 1.0, 1.0, 1.0],
]


def _random_weights(rng: random.Random, n: int) -> list[float]:
    return [rng.choice([rng.random(), rng.random() * 0.01, rng.uniform(1, 50)]) for _ in range(n)]


# ---------------------------------------------------------------------------
# The invariant that is money
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("total", _TOTALS)
@pytest.mark.parametrize("weights", _WEIGHT_SETS)
def test_the_allocated_total_equals_the_requested_total(weights, total):
    assert sum(apportion(weights, total)) == total


def test_the_allocated_total_equals_the_requested_total_on_random_shapes():
    """A seeded sweep, so a failure is reproducible rather than flaky."""
    rng = random.Random(20260804)
    for _ in range(3000):
        n = rng.randint(1, 14)
        total = rng.randint(0, 400)
        weights = _random_weights(rng, n)
        counts = apportion(weights, total)
        assert sum(counts) == total, (weights, total, counts)
        assert all(c >= 0 for c in counts)


def test_the_two_stage_split_across_platforms_and_archetypes_is_also_exact():
    """`run_prepare_agents` apportions twice — platforms, then archetypes.

    Two exact splits compose into an exact split only because the first one is
    exact. The old code took `max(1, target // len(platforms))` and multiplied
    it back up, so 30 agents over four platforms was 28 before an archetype was
    considered — and 2 agents over four platforms was 4.
    """
    for total in _TOTALS:
        for platforms in (1, 2, 3, 4, 5):
            for weights in _WEIGHT_SETS:
                allocated = sum(
                    sum(apportion(weights, per_platform))
                    for per_platform in apportion([1.0] * platforms, total)
                )
                assert allocated == total, (total, platforms, weights)


def test_the_reported_48_agent_case():
    """Three buyers and a four-strong cohort at 30%, the reported shape.

    Before: 45. The three missing agents were charged for.
    """
    weights = [0.7 / 3] * 3 + [0.3 / 4] * 4
    counts = apportion(weights, 48)
    assert sum(counts) == 48
    assert sum(counts[3:]) == 15, counts  # 31.25% of 48 — the nearest whole share


# ---------------------------------------------------------------------------
# `max(1, …)`'s intent, without spending the total on it
# ---------------------------------------------------------------------------

def test_no_archetype_with_weight_vanishes_when_there_are_seats_for_all():
    rng = random.Random(4242)
    for _ in range(2000):
        n = rng.randint(1, 10)
        weights = _random_weights(rng, n)
        total = rng.randint(n, n + 200)
        counts = apportion(weights, total)
        assert all(c >= 1 for c in counts), (weights, total, counts)
        assert sum(counts) == total


def test_a_tiny_weight_still_gets_an_agent():
    """0.1% of the audience in a 96-agent swarm rounds to nothing on its own.

    An archetype the founder confirmed is in their audience, contributing zero
    agents, is a cohort missing from every number in the report.
    """
    counts = apportion([0.999, 0.001], 96)
    assert counts == [95, 1]


def test_the_seat_a_starved_archetype_gets_is_taken_not_added():
    """The old `max(1, …)` added the seat, which is where the total drifted."""
    weights = [0.999, 0.0005, 0.0005]
    counts = apportion(weights, 10)
    assert sum(counts) == 10
    assert counts == [8, 1, 1]


def test_more_archetypes_than_agents_keeps_the_total_and_drops_the_smallest():
    """The requested count is the promise; an archetype's presence is not.

    The old code allocated one agent per archetype regardless, so a 3-agent run
    across 8 archetypes built 8 agents — over-delivering against a charge, which
    is the same defect with its sign flipped.
    """
    counts = apportion([8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0], 3)
    assert sum(counts) == 3
    assert counts[:3] == [1, 1, 1]
    assert counts[3:] == [0] * 5


def test_a_zero_weight_archetype_gets_nothing():
    """`weight` is `gt=0` in the schema, so this is the defensive edge only."""
    counts = apportion([1.0, 0.0, 1.0], 10)
    assert counts == [5, 0, 5]


# ---------------------------------------------------------------------------
# Determinism and the degenerate edges
# ---------------------------------------------------------------------------

def test_the_allocation_is_a_function_of_its_inputs():
    """Two runs of one configuration must not produce two audiences."""
    weights = [0.25, 0.25, 0.25, 0.25]
    assert apportion(weights, 30) == apportion(list(weights), 30)
    assert apportion(weights, 30) == [8, 8, 7, 7]


def test_equal_weights_differ_by_at_most_one_agent():
    for total in _TOTALS:
        for n in (2, 3, 4, 5, 7, 11):
            counts = apportion([1.0] * n, total)
            assert sum(counts) == total
            if total >= n:
                assert max(counts) - min(counts) <= 1, (total, n, counts)


@pytest.mark.parametrize("total", [0, -1, -50])
def test_a_non_positive_total_allocates_nothing(total):
    assert apportion([1.0, 2.0], total) == [0, 0]


def test_an_empty_weight_list_is_empty():
    assert apportion([], 30) == []


def test_all_weights_zero_is_reported_not_silently_starved(capturable_logger):
    """A silent `[0, 0, 0]` here is a run that charges and builds nothing.

    structlog is not bound to stdlib logging outside `create_app`, so this uses
    `capture_logs` — a `caplog` assertion would pass without the log existing.
    """
    with capture_logs() as logs:
        counts = apportion([0.0, 0.0, 0.0], 9)

    assert sum(counts) == 9
    assert counts == [3, 3, 3]
    assert any(entry["event"] == "apportion_no_positive_weights" for entry in logs)


def test_the_realised_share_of_a_sub_group_tracks_its_configured_share():
    """The adversarial cohort is a weight sub-group, and this is its accuracy.

    Asserted as a bound over a sweep rather than at one shape, because the live
    30-of-96 figure the product quotes was measured at one shape and the old
    apportionment was 10 points out two configurations away from it.
    """
    worst = 0.0
    for buyers in (1, 2, 3, 4, 6):
        for cohort in (1, 2, 3, 4):
            for share in (0.1, 0.2, 0.3, 0.4, 0.5):
                for agents in (30, 48, 96, 150, 200):
                    weights = [(1 - share) / buyers] * buyers + [share / cohort] * cohort
                    counts = apportion(weights, agents)
                    assert sum(counts) == agents
                    worst = max(worst, abs(sum(counts[buyers:]) / agents - share))

    # Measured at 0.0333 over this sweep; 0.1000 under the old apportionment.
    assert worst <= 0.034, worst
