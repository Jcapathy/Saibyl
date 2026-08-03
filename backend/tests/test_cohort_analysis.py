"""The cohort split, the adversarial disclosure, and objection origin.

These test the honesty properties, not the arithmetic. A founder reading a −0.4
headline on a run where 40% of the swarm was configured to be hostile is being
told something different from a founder reading −0.4 on a pure-buyer swarm, and
the artifact is the only place that distinction can be made durable.
"""
from __future__ import annotations

import pytest

from app.services.intelligence.analysis_builder import (
    _adversarial_disclosure,
    _attribute_objection_cohorts,
    _by_cohort,
    _quality,
    _timeline,
)
from app.services.intelligence.analysis_data import MeasuredEvent, RunData
from app.services.intelligence.analysis_schema import ObjectionSummary
from app.services.intelligence.report_agent import build_lens_context


def _event(
    event_id: str,
    agent: str,
    *,
    valence: float = 0.0,
    adversarial: bool = False,
    round_number: int = 1,
    archetype: str = "Buyer",
    stance: str = "support",
) -> MeasuredEvent:
    return MeasuredEvent(
        id=event_id,
        agent_id=agent,
        agent_username=agent,
        archetype=archetype,
        platform="hacker_news",
        round_number=round_number,
        event_type="post",
        content="text",
        valence=valence,
        stance=stance,
        intensity=0.5,
        intent=None,
        is_novel_claim=False,
        objections=[],
        is_adversarial=adversarial,
        adversarial_role="incumbent_power_user" if adversarial else None,
    )


def _run(**overrides) -> RunData:
    events = overrides.pop(
        "events",
        [
            _event("e1", "buyer-1", valence=0.4),
            _event("e2", "buyer-2", valence=0.2),
            _event("e3", "adv-1", valence=-0.8, adversarial=True, archetype="Incumbent user"),
            _event("e4", "adv-2", valence=-0.6, adversarial=True, archetype="Incumbent user"),
        ],
    )
    defaults = {
        "simulation_id": "sim-1",
        "organization_id": "org-1",
        "prediction_goal": "goal",
        "max_rounds": 3,
        "events": events,
        "agents_total": 10,
        "archetypes": ["Buyer", "Incumbent user"],
        "platforms": ["hacker_news"],
        "events_total": len(events),
        "events_measured": len(events),
        "measurement_model": "haiku",
        "agents_adversarial": 4,
        "adversarial_archetypes": ["Incumbent user"],
        "adversarial_roles": {"incumbent_power_user": 4},
        "adversarial_share_configured": 0.4,
        "named_competitors": [],
        "lens": "founder",
        "founder_stage": "pre_launch_positioning",
    }
    defaults.update(overrides)
    return RunData(**defaults)


def _pure_buyer_run() -> RunData:
    return _run(
        events=[_event("e1", "buyer-1", valence=0.4), _event("e2", "buyer-2", valence=0.2)],
        agents_adversarial=0,
        adversarial_archetypes=[],
        adversarial_roles={},
        adversarial_share_configured=0.0,
        archetypes=["Buyer"],
        events_total=2,
        events_measured=2,
    )


# ---------------------------------------------------------------------------
# The cohort split
# ---------------------------------------------------------------------------

def test_cohort_split_is_empty_without_an_adversarial_cohort():
    """A one-sided split is not a split. Rendering "buyers: 100%" is noise."""
    assert _by_cohort(_pure_buyer_run(), []) == []


def test_cohort_split_separates_buyers_from_incumbent_aligned():
    slices = _by_cohort(_run(), [])

    by_name = {s.cohort: s for s in slices}
    assert set(by_name) == {"buyer", "adversarial"}
    assert by_name["buyer"].valence.mean > 0
    assert by_name["adversarial"].valence.mean < 0


def test_cohort_slice_reports_allocation_not_only_participation():
    """A cohort allocated 4 agents that spoke twice is a finding.

    It is only visible if the denominator is the allocation, so the slice
    carries both numbers.
    """
    run = _run(
        events=[
            _event("e1", "buyer-1", valence=0.4),
            _event("e3", "adv-1", valence=-0.8, adversarial=True),
        ]
    )
    slices = {s.cohort: s for s in _by_cohort(run, [])}

    assert slices["adversarial"].agents_total == 4
    assert slices["adversarial"].agent_count == 1
    assert slices["buyer"].agents_total == 6


def test_cohort_archetypes_do_not_overlap():
    slices = {s.cohort: s for s in _by_cohort(_run(), [])}
    assert slices["adversarial"].archetypes == ["Incumbent user"]
    assert "Incumbent user" not in slices["buyer"].archetypes


# ---------------------------------------------------------------------------
# The disclosure
# ---------------------------------------------------------------------------

def test_disclosure_is_disabled_without_a_cohort():
    disclosure = _adversarial_disclosure(_pure_buyer_run())
    assert disclosure.enabled is False
    assert disclosure.disclosure == ""


def test_disclosure_states_the_count_the_share_and_the_construction():
    disclosure = _adversarial_disclosure(_run())

    assert disclosure.enabled is True
    assert disclosure.agents_total == 4
    assert disclosure.share_realised == pytest.approx(0.4)
    assert "synthetic" in disclosure.disclosure
    assert "argue against adopting" in disclosure.disclosure


def test_disclosure_says_so_when_no_competitor_was_named():
    """The normal case. Saying nothing would read as an omission."""
    disclosure = _adversarial_disclosure(_run())
    assert "No competitor was named" in disclosure.disclosure
    assert disclosure.named_competitors == []


def test_disclosure_names_only_competitors_the_material_grounded():
    disclosure = _adversarial_disclosure(_run(named_competitors=["Datadog"]))
    assert "Datadog" in disclosure.disclosure
    assert "no claim about a real company originates from the model" in disclosure.disclosure


def test_realised_share_can_differ_from_configured():
    """Allocation rounds to whole agents, so the two legitimately differ."""
    run = _run(agents_total=9, agents_adversarial=4, adversarial_share_configured=0.4)
    disclosure = _adversarial_disclosure(run)

    assert disclosure.share_configured == pytest.approx(0.4)
    assert disclosure.share_realised == pytest.approx(4 / 9, rel=1e-3)


# ---------------------------------------------------------------------------
# Quality caveats
# ---------------------------------------------------------------------------

def test_quality_caveat_warns_that_the_headline_includes_the_cohort():
    run = _run()
    quality = _quality(run, _timeline(run), 4)

    assert any("incumbent-aligned" in c for c in quality.caveats)


def test_no_cohort_caveat_on_a_pure_buyer_run():
    run = _pure_buyer_run()
    quality = _quality(run, _timeline(run), 2)

    assert not any("incumbent-aligned" in c for c in quality.caveats)


# ---------------------------------------------------------------------------
# Objection origin
# ---------------------------------------------------------------------------

def _objection(event_ids: list[str]) -> ObjectionSummary:
    return ObjectionSummary(key="switching-cost", label="Switching cost", event_ids=event_ids)


def test_objection_raised_first_by_the_cohort_and_then_by_buyers_has_crossed():
    run = _run(
        events=[
            _event("a1", "adv-1", adversarial=True, round_number=1),
            _event("b1", "buyer-1", round_number=3),
        ]
    )
    objection = _objection(["a1", "b1"])

    _attribute_objection_cohorts(run, [objection])

    assert objection.originated_adversarial is True
    assert objection.buyer_agent_count == 1
    assert objection.crossed_into_buyers is True


def test_objection_confined_to_the_cohort_has_not_crossed():
    """A competitor talking to themselves is a different finding entirely."""
    run = _run(
        events=[
            _event("a1", "adv-1", adversarial=True, round_number=1),
            _event("a2", "adv-2", adversarial=True, round_number=2),
        ]
    )
    objection = _objection(["a1", "a2"])

    _attribute_objection_cohorts(run, [objection])

    assert objection.originated_adversarial is True
    assert objection.buyer_agent_count == 0
    assert objection.crossed_into_buyers is False


def test_a_mixed_first_round_is_not_credited_to_the_cohort():
    """If a buyer said it in the same round, it was already in the market's
    mouth. Crediting the incumbent would overstate the cohort's influence,
    which is the direction this feature is most likely to be wrong in."""
    run = _run(
        events=[
            _event("a1", "adv-1", adversarial=True, round_number=1),
            _event("b1", "buyer-1", round_number=1),
        ]
    )
    objection = _objection(["a1", "b1"])

    _attribute_objection_cohorts(run, [objection])

    assert objection.originated_adversarial is False


def test_attribution_is_a_noop_without_a_cohort():
    objection = _objection(["e1"])
    _attribute_objection_cohorts(_pure_buyer_run(), [objection])

    assert objection.originated_adversarial is False
    assert objection.adversarial_agent_count == 0


# ---------------------------------------------------------------------------
# The report's lens context
# ---------------------------------------------------------------------------

def test_lens_context_is_empty_for_a_legacy_run():
    """Every run made before Phase 2 has no lens and no cohort. Their reports
    must come out exactly as they did."""
    assert build_lens_context({}, None) == ""


def test_lens_context_carries_the_stage_questions_and_its_limits():
    context = build_lens_context({"founder_stage": "concept_validation"}, None)

    assert "Concept validation" in context
    assert "THIS RUN CANNOT CONCLUDE" in context
    assert "no product for an agent to adopt" in context


def test_lens_context_forbids_naming_a_competitor_when_none_was_grounded():
    artifact = {
        "adversarial": {
            "enabled": True,
            "disclosure": "4 of 10 agents were incumbent-aligned.",
            "named_competitors": [],
        }
    }
    context = build_lens_context({}, artifact)

    assert "No competitor was named in this run. Do not name one." in context


def test_lens_context_permits_a_grounded_name_but_not_claims_about_it():
    artifact = {
        "adversarial": {
            "enabled": True,
            "disclosure": "4 of 10 agents were incumbent-aligned.",
            "named_competitors": ["Datadog"],
        }
    }
    context = build_lens_context({}, artifact)

    assert "Datadog" in context
    assert "MUST\n    NOT state any fact about their product" in context


def test_lens_context_requires_separating_the_cohorts():
    artifact = {"adversarial": {"enabled": True, "disclosure": "x", "named_competitors": []}}
    context = build_lens_context({}, artifact)

    assert "Never present an incumbent-aligned agent's argument as independent" in context


def test_lens_context_ignores_a_disabled_cohort():
    context = build_lens_context({}, {"adversarial": {"enabled": False}})
    assert context == ""
