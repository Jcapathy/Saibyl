"""Guards for the readers that report one sentiment number for a whole run.

Every one of these used to average `simulation_events.metadata["sentiment"]`, a
key written by the drift formula removed in Phase 1. On a run measured since it
is absent, and each reader had its own way of turning that absence into a
number: a 0.0 mean, an "N/A" handed to a prompt that mandates a filled stat
card. These tests hold the line that an unmeasured run produces no headline
figure at all.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.services.intelligence.analysis_data import MeasuredEvent, RunData


def _event(
    agent: str,
    round_number: int,
    valence: float | None,
    stance: str | None = "support",
    event_type: str = "post",
) -> MeasuredEvent:
    return MeasuredEvent(
        id=f"{agent}-r{round_number}-{valence}",
        agent_id=agent,
        agent_username=agent,
        archetype="Tester",
        platform="twitter_x",
        round_number=round_number,
        event_type=event_type,
        content="text",
        valence=valence,
        stance=stance,
        intensity=0.5,
        intent="none",
        is_novel_claim=False,
        objections=[],
    )


def _run(events: list[MeasuredEvent]) -> RunData:
    return RunData(
        simulation_id="sim-1",
        organization_id="org-1",
        prediction_goal="will it land",
        max_rounds=3,
        events=events,
        agents_total=len({e.agent_id for e in events}),
        events_total=len(events),
        events_measured=len(events),
    )


# ── Polarization ─────────────────────────────────────────

def test_unmeasured_run_reports_no_polarization():
    from app.services.intelligence.report_agent import compute_polarization

    assert compute_polarization([]) == {
        "controversy_score": None,
        "polarization_ratio": None,
        "valence_switching_pct": None,
    }


def test_reactions_are_not_moderate_opinions():
    """A like carries no text. Counting it as 0.0 would say the room is calm."""
    from app.services.intelligence.report_agent import compute_polarization

    reactions = [_event("a", 1, None, None, "react") for _ in range(20)]
    assert compute_polarization(reactions)["polarization_ratio"] is None

    # One extreme poster among twenty reactions is an extreme room, not a
    # 1-in-21 fringe.
    metrics = compute_polarization([*reactions, _event("b", 1, 0.9)])
    assert metrics["polarization_ratio"] == "1.0:1"


def test_off_topic_events_hold_no_position():
    from app.services.intelligence.report_agent import compute_polarization

    assert compute_polarization(
        [_event("a", 1, 0.9, "off_topic")]
    )["polarization_ratio"] is None


def test_ratio_clusters_by_agent_at_the_final_round():
    from app.services.intelligence.report_agent import compute_polarization

    metrics = compute_polarization([
        _event("a", 1, 0.1),           # earlier round: not in the ratio
        _event("a", 2, -0.9),
        _event("a", 2, -0.7),          # same agent, same round: one position
        _event("b", 2, 0.2),
        _event("c", 2, 0.9),
    ])
    # Final-round agent means: a=-0.8, b=0.2, c=0.9 -> 2 extreme, 1 moderate.
    assert metrics["polarization_ratio"] == "2.0:1"
    assert metrics["controversy_score"] == 0.4


def test_valence_switching_is_measured_within_an_agent():
    from app.services.intelligence.report_agent import compute_polarization

    metrics = compute_polarization([
        _event("a", 1, 0.8), _event("a", 2, -0.9),   # crosses zero
        _event("b", 1, 0.1), _event("b", 2, 0.2),    # does not
    ])
    assert metrics["valence_switching_pct"] == 50


def test_single_round_run_reports_no_switching_rather_than_zero():
    """No transition was observed. That is absent, not "nobody changed"."""
    from app.services.intelligence.report_agent import compute_polarization

    metrics = compute_polarization([_event("a", 1, 0.8), _event("b", 1, -0.8)])
    assert metrics["valence_switching_pct"] is None
    assert metrics["polarization_ratio"] == "2.0:1"


# ── The report prompt ────────────────────────────────────

def test_unmeasured_polarization_is_omitted_from_the_stat_card():
    """The prompt mandates a filled table, so an empty slot gets invented."""
    from app.services.intelligence.report_agent import (
        CONCLUSION_PROMPT,
        EXECUTIVE_SUMMARY_PROMPT,
        _polarization_prompt_fields,
        compute_polarization,
    )

    fields = _polarization_prompt_fields(compute_polarization([]))
    assert fields["polarization_row"] == ""
    assert "N/A" not in "".join(fields.values())

    common = dict(
        prediction_goal="g", platforms="twitter_x", agent_count=10,
        rounds=3, event_count=100, sections_text="S",
    )
    exec_prompt = EXECUTIVE_SUMMARY_PROMPT.format(**common, **fields)
    conclusion = CONCLUSION_PROMPT.format(**common, **fields)

    assert "| Polarization Ratio |" not in exec_prompt
    assert "N/A" not in exec_prompt
    assert "Polarization ratio (extreme-to-moderate)" not in conclusion


def test_measured_polarization_keeps_the_stat_card_row():
    from app.services.intelligence.report_agent import (
        EXECUTIVE_SUMMARY_PROMPT,
        _polarization_prompt_fields,
        compute_polarization,
    )

    metrics = compute_polarization([_event("a", 1, 0.9), _event("b", 1, 0.1)])
    fields = _polarization_prompt_fields(metrics)
    exec_prompt = EXECUTIVE_SUMMARY_PROMPT.format(
        prediction_goal="g", platforms="twitter_x", agent_count=10,
        rounds=3, event_count=100, sections_text="S", **fields,
    )
    assert "| Polarization Ratio | 1.0:1 |" in exec_prompt


# ── The Saibyl Score ─────────────────────────────────────

class _FakeQuery:
    """Minimal stand-in for the supabase query builder score.py chains."""

    def __init__(self, data):
        self._data = data

    def __getattr__(self, _name):
        return lambda *_args, **_kwargs: self

    def execute(self):
        return type("Result", (), {"data": self._data})()


def _patch_score_deps(monkeypatch, run: RunData, status: str = "complete"):
    sim_row = [{
        "id": "sim-1", "name": "Launch", "prediction_goal": "will it land",
        "status": status,
    }]
    monkeypatch.setattr(
        "app.api.score.get_supabase_admin",
        lambda: type("Admin", (), {"table": lambda _self, _n: _FakeQuery(sim_row)})(),
    )
    monkeypatch.setattr("app.api.score.load_run_data", lambda _sim_id: run)

    async def _summary(**_kwargs):
        return "A summary."

    monkeypatch.setattr("app.api.score.llm_complete", _summary)


@pytest.mark.asyncio
async def test_unmeasured_run_produces_no_saibyl_score(monkeypatch):
    """The headline number must not exist when nothing behind it was measured.

    A defaulted mean of 0.0 scores 50/100 and publishes "mixed outlook" as a
    verdict — the single most visible fabricated number in the product.
    """
    from app.api.score import _compute_score

    _patch_score_deps(monkeypatch, _run([
        _event("a", 1, None, None, "react"),
        _event("b", 1, 0.9, "off_topic"),
    ]))

    with pytest.raises(HTTPException) as exc:
        await _compute_score("sim-1", "org-1")

    assert exc.value.status_code == 422
    assert "no measured sentiment" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_score_is_derived_from_measured_valence(monkeypatch):
    from app.api.score import _compute_score

    _patch_score_deps(monkeypatch, _run([
        _event("a", 1, 0.5), _event("b", 1, 0.5), _event("c", 1, 0.5),
    ]))

    result = await _compute_score("sim-1", "org-1")
    # (0.5 + 1) / 2 * 100, with no controversy boost: the agents agree.
    assert result.score == 75
    assert result.category == "positive"


@pytest.mark.asyncio
async def test_one_prolific_agent_is_not_a_divided_room(monkeypatch):
    """Spread is measured across agents, so verbosity cannot earn the boost."""
    from app.api.score import _compute_score

    _patch_score_deps(monkeypatch, _run([
        _event("a", 1, 1.0), _event("a", 2, -1.0),
        _event("b", 1, 0.0),
    ]))

    result = await _compute_score("sim-1", "org-1")
    # Agent means are 0.0 and 0.0 — no spread, so no +10 controversy boost.
    assert result.score == 50


# ── Comparison ───────────────────────────────────────────

def test_comparison_states_an_unmeasured_run_as_unmeasured():
    from app.api.comparison import _sentiment_line

    line = _sentiment_line({
        "avg_sentiment": None, "sentiment_ci": None, "sentiment_agents": 0,
    })
    assert "not measured" in line
    assert "0.0" not in line


def test_comparison_quotes_the_interval_with_the_mean():
    from app.api.comparison import _sentiment_line

    line = _sentiment_line({
        "avg_sentiment": -0.42, "sentiment_ci": [-0.55, -0.29],
        "sentiment_agents": 37,
    })
    assert "-0.42" in line
    assert "37 agents" in line
