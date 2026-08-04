"""The N-way scoreboard, and the refusals that make it a measurement.

The scoreboard's value is that it can decline to name a winner. A marketer acts
on the top row, so an ordering drawn from overlapping confidence bands launders
sampling noise into a spend decision — which is the same failure the inoculation
loop's `unresolved` verdict exists to prevent, and it is the thing most likely
to be "improved" away by someone who finds a blank winner unsatisfying.
"""
from __future__ import annotations

from app.services.engine.variants import Arena
from app.services.intelligence.analysis_data import MeasuredEvent, RunData
from app.services.intelligence.variant_scoreboard import (
    build_scoreboard,
    objective_intents,
)


def _event(
    idx: int,
    variant: str,
    agent: str,
    *,
    intent: str | None = None,
    archetype: str = "Buyer",
    platform: str = "reddit",
    round_number: int = 1,
    takeaway: str | None = None,
    target: str | None = None,
    valence: float | None = 0.2,
) -> MeasuredEvent:
    return MeasuredEvent(
        id=f"e{idx}",
        agent_id=agent,
        agent_username=agent,
        archetype=archetype,
        platform=platform,
        round_number=round_number,
        event_type="post",
        content="something about the offer",
        valence=valence,
        stance="support",
        intensity=0.5,
        intent=intent,
        is_novel_claim=False,
        objections=[],
        variant=variant,
        target_event_id=target,
        takeaway=takeaway,
    )


def _run(events, arenas, *, objective="clicks", archetypes=("Buyer",), platforms=("reddit",)):
    return RunData(
        simulation_id="sim",
        organization_id="org",
        prediction_goal="Our launch",
        max_rounds=5,
        events=events,
        agents_total=len({e.agent_id for e in events}) or 1,
        archetypes=list(archetypes),
        platforms=list(platforms),
        events_total=len(events),
        events_measured=len(events),
        objective=objective,
        arenas=arenas,
    )


_TWO = [
    Arena(variant_key="a", label="Bold", content="Ship faster with zero setup"),
    Arena(variant_key="b", label="Safe", content="Reliable tooling for teams"),
]


# ── The refusal ──────────────────────────────────────────

def test_no_winner_when_the_top_two_intervals_overlap():
    """The rule the scoreboard exists to honour."""
    events = [_event(i, "a", f"a{i}", intent="click") for i in range(3)]
    events += [_event(10 + i, "a", f"a{10 + i}") for i in range(3)]
    events += [_event(20 + i, "b", f"b{i}", intent="click") for i in range(2)]
    events += [_event(30 + i, "b", f"b{30 + i}") for i in range(4)]

    board = build_scoreboard(_run(events, _TWO))

    assert board.winner_variant_key is None
    assert "No winner" in board.verdict
    assert "not a ranking" in board.verdict


def test_a_winner_is_named_when_the_intervals_separate():
    # Every agent converts on A, none on B, with enough agents to separate.
    events = [_event(i, "a", f"a{i}", intent="click") for i in range(30)]
    events += [_event(100 + i, "b", f"b{i}") for i in range(30)]

    board = build_scoreboard(_run(events, _TWO))

    assert board.winner_variant_key == "a"
    assert "leads" in board.verdict


def test_the_ordering_is_by_the_objective_not_by_sentiment():
    """Sentiment is demoted to a supporting metric (DECISIONS §6)."""
    # B is loved and converts nobody; A is disliked and converts everyone.
    events = [_event(i, "a", f"a{i}", intent="click", valence=-0.6) for i in range(20)]
    events += [_event(100 + i, "b", f"b{i}", valence=0.9) for i in range(20)]

    board = build_scoreboard(_run(events, _TWO))

    assert [v.variant_key for v in board.variants] == ["a", "b"]
    assert board.variants[0].valence.mean < board.variants[1].valence.mean


def test_a_single_arena_run_gets_no_scoreboard():
    """One variant is not a comparison, and a one-row board invites a reader to
    treat it as one."""
    events = [_event(i, "a", f"a{i}", intent="click") for i in range(5)]
    one = [Arena(variant_key="a", label="Only", content="x")]

    assert build_scoreboard(_run(events, one)) is None
    assert build_scoreboard(_run(events, [])) is None


def test_an_arena_that_produced_nothing_still_appears():
    """A variant nobody engaged with is a finding, not an absence."""
    events = [_event(i, "a", f"a{i}", intent="click") for i in range(5)]

    board = build_scoreboard(_run(events, _TWO))

    keys = [v.variant_key for v in board.variants]
    assert "b" in keys
    silent = next(v for v in board.variants if v.variant_key == "b")
    assert silent.event_count == 0 and silent.agent_count == 0


# ── Objectives ───────────────────────────────────────────

def test_each_objective_counts_its_own_intent():
    assert objective_intents("clicks") == ("click",)
    assert objective_intents("foot_traffic") == ("visit",)
    assert objective_intents("product_sale") == ("purchase",)
    assert "trial" in objective_intents("signup")


def test_an_unset_objective_falls_back_to_any_committing_intent():
    intents = objective_intents(None)
    assert "purchase" in intents and "click" in intents
    # "share" is virality, not conversion, and must not be counted as one.
    assert "share" not in intents
    assert "none" not in intents and "abandon" not in intents


def test_the_objective_rate_counts_agents_not_events():
    """One agent posting six times is one conversion, not six."""
    loud = [_event(i, "a", "same-agent", intent="click") for i in range(6)]
    loud += [_event(50 + i, "b", f"b{i}") for i in range(6)]

    board = build_scoreboard(_run(loud, _TWO))
    winner = next(v for v in board.variants if v.variant_key == "a")

    assert winner.objective_rate.n == 1
    assert winner.event_count == 6


# ── Virality ─────────────────────────────────────────────

def test_zero_observed_share_intent_reports_a_band_not_a_confident_zero():
    events = [_event(i, "a", f"a{i}") for i in range(40)]
    events += [_event(100 + i, "b", f"b{i}") for i in range(40)]

    board = build_scoreboard(_run(events, _TWO))
    arena = board.variants[0]

    assert arena.virality.share_intent_rate.mean == 0.0
    assert arena.virality.share_intent_rate.upper > 0.0  # rule of three


def test_unmeasurable_components_are_none_and_do_not_count_as_zero():
    """A gap in instrumentation must not read as a variant that failed."""
    events = [_event(i, "a", f"a{i}", intent="click") for i in range(5)]
    events += [_event(100 + i, "b", f"b{i}") for i in range(5)]

    board = build_scoreboard(_run(events, _TWO))  # one platform, no takeaways
    arena = board.variants[0]

    assert arena.virality.cross_platform_jump is None
    assert arena.virality.restatement_rate is None
    assert arena.virality.cascade_branching is None
    assert arena.virality.components_used < arena.virality.components_total


def test_cross_platform_jump_is_measured_when_there_are_two_platforms():
    events = [
        _event(0, "a", "a1", platform="reddit"),
        _event(1, "a", "a1", platform="linkedin"),
        _event(2, "a", "a2", platform="reddit"),
        _event(3, "b", "b1", platform="reddit"),
    ]
    board = build_scoreboard(
        _run(events, _TWO, platforms=("reddit", "linkedin"))
    )
    arena = next(v for v in board.variants if v.variant_key == "a")

    assert arena.virality.cross_platform_jump == 0.5


def test_cross_archetype_reach_is_the_heaviest_component():
    from app.services.intelligence.variant_scoreboard import _VIRALITY_WEIGHTS

    assert _VIRALITY_WEIGHTS["cross_archetype_reach"] == max(
        _VIRALITY_WEIGHTS.values()
    )
    assert abs(sum(_VIRALITY_WEIGHTS.values()) - 1.0) < 1e-9


def test_cascade_is_branching_and_is_measured_from_the_graph():
    events = [
        _event(0, "a", "a1"),
        _event(1, "a", "a2", target="e0"),
        _event(2, "a", "a3", target="e0"),
        _event(3, "b", "b1"),
    ]
    board = build_scoreboard(_run(events, _TWO))
    arena = next(v for v in board.variants if v.variant_key == "a")

    assert arena.virality.cascade_branching == 2.0


# ── The two derived flags ────────────────────────────────

_THREE = [
    Arena(variant_key="a", label="Bold", content="Ship faster with zero setup"),
    Arena(variant_key="b", label="Safe", content="Reliable tooling for teams"),
    Arena(variant_key="c", label="Cheap", content="Affordable pricing for startups"),
]


def _spreading(idx_base: int, key: str, takeaway: str, n: int = 12):
    """Agents that spread the message, across cohorts and platforms."""
    return [
        _event(
            idx_base + i, key, f"{key}{i}",
            intent="share",
            archetype=("Buyer" if i % 2 else "Skeptic"),
            platform=("reddit" if i % 2 else "linkedin"),
            takeaway=takeaway,
        )
        for i in range(n)
    ]


def test_off_message_is_relative_to_the_other_variants():
    """One variant understood far worse than its peers is the actionable case.

    The absolute threshold this replaced (0.25) fired on two of three variants
    on the first live run, where the measured accuracies were 0.07, 0.07 and
    0.14 — a flag that fires on almost everything is noise wearing the clothes
    of a finding. Lexical overlap between a twelve-word paraphrase and a
    marketing sentence is inherently low; there is no absolute level at which it
    means off-message.
    """
    events = (
        _spreading(0, "a", "completely unrelated aquarium maintenance advice")
        + _spreading(100, "b", "reliable tooling built for teams")
        + _spreading(200, "c", "affordable pricing aimed at startups")
    )
    board = build_scoreboard(
        _run(events, _THREE, archetypes=("Buyer", "Skeptic"),
             platforms=("reddit", "linkedin"))
    )
    by_key = {v.variant_key: v for v in board.variants}

    assert by_key["a"].viral_but_off_message
    assert not by_key["b"].viral_but_off_message
    assert not by_key["c"].viral_but_off_message


def test_nothing_is_flagged_when_the_variants_sit_together():
    """The first live run's actual shape: all three similar, none separable.

    Silence here is the honest reading of "this metric did not separate them".
    """
    events = (
        _spreading(0, "a", "ship faster with zero setup")
        + _spreading(100, "b", "reliable tooling built for teams")
        + _spreading(200, "c", "affordable pricing aimed at startups")
    )
    board = build_scoreboard(
        _run(events, _THREE, archetypes=("Buyer", "Skeptic"),
             platforms=("reddit", "linkedin"))
    )

    assert not any(v.viral_but_off_message for v in board.variants)


def test_two_variants_are_never_flagged_off_message():
    """With two arenas, 'worse than the other' is a coin-flip dressed as a finding."""
    events = (
        _spreading(0, "a", "completely unrelated aquarium maintenance advice")
        + _spreading(100, "b", "reliable tooling built for teams")
    )
    board = build_scoreboard(
        _run(events, _TWO, archetypes=("Buyer", "Skeptic"),
             platforms=("reddit", "linkedin"))
    )

    assert not any(v.viral_but_off_message for v in board.variants)


def test_thresholds_are_published_in_the_artifact():
    """A reader must be able to disagree with them without reading the source."""
    events = [_event(i, "a", f"a{i}") for i in range(4)]
    board = build_scoreboard(_run(events, _TWO))

    assert board.viral_score_threshold > 0
    assert board.off_message_threshold > 0
    assert board.objective == "clicks"
    assert board.objective_intents == ["click"]


# ── Per-archetype ────────────────────────────────────────

def test_per_archetype_breakdown_shows_who_a_variant_wins_and_loses():
    events = [
        _event(0, "a", "buyer1", intent="click", archetype="Buyer"),
        _event(1, "a", "buyer2", intent="click", archetype="Buyer"),
        _event(2, "a", "skeptic1", archetype="Skeptic"),
        _event(3, "b", "buyer1", archetype="Buyer"),
    ]
    board = build_scoreboard(
        _run(events, _TWO, archetypes=("Buyer", "Skeptic"))
    )
    arena = next(v for v in board.variants if v.variant_key == "a")
    by = {s.archetype: s for s in arena.by_archetype}

    assert by["Buyer"].objective_rate.mean == 1.0
    assert by["Skeptic"].objective_rate.mean == 0.0
