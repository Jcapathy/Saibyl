"""Tests for the statistics behind every rendered number.

These guard the two claims Phase 1 makes to customers: that confidence comes
from the agent count, and that a figure with nothing behind it is reported as
absent rather than as zero.
"""
from __future__ import annotations

from app.services.intelligence.analysis_data import (
    MeasuredEvent,
    mean_intensity,
    mean_interval,
    stance_split,
)


def _event(
    event_id: str,
    agent: str,
    valence: float | None,
    stance: str | None = "support",
    intensity: float = 0.5,
) -> MeasuredEvent:
    return MeasuredEvent(
        id=event_id,
        agent_id=agent,
        agent_username=agent,
        archetype="Tester",
        platform="twitter_x",
        round_number=1,
        event_type="post",
        content="text",
        valence=valence,
        stance=stance,
        intensity=intensity,
        intent="none",
        is_novel_claim=False,
        objections=[],
    )


def test_empty_input_reports_zero_n_not_a_number():
    interval = mean_interval([])
    assert interval.n == 0
    assert interval.mean == 0.0


def test_single_agent_spans_the_full_scale():
    """One observation cannot support a narrow band, however many posts it made."""
    events = [_event(f"e{i}", "agent-1", 0.8) for i in range(10)]
    interval = mean_interval(events)
    assert interval.n == 1
    assert (interval.lower, interval.upper) == (-1.0, 1.0)


def test_interval_is_clustered_by_agent_not_by_event():
    """Ten posts from two agents is n=2, not n=10.

    This is the whole point: treating repeated posts as independent
    observations would shrink the band by roughly sqrt(5) and manufacture
    precision out of one agent's verbosity.
    """
    chatty = [_event(f"a{i}", "agent-1", 0.9) for i in range(9)]
    quiet = [_event("b0", "agent-2", -0.9)]
    interval = mean_interval(chatty + quiet)

    assert interval.n == 2
    # Each agent contributes its own mean equally, so the run mean is 0.0 —
    # not 0.72, which is what event-weighting would produce.
    assert abs(interval.mean) < 1e-9


def test_more_agents_narrows_the_band():
    small = mean_interval([_event(f"s{i}", f"agent-{i}", 0.4 + 0.1 * (i % 3)) for i in range(5)])
    large = mean_interval([_event(f"l{i}", f"agent-{i}", 0.4 + 0.1 * (i % 3)) for i in range(50)])
    assert large.upper - large.lower < small.upper - small.lower


def test_unscored_and_off_topic_events_are_excluded_from_the_mean():
    events = [
        _event("e1", "agent-1", 0.8),
        _event("e2", "agent-2", None, stance=None),        # a reaction
        _event("e3", "agent-3", -0.9, stance="off_topic"),  # not about the subject
    ]
    interval = mean_interval(events)
    assert interval.n == 1
    assert interval.mean == 0.8


def test_interval_never_exceeds_the_valence_scale():
    events = [_event(f"e{i}", f"agent-{i}", 0.99) for i in range(3)]
    interval = mean_interval(events)
    assert interval.lower >= -1.0
    assert interval.upper <= 1.0


def test_stance_split_counts_off_topic_but_sums_to_100():
    events = [
        _event("e1", "a1", 0.5, stance="support"),
        _event("e2", "a2", -0.5, stance="oppose"),
        _event("e3", "a3", 0.0, stance="undecided"),
        _event("e4", "a4", 0.0, stance="off_topic"),
    ]
    split = stance_split(events)
    total = (
        split.support_pct + split.oppose_pct
        + split.undecided_pct + split.off_topic_pct
    )
    assert abs(total - 100.0) < 0.01
    assert split.support_pct == 25.0


def test_stance_split_of_nothing_is_all_zero():
    split = stance_split([_event("e1", "a1", None, stance=None)])
    assert split.support_pct == 0.0
    assert split.oppose_pct == 0.0


def test_mean_intensity_ignores_missing_values():
    events = [_event("e1", "a1", 0.5, intensity=0.4), _event("e2", "a2", 0.5, intensity=0.6)]
    events.append(_event("e3", "a3", None, stance=None))
    events[-1].intensity = None
    assert mean_intensity(events) == 0.5
