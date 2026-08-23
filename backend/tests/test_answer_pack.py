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
ICP = "44444444-4444-4444-4444-444444444444"


def _store(objections, *, competitors=None):
    return {
        "canonical_objections": objections,
        "simulations": [{
            "id": SIM,
            "organization_id": ORG,
            "name": "Test product",
            "prediction_goal": "Would they pay?",
            "project_id": "33333333-3333-3333-3333-333333333333",
            "icp_profile_id": ICP if competitors is not None else None,
        }],
        "icp_profiles": [{
            "id": ICP,
            "competitors": competitors or [],
            "product_summary": "A thing that does a thing.",
        }],
    }


def _card(rival):
    return ap.Battlecard(
        rival=rival,
        they_say="They say they are cheaper.",
        the_honest_read="They are, on a small team.",
        where_we_win="Multi-entity closes.",
    )


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


async def test_a_battlecard_for_a_rival_nobody_named_is_dropped(monkeypatch):
    """The guarantee the docstring makes and the module did not keep.

    `rivals` was interpolated into the prompt and nothing checked what came
    back, so the model could return a battlecard for a company the founder has
    never heard of — in the one artifact a founder reads out loud on a live
    call. Asking a model to name a founder's competitors is how a battlecard
    ends up arguing against a company that does not exist.
    """
    _install(
        monkeypatch,
        _store([_objection("price", "Too expensive", 14, 9.5)]),
        ap._Generated(
            rows=[_row("price")],
            battlecards=[_card("Numeric"), _card("Doing nothing")],
        ),
    )

    pack = await ap.build_answer_pack(SIM, ORG)

    assert [card.rival for card in pack.battlecards] == ["Doing nothing"]


async def test_a_rival_the_buyers_named_out_loud_keeps_its_battlecard(monkeypatch):
    """The model may notice a rival in the room's own words. It may not conjure
    one, and the difference is a substring match away."""
    _install(
        monkeypatch,
        _store([
            _objection("switching", "We already have something", 8, 5.0, quote="We already use Wedge.")
        ]),
        ap._Generated(rows=[_row("switching")], battlecards=[_card("Wedge")]),
    )

    pack = await ap.build_answer_pack(SIM, ORG)

    assert [card.rival for card in pack.battlecards] == ["Wedge"]


async def test_a_competitor_row_is_read_as_a_name_not_a_python_dict(monkeypatch):
    """`icp_profiles.competitors` holds `Competitor.model_dump()` rows, and
    every writer of that column writes them that way.

    `str(row)` put "{'name': 'Datadog', 'positioning': …, 'mentioned_in':
    ['9f3e…']}" into the allow-list the model is told to write about — so the
    founder's real competitor was unrecognisable in the prompt and any
    battlecard naming it was then dropped as invented.
    """
    store = _store(
        [_objection("price", "Too expensive", 14, 9.5)],
        competitors=[{
            "name": "Datadog",
            "positioning": "APM incumbent",
            "mentioned_in": ["9f3e1a20-0000-4000-8000-000000000000"],
        }],
    )
    monkeypatch.setattr(ap, "get_supabase_admin", lambda: _Admin(store))
    prompts: list[str] = []

    async def fake_structured(messages, _schema):
        prompts.append(messages[-1]["content"])
        return ap._Generated(rows=[_row("price")], battlecards=[_card("Datadog")])

    monkeypatch.setattr(ap, "llm_structured", fake_structured)

    pack = await ap.build_answer_pack(SIM, ORG)

    assert "- Datadog" in prompts[0]
    assert "mentioned_in" not in prompts[0]
    assert [card.rival for card in pack.battlecards] == ["Datadog"]


async def test_the_measured_agent_count_is_not_evidence_for_a_figure(monkeypatch):
    """The prompt states "raised by: 14 buyers", and the scrubber was pointed
    at the prompt — so a count this module printed licensed "we are 14%
    cheaper", in a line meant to be said out loud to someone who can check it.
    """
    _install(
        monkeypatch,
        _store([_objection("price", "Too expensive", 14, 9.5)]),
        ap._Generated(
            rows=[_row("price", respond="We are 14% cheaper than the incumbent.")],
            battlecards=[],
        ),
    )

    pack = await ap.build_answer_pack(SIM, ORG)

    assert "14%" not in pack.rows[0].respond
    assert "[TODO: your number]" in pack.rows[0].respond
    assert pack.placeholders_to_fill == 1


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
