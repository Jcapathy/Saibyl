"""Grounding must not fabricate evidence, and accuracy must not fabricate a rate.

Both modules exist because of the same finding: the most severe item on
saibyl.com's own website check is that nothing shows synthetic objections
predict real ones. `grounding.py` widens what the room argues about;
`outcomes.py` measures whether it was right.

Both are therefore one wrong default away from being the very thing they were
built to fix — an unbacked claim. What is pinned here is the set of refusals:

- an objection seen once is not grounding
- one org's runs are not de-identified evidence to another org
- an unanswered prediction is not a wrong prediction
- and there is no accuracy rate until there are enough answers to survive being
  asked "on how much?"
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.engine import grounding, outcomes
from app.services.engine.grounding import (
    MIN_ORGS_FOR_SHARED,
    MIN_RUNS,
    GroundedObjection,
    GroundingScope,
    grounded_objections,
    grounding_prompt_section,
)
from app.services.engine.outcomes import (
    MIN_ANSWERS_TO_REPORT,
    OutcomeVerdict,
    accuracy_for,
    record_outcome,
)

ORG = "org-asking"
OTHER = "org-somebody-else"


class _Query:
    def __init__(self, rows, state):
        self._rows, self._state, self._eq = rows, state, {}

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._eq[col] = val
        return self

    def limit(self, *_a, **_k):
        return self

    def upsert(self, row, **kwargs):
        self._state.upserts.append((row, kwargs))
        return self

    def execute(self):
        rows = self._rows
        for col, val in self._eq.items():
            rows = [r for r in rows if str(r.get(col)) == str(val)]
        return SimpleNamespace(data=rows)


def _wire(monkeypatch, module, rows):
    state = SimpleNamespace(upserts=[])
    monkeypatch.setattr(
        module, "get_supabase_admin",
        lambda: SimpleNamespace(table=lambda _n: _Query(rows, state)),
    )
    return state


def _objection(key, sim, org=ORG, label=None):
    return {
        "objection_key": key,
        "label": label or key.replace("_", " "),
        "simulation_id": sim,
        "organization_id": org,
    }


# ── grounding: what counts as evidence ───────────────────────────────────────

def test_an_objection_seen_once_is_not_grounding(monkeypatch):
    """One run is an anecdote. Reporting it as a pattern is the whole failure."""
    _wire(monkeypatch, grounding, [_objection("price_too_high", "sim-1")])
    assert grounded_objections(None, organization_id=ORG) == []


def test_an_objection_that_recurs_is_kept_with_its_count(monkeypatch):
    rows = [_objection("price_too_high", f"sim-{i}") for i in range(MIN_RUNS)]
    _wire(monkeypatch, grounding, rows)
    got = grounded_objections(None, organization_id=ORG)

    assert [o.key for o in got] == ["price_too_high"]
    assert got[0].run_count == MIN_RUNS
    assert "your own" in got[0].receipt(), "own-scope evidence must say whose it is"


def test_the_same_run_counted_twice_is_still_one_run(monkeypatch):
    """Objections are per-event; a run raising one repeatedly is one run."""
    rows = [_objection("price_too_high", "sim-1") for _ in range(9)]
    _wire(monkeypatch, grounding, rows)
    assert grounded_objections(None, organization_id=ORG) == []


# ── grounding: the tenancy boundary ──────────────────────────────────────────

def test_own_scope_never_reads_another_organisation(monkeypatch):
    rows = [_objection("theirs", f"sim-{i}", org=OTHER) for i in range(6)]
    _wire(monkeypatch, grounding, rows)
    assert grounded_objections(None, organization_id=ORG, scope=GroundingScope.OWN) == []


def test_shared_scope_needs_enough_organisations_to_be_an_aggregate(monkeypatch):
    """Two orgs is not de-identified: with two, the second knows the first."""
    rows = [
        _objection("shared_worry", f"sim-{i}", org=f"org-{i % (MIN_ORGS_FOR_SHARED - 1)}")
        for i in range(8)
    ]
    _wire(monkeypatch, grounding, rows)
    assert grounded_objections(None, organization_id=ORG, scope=GroundingScope.SHARED) == []


def test_shared_scope_excludes_the_asking_orgs_own_runs(monkeypatch):
    """Otherwise their own material is reported back as independent evidence."""
    rows = [_objection("mine", f"sim-{i}", org=ORG) for i in range(9)]
    _wire(monkeypatch, grounding, rows)
    assert grounded_objections(None, organization_id=ORG, scope=GroundingScope.SHARED) == []


def test_shared_scope_keeps_a_genuine_cross_org_pattern(monkeypatch):
    rows = [
        _objection("integration_risk", f"sim-{i}", org=f"org-{i}")
        for i in range(MIN_ORGS_FOR_SHARED)
    ]
    _wire(monkeypatch, grounding, rows)
    got = grounded_objections(None, organization_id=ORG, scope=GroundingScope.SHARED)

    assert [o.key for o in got] == ["integration_risk"]
    assert got[0].org_count == MIN_ORGS_FOR_SHARED
    assert "products" in got[0].receipt()


def test_a_broken_history_query_does_not_fail_the_run(monkeypatch):
    """Grounding is enrichment. Losing it costs quality, not the founder's run."""
    def _boom():
        raise RuntimeError("history unavailable")

    monkeypatch.setattr(grounding, "get_supabase_admin", _boom)
    assert grounded_objections(None, organization_id=ORG) == []


# ── grounding: the prompt must not put words in the room's mouth ─────────────

def test_the_prompt_asks_the_room_to_check_not_to_repeat():
    section = grounding_prompt_section([
        GroundedObjection("k", "Too expensive", 5, 1, GroundingScope.OWN)
    ])
    assert "CHECK" in section
    assert "not" in section and "conclusions to repeat" in section
    assert "Too expensive" in section


def test_no_grounding_means_no_prompt_section():
    """A new founder has no history, and that is normal, not an error."""
    assert grounding_prompt_section([]) == ""


# ── outcomes: the refusals that keep the number honest ───────────────────────

def _outcome(occurred):
    return {"occurred": occurred}


def test_an_unanswered_prediction_is_not_a_wrong_one(monkeypatch):
    """Counting NULL as False measures our follow-up rate and calls it accuracy."""
    rows = [_outcome(True)] * 20 + [_outcome(None)] * 40
    _wire(monkeypatch, outcomes, rows)

    got = accuracy_for()
    assert got.answered == 20
    assert got.confirmed == 20
    assert got.pending == 40


def test_there_is_no_rate_until_there_are_enough_answers(monkeypatch):
    _wire(monkeypatch, outcomes, [_outcome(True)] * (MIN_ANSWERS_TO_REPORT - 1))
    got = accuracy_for()

    assert got.rate is None, "a rate from too few answers is noise with a decimal point"
    assert "Not enough answers" in got.sentence
    assert str(MIN_ANSWERS_TO_REPORT) in got.sentence


def test_a_rate_appears_once_the_evidence_does(monkeypatch):
    rows = [_outcome(True)] * 24 + [_outcome(False)] * 8
    _wire(monkeypatch, outcomes, rows)
    got = accuracy_for()

    assert got.answered == 32
    assert got.confirmed == 24
    assert got.rate == pytest.approx(0.75)
    assert "24 of 32" in got.sentence and "75%" in got.sentence


def test_nothing_measured_reports_no_rate_rather_than_zero(monkeypatch):
    """A 0% that means "we have not asked" is worse than saying nothing."""
    _wire(monkeypatch, outcomes, [])
    got = accuracy_for()
    assert got.rate is None
    assert got.answered == 0


def test_a_verdict_is_upserted_so_a_correction_does_not_double_count(monkeypatch):
    state = _wire(monkeypatch, outcomes, [])
    record_outcome(
        organization_id=ORG,
        verdict=OutcomeVerdict("sim-1", "price_too_high", True, evidence="two sales calls"),
    )

    row, kwargs = state.upserts[0]
    assert kwargs["on_conflict"] == "simulation_id,objection_key"
    assert row["occurred"] is True
    assert row["evidence"] == "two sales calls"


def test_asking_without_an_answer_records_no_answered_at(monkeypatch):
    state = _wire(monkeypatch, outcomes, [])
    record_outcome(organization_id=ORG, verdict=OutcomeVerdict("sim-1", "k", None))

    row, _ = state.upserts[0]
    assert row["occurred"] is None
    assert "answered_at" not in row, "an unanswered prediction must not look answered"
