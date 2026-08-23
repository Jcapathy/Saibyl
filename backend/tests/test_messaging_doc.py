"""The messaging worksheet is filled from measurement, or it is not filled.

The contract under test:

- A run with no measured objections refuses, rather than filling a worksheet
  from nothing. That refusal is the whole difference between this and the
  document a founder writes alone.
- Measured numbers in the objections section come from the database, never
  from the model's echo of them.
- When the scoreboard refused to name a winner, the refusal survives into the
  document instead of the top row being promoted to "the pitch".
- Competitors come from the founder or from the buyers' own words; a name the
  model produced never reaches the document.
- The three-differentiator test is computed from the set, not asserted by the
  writer of the set.
- A missing number stays a visible placeholder and is counted.
- The price sits at the target margin, like every other paid artifact.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.gtm import messaging_doc as md


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


def _objection(key, label, agents=10, score=5.0, quote="They said this.", summary=""):
    return {
        "simulation_id": SIM,
        "organization_id": ORG,
        "objection_key": key,
        "label": label,
        "summary": summary,
        "quotes": [{"text": quote}],
        "agent_count": agents,
        "cohort_spread": {"a": 0.4, "b": 0.2},
        "load_bearing_score": score,
    }


def _variant(key, label, content, position=0):
    return {
        "simulation_id": SIM,
        "organization_id": ORG,
        "variant_key": key,
        "label": label,
        "content": content,
        "position": position,
    }


def _store(objections, *, variants=None, scoreboard=None, competitors=None):
    store = {
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
        "simulation_variants": variants or [],
        "simulation_analysis": [],
    }
    if scoreboard is not None:
        store["simulation_analysis"] = [{
            "simulation_id": SIM,
            "organization_id": ORG,
            "artifact": {"scoreboard": scoreboard},
        }]
    return store


def _prop(category="Fast", statement="It is faster.", source="the founder's words", key=None):
    return md.ValueProp(
        category=category,
        statement=statement,
        source=source,
        source_objection_key=key,
    )


def _diff(distinction="Distinct", benefit="So you win.", rivals=None):
    return md.Differentiator(
        distinction=distinction,
        client_benefit=benefit,
        rivals_who_can_claim_it=list(rivals or []),
    )


def _generated(**over):
    base = {
        "problem": md.Problem(headline="It is slow.", impact="[TODO: your number]"),
        "solution": md.Solution(
            what_we_do_high_level="We make it fast.",
            what_we_do_specific="We make batch jobs fast.",
            how_we_do_it="By scheduling them across idle machines.",
        ),
        "icp": md.ICPLine(who="Engineers", not_for="Consumers"),
        "value_props": [_prop(), _prop("Easy"), _prop("Efficient")],
        "differentiators": [_diff("One"), _diff("Two"), _diff("Three")],
        "elevator_pitch": md._PitchDraft(
            problem="Jobs are slow.",
            solution="We make them fast.",
            value="Teams ship sooner.",
            differentiator="No rewrite needed.",
            call_to_action="Can we book 20 minutes?",
        ),
        "objections": [],
        "notes": [],
    }
    base.update(over)
    return md._Generated(**base)


def _install(monkeypatch, store, generated):
    monkeypatch.setattr(md, "get_supabase_admin", lambda: _Admin(store))

    async def fake_structured(_messages, _schema):
        return generated

    monkeypatch.setattr(md, "llm_structured", fake_structured)


async def test_a_run_with_no_measured_objections_refuses(monkeypatch):
    """The failure this module exists to prevent.

    A messaging document written with nothing measured is exactly the one the
    founder would have written alone — an invented problem, value props they
    find impressive, differentiators nobody checked — with the product's name
    on it, which makes it worse than not offering one.
    """
    _install(monkeypatch, _store([]), _generated())

    with pytest.raises(ValueError, match="no measured objections"):
        await md.build_messaging_doc(SIM, ORG)


async def test_measured_numbers_come_from_the_database_not_the_model(monkeypatch):
    """A model asked to restate a score will eventually round it."""
    _install(
        monkeypatch,
        _store([_objection("price", "Too expensive", agents=14, score=9.5)]),
        _generated(
            objections=[
                md._ObjectionDraft(
                    objection_key="price",
                    how_the_messaging_answers_it="The pricing line moves above the fold.",
                )
            ]
        ),
    )

    doc = await md.build_messaging_doc(SIM, ORG)

    line = doc.objections[0]
    assert line.agents_raising == 14
    assert line.load_bearing_score == pytest.approx(9.5)
    assert line.quotes == ["They said this."]
    assert line.label == "Too expensive"
    assert doc.built_from_objections == 1


async def test_an_objection_nobody_raised_is_dropped(monkeypatch):
    _install(
        monkeypatch,
        _store([_objection("price", "Too expensive")]),
        _generated(
            objections=[
                md._ObjectionDraft(objection_key="price", how_the_messaging_answers_it="x"),
                md._ObjectionDraft(objection_key="invented", how_the_messaging_answers_it="y"),
            ]
        ),
    )

    doc = await md.build_messaging_doc(SIM, ORG)

    assert [line.objection_key for line in doc.objections] == ["price"]


async def test_a_refusal_to_name_a_winner_survives_into_the_document(monkeypatch):
    """The defect: promoting the top row of an overlapping scoreboard.

    The scoreboard declines to name a winner when the top two intervals
    overlap. If the document quietly picks the leader anyway, the founder
    repeats a sentence that sampling noise chose for them, for months, across
    every asset derived from this worksheet.

    Note the structural half of the guarantee too: `_PitchDraft` has no field
    for the winning variant, so the model could not name one even if it tried
    — the key is attached here or not at all.
    """
    verdict = (
        "No winner: Version A leads Version B by 4.0% per agent, but the 95% "
        "interval (-1.0% to 9.0%) includes zero."
    )
    _install(
        monkeypatch,
        _store(
            [_objection("price", "Too expensive")],
            variants=[
                _variant("a", "Version A", "Ship faster.", 0),
                _variant("b", "Version B", "Stop waiting.", 1),
            ],
            scoreboard={"winner_variant_key": None, "verdict": verdict},
        ),
        _generated(),
    )

    doc = await md.build_messaging_doc(SIM, ORG)

    assert doc.elevator_pitch.from_variant_key is None
    assert doc.elevator_pitch.caveat == verdict
    assert doc.message_test is not None
    assert doc.message_test.named_a_winner is False
    # Carried verbatim. Rewriting a refusal is how "the intervals overlap"
    # becomes "version B edged ahead".
    assert doc.message_test.verdict == verdict
    assert doc.message_test.versions_tested == 2


async def test_the_winning_message_becomes_the_pitch(monkeypatch):
    _install(
        monkeypatch,
        _store(
            [_objection("price", "Too expensive")],
            variants=[
                _variant("a", "Version A", "Ship faster.", 0),
                _variant("b", "Version B", "Stop waiting.", 1),
            ],
            scoreboard={
                "winner_variant_key": "b",
                "verdict": "Version B leads: agents were 12.0% more likely to convert.",
            },
        ),
        _generated(),
    )

    doc = await md.build_messaging_doc(SIM, ORG)

    assert doc.elevator_pitch.from_variant_key == "b"
    assert doc.elevator_pitch.from_variant_label == "Version B"
    assert doc.elevator_pitch.caveat is None
    assert doc.message_test.named_a_winner is True


async def test_a_winner_with_no_matching_variant_is_treated_as_no_winner(monkeypatch):
    """A broken join is not a result.

    Pointing the pitch at a variant key with no row behind it would produce a
    document that claims a version won and cannot say which words it was.
    """
    _install(
        monkeypatch,
        _store(
            [_objection("price", "Too expensive")],
            variants=[
                _variant("a", "Version A", "Ship faster.", 0),
                _variant("b", "Version B", "Stop waiting.", 1),
            ],
            scoreboard={"winner_variant_key": "zzz", "verdict": "Version Z leads."},
        ),
        _generated(),
    )

    doc = await md.build_messaging_doc(SIM, ORG)

    assert doc.elevator_pitch.from_variant_key is None
    assert doc.message_test.named_a_winner is False
    assert doc.elevator_pitch.caveat


async def test_a_single_message_run_makes_no_comparison_claim(monkeypatch):
    """One version is not a comparison, and a one-row result invites a reader
    to treat it as one."""
    _install(
        monkeypatch,
        _store(
            [_objection("price", "Too expensive")],
            variants=[_variant("a", "The only version", "Ship faster.", 0)],
        ),
        _generated(),
    )

    doc = await md.build_messaging_doc(SIM, ORG)

    assert doc.message_test is None
    assert doc.elevator_pitch.caveat is None


async def test_a_competitor_the_model_invented_never_reaches_the_document(monkeypatch):
    """The failure: a differentiator argued against a company that does not
    exist. Nobody catches it until a prospect does."""
    _install(
        monkeypatch,
        _store([_objection("price", "Too expensive")], competitors=["Rivalry Inc"]),
        _generated(
            differentiators=[
                _diff("One", rivals=["Rivalry Inc", "Fabricated Corp"]),
                _diff("Two", rivals=["Fabricated Corp"]),
                _diff("Three", rivals=[]),
            ]
        ),
    )

    doc = await md.build_messaging_doc(SIM, ORG)

    assert "Fabricated Corp" not in doc.alternatives
    for differentiator in doc.differentiators:
        assert "Fabricated Corp" not in differentiator.rivals_who_can_claim_it
    assert "Rivalry Inc" in doc.alternatives


async def test_a_competitor_the_buyers_named_out_loud_is_allowed(monkeypatch):
    """The model may notice a rival in the room's own words. It may not
    conjure one, and the difference is a substring match away."""
    _install(
        monkeypatch,
        _store(
            [_objection("switching", "We already have something", quote="We already use Wedge.")],
            competitors=["Rivalry Inc"],
        ),
        _generated(differentiators=[_diff("One", rivals=["Wedge"]), _diff("Two"), _diff("Three")]),
    )

    doc = await md.build_messaging_doc(SIM, ORG)

    assert "Wedge" in doc.alternatives
    assert doc.differentiators[0].rivals_who_can_claim_it == ["Wedge"]


async def test_a_competitor_row_is_read_as_a_name_not_a_python_dict(monkeypatch):
    """`icp_profiles.competitors` holds `Competitor.model_dump()` rows, and
    every writer of that column writes them that way.

    `str(row)` therefore rendered "{'name': 'Datadog', 'positioning': 'APM
    incumbent', 'mentioned_in': ['9f3e…']}" into `alternatives`, which the
    founder reads — an internal document UUID in a paid worksheet. Worse, the
    model's correct nomination of the founder's actual competitor matched no
    entry, so it was dropped as invented and the three-differentiator test
    never had a name that could break the set: it reported "Defensible"
    whatever the rival lists said.
    """
    _install(
        monkeypatch,
        _store(
            [_objection("price", "Too expensive")],
            competitors=[{
                "name": "Datadog",
                "positioning": "APM incumbent",
                "mentioned_in": ["9f3e1a20-0000-4000-8000-000000000000"],
            }],
        ),
        _generated(
            differentiators=[
                _diff("One", rivals=["Datadog"]),
                _diff("Two", rivals=["Datadog"]),
                _diff("Three", rivals=["Datadog"]),
            ]
        ),
    )

    doc = await md.build_messaging_doc(SIM, ORG)

    assert "Datadog" in doc.alternatives
    assert all("mentioned_in" not in name for name in doc.alternatives)
    assert doc.differentiators[0].rivals_who_can_claim_it == ["Datadog"]
    # The set the model itself says Datadog claims three times over is not
    # defensible, and the document has to say so.
    assert "Not defensible" in doc.differentiation_verdict
    assert "Datadog" in doc.differentiation_verdict


async def test_the_measured_agent_count_is_not_evidence_for_a_figure(monkeypatch):
    """The prompt states "raised by: 14 buyers", and the scrubber was pointed
    at the prompt — so a count this module printed licensed any figure that
    landed on the same number, in the document every other asset is derived
    from."""
    _install(
        monkeypatch,
        _store([_objection("price", "Too expensive", agents=14)]),
        _generated(
            value_props=[
                _prop("Fast", statement="We are 14% cheaper than the incumbent."),
                _prop("Easy"),
                _prop("Efficient"),
            ]
        ),
    )

    doc = await md.build_messaging_doc(SIM, ORG)

    assert "14%" not in doc.value_props[0].statement
    assert md.MISSING_NUMBER in doc.value_props[0].statement


def test_the_always_real_alternatives_are_never_forgotten():
    """Doing nothing and building in-house are usually the highest-frequency
    competitors in early-stage B2B and the ones most often left off."""
    assert "Doing nothing" in md.ALWAYS_REAL_ALTERNATIVES
    assert "Building it in-house" in md.ALWAYS_REAL_ALTERNATIVES


async def test_the_three_way_test_is_computed_from_the_set_not_asserted(monkeypatch):
    """A model asked whether its own set passes the test will say yes."""
    _install(
        monkeypatch,
        _store([_objection("price", "Too expensive")], competitors=["Rivalry Inc"]),
        _generated(
            differentiators=[
                _diff("One", rivals=["Rivalry Inc"]),
                _diff("Two", rivals=["Rivalry Inc"]),
                _diff("Three", rivals=["Rivalry Inc"]),
            ]
        ),
    )

    doc = await md.build_messaging_doc(SIM, ORG)

    assert "Not defensible" in doc.differentiation_verdict
    assert "Rivalry Inc" in doc.differentiation_verdict


async def test_a_set_no_alternative_breaks_is_reported_as_defensible(monkeypatch):
    _install(
        monkeypatch,
        _store([_objection("price", "Too expensive")], competitors=["Rivalry Inc"]),
        _generated(
            differentiators=[
                _diff("One", rivals=["Rivalry Inc"]),
                _diff("Two", rivals=["Rivalry Inc"]),
                _diff("Three", rivals=[]),
            ]
        ),
    )

    doc = await md.build_messaging_doc(SIM, ORG)

    assert doc.differentiation_verdict.startswith("Defensible")


async def test_there_are_never_more_than_three_value_props(monkeypatch):
    """More than three and none of them are remembered."""
    _install(
        monkeypatch,
        _store([_objection("price", "Too expensive")]),
        _generated(value_props=[_prop(f"Category {i}") for i in range(7)]),
    )

    doc = await md.build_messaging_doc(SIM, ORG)

    assert len(doc.value_props) == md.VALUE_PROP_COUNT


async def test_a_missing_value_prop_is_declared_rather_than_manufactured(monkeypatch):
    """Padding to three would be the invention this module refuses, and the
    one the founder least suspects because the document looks complete."""
    _install(
        monkeypatch,
        _store([_objection("price", "Too expensive")]),
        _generated(value_props=[_prop("Fast"), _prop("Easy")]),
    )

    doc = await md.build_messaging_doc(SIM, ORG)

    assert len(doc.value_props) == 2
    assert any("value propositions" in note for note in doc.notes)


async def test_a_value_prop_citing_an_objection_nobody_raised_loses_the_citation(monkeypatch):
    _install(
        monkeypatch,
        _store([_objection("price", "Too expensive")]),
        _generated(
            value_props=[
                _prop("Fast", key="never-raised"),
                _prop("Easy", key="price"),
                _prop("Safe"),
            ]
        ),
    )

    doc = await md.build_messaging_doc(SIM, ORG)

    keys = {p.category: p.source_objection_key for p in doc.value_props}
    assert keys["Fast"] is None
    assert keys["Easy"] == "price"


async def test_value_prop_order_follows_the_measured_ranking(monkeypatch):
    """Emphasis is the measurement's, not the model's: the prop answering the
    objection that costs deals leads, whatever order it came back in."""
    _install(
        monkeypatch,
        _store([
            _objection("kills-deals", "The one that kills deals", agents=20, score=9.9),
            _objection("loudest", "The loud one", agents=30, score=2.0),
        ]),
        _generated(
            value_props=[
                _prop("Loud", key="loudest"),
                _prop("Deadly", key="kills-deals"),
                _prop("Unsourced"),
            ]
        ),
    )

    doc = await md.build_messaging_doc(SIM, ORG)

    assert [p.category for p in doc.value_props] == ["Deadly", "Loud", "Unsourced"]


async def test_the_objections_section_keeps_the_measured_ranking(monkeypatch):
    _install(
        monkeypatch,
        _store([
            _objection("kills-deals", "The one that kills deals", agents=20, score=9.9),
            _objection("loudest", "The loud one", agents=30, score=2.0),
        ]),
        _generated(
            objections=[
                md._ObjectionDraft(objection_key="loudest", how_the_messaging_answers_it="a"),
                md._ObjectionDraft(objection_key="kills-deals", how_the_messaging_answers_it="b"),
            ]
        ),
    )

    doc = await md.build_messaging_doc(SIM, ORG)

    assert [line.objection_key for line in doc.objections] == ["kills-deals", "loudest"]


async def test_a_missing_number_stays_a_visible_placeholder_and_is_counted(monkeypatch):
    """A visible placeholder is honest; a plausible invention is a statistic
    the founder says out loud to the one audience that can check it."""
    _install(
        monkeypatch,
        _store([_objection("price", "Too expensive")]),
        _generated(
            value_props=[
                _prop("Fast", statement=f"Cut runtime by {md.MISSING_NUMBER}."),
                _prop("Easy"),
                _prop("Efficient"),
            ]
        ),
    )

    doc = await md.build_messaging_doc(SIM, ORG)

    assert md.MISSING_NUMBER in doc.value_props[0].statement
    # The problem's impact carries one too, so both sections are counted.
    assert doc.placeholders_to_fill == 2


def test_the_document_is_priced_at_the_target_margin():
    from app.services.billing.agent_pricing import (
        MESSAGING_DOC_COGS_USD,
        MIN_MARGIN_PCT,
        messaging_doc_credits,
    )

    price = messaging_doc_credits()
    assert price == 1_500

    # The margin floor, asserted rather than assumed: a COGS revision that
    # pushes this under the floor should fail here, not on the ledger.
    revenue = price / 1000  # credits are $0.001 of COGS by definition
    margin_pct = (revenue - float(MESSAGING_DOC_COGS_USD)) / revenue * 100
    assert margin_pct >= float(MIN_MARGIN_PCT)
