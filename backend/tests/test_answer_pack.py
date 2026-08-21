"""The objection matrix is built from measurement, or it is not built.

The contract under test:

- A run with no measured objections refuses, rather than generating a
  plausible matrix from nothing. That is the whole difference between this
  and the document a founder writes alone.
- Measured numbers on each row come from the database, never from the
  model's echo of them.
- A row for an objection nobody raised is dropped, not shown.
- The measured ranking survives the model's own ordering.
- Battlecards are written only for alternatives the founder named, plus the
  two that are always real — doing nothing and building in-house.
- The price sits at the target margin, like every other paid artifact.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.gtm import answer_pack as ap


class _Query:
    def __init__(self, table: str, store: dict):
        self._table = table
        self._store = store
        self._filters: dict = {}

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._filters[column] = value
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def single(self):
        return self

    def execute(self):
        rows = self._store.get(self._table, [])
        matched = [r for r in rows if all(r.get(k) == v for k, v in self._filters.items())]
        if self._table in ("simulations", "icp_profiles"):
            return SimpleNamespace(data=(matched[0] if matched else None))
        return SimpleNamespace(data=matched)


class _Admin:
    def __init__(self, store):
        self.store = store

    def table(self, name):
        return _Query(name, self.store)


SIM = "11111111-1111-1111-1111-111111111111"
ORG = "22222222-2222-2222-2222-222222222222"


def _store(objections):
    return {
        "canonical_objections": objections,
        "simulations": [{
            "id": SIM,
            "organization_id": ORG,
            "name": "Test product",
            "prediction_goal": "Would they pay?",
            "project_id": "33333333-3333-3333-3333-333333333333",
            "icp_profile_id": None,
        }],
    }


def _objection(key, label, agents, score, quote="They said this."):
    return {
        "simulation_id": SIM,
        "organization_id": ORG,
        "objection_key": key,
        "label": label,
        "summary": "",
        "quotes": [{"text": quote}],
        "agent_count": agents,
        "cohort_spread": {"a": 0.4, "b": 0.2},
        "load_bearing_score": score,
        "first_round_seen": 1,
    }


def _install(monkeypatch, store, generated):
    monkeypatch.setattr(ap, "get_supabase_admin", lambda: _Admin(store))

    async def fake_structured(_messages, _schema):
        return generated

    monkeypatch.setattr(ap, "llm_structured", fake_structured)


def _row(key, **over):
    base = {
        "objection_key": key,
        "acknowledge": "a", "explore": "b", "respond": "c", "confirm": "d",
    }
    base.update(over)
    return base


async def test_a_run_with_no_measured_objections_refuses(monkeypatch):
    """The failure this module exists to prevent.

    A matrix generated with nothing measured is exactly the document the
    founder would have written alone — invented objections answered with
    invented confidence — with the product's name on it, which makes it
    worse than not offering one.
    """
    _install(monkeypatch, _store([]), ap._Generated(rows=[], battlecards=[]))

    with pytest.raises(ValueError, match="no measured objections"):
        await ap.build_answer_pack(SIM, ORG)


async def test_measured_numbers_come_from_the_database_not_the_model(monkeypatch):
    """A model asked to echo a score will eventually round it."""
    _install(
        monkeypatch,
        _store([_objection("price", "Too expensive", agents=14, score=9.5)]),
        # The model claims different numbers. They must not survive.
        ap._Generated(
            rows=[_row("price", agents_raising=999, load_bearing_score=0.1)],
            battlecards=[],
        ),
    )

    pack = await ap.build_answer_pack(SIM, ORG)

    assert pack.rows[0].agents_raising == 14
    assert pack.rows[0].load_bearing_score == pytest.approx(9.5)
    assert pack.rows[0].evidence_quotes == ["They said this."]


async def test_a_row_for_an_objection_nobody_raised_is_dropped(monkeypatch):
    _install(
        monkeypatch,
        _store([_objection("price", "Too expensive", 14, 9.5)]),
        ap._Generated(
            rows=[_row("price"), _row("invented-by-the-model")],
            battlecards=[],
        ),
    )

    pack = await ap.build_answer_pack(SIM, ORG)

    assert [r.objection_key for r in pack.rows] == ["price"]


async def test_the_measured_ranking_survives_the_models_ordering(monkeypatch):
    """Load-bearing order is the product; the model's order is a suggestion."""
    _install(
        monkeypatch,
        _store([
            _objection("kills-deals", "The one that kills deals", 20, 9.9),
            _objection("loudest", "The loud one", 30, 2.0),
        ]),
        # Model returns them the other way round.
        ap._Generated(
            rows=[_row("loudest"), _row("kills-deals")],
            battlecards=[],
        ),
    )

    pack = await ap.build_answer_pack(SIM, ORG)

    assert [r.objection_key for r in pack.rows] == ["kills-deals", "loudest"]


async def test_walking_away_is_available_rather_than_always_rebutting(monkeypatch):
    """A matrix that pretends every objection is winnable teaches founders to
    argue with people who were never going to buy."""
    _install(
        monkeypatch,
        _store([_objection("wrong-buyer", "We are not the buyer for this", 8, 5.0)]),
        ap._Generated(
            rows=[_row("wrong-buyer", when_to_walk="They are not the buyer. Thank them and move on.")],
            battlecards=[],
        ),
    )

    pack = await ap.build_answer_pack(SIM, ORG)

    assert pack.rows[0].when_to_walk


def test_the_always_real_alternatives_are_never_forgotten():
    """Doing nothing and building in-house are the two competitors every
    founder has and no battlecard deck includes."""
    assert "Doing nothing" in ap.ALWAYS_REAL_ALTERNATIVES
    assert "Building it in-house" in ap.ALWAYS_REAL_ALTERNATIVES


def test_the_pack_is_priced_at_the_target_margin():
    from app.services.billing.agent_pricing import (
        ANSWER_PACK_COGS_USD,
        MIN_MARGIN_PCT,
        answer_pack_credits,
    )

    price = answer_pack_credits()
    assert price == 1_500

    # The margin floor, asserted rather than assumed: a COGS revision that
    # pushes this under the floor should fail here, not on the ledger.
    revenue = price / 1000  # credits are $0.001 of COGS by definition
    margin_pct = (revenue - float(ANSWER_PACK_COGS_USD)) / revenue * 100
    assert margin_pct >= float(MIN_MARGIN_PCT)
