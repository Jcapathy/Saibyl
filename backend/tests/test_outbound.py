"""The outbound sequence is built from measurement, or it is not built.

The contract under test:

- A run with no measured objections refuses, and so does a run with no buyer
  profile. Generic outbound is the thing this module exists to not produce.
- The pain slots are filled from the measured ranking. The model is never asked
  which objection a touch answers, so it cannot reorder them.
- Measured numbers on each touch come from the database, never from the model.
- The cadence is code. The model cannot add a touch, and a touch it left blank
  is dropped rather than rendered empty.
- A pain nobody raised leaves its touches out rather than filling them.
- The scoreboard's refusal to name a winner is honoured.
- No contact data is stored anywhere, and nothing here sends.
- The price sits at the target margin, like every other paid artifact.
"""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.gtm import outbound as ob
from app.workers import outbound_tasks

SIM = "11111111-1111-1111-1111-111111111111"
ORG = "22222222-2222-2222-2222-222222222222"
ICP = "33333333-3333-3333-3333-333333333333"


class _Query:
    def __init__(self, table: str, store: dict):
        self._table = table
        self._store = store
        self._filters: dict = {}
        self._single = False

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
        self._single = True
        return self

    def execute(self):
        rows = self._store.get(self._table, [])
        matched = [r for r in rows if all(r.get(k) == v for k, v in self._filters.items())]
        if self._single:
            return SimpleNamespace(data=(matched[0] if matched else None), count=len(matched))
        return SimpleNamespace(data=matched, count=len(matched))


class _Admin:
    def __init__(self, store):
        self.store = store

    def table(self, name):
        return _Query(name, self.store)


def _objection(key, label, agents=10, score=5.0, quote="They said this."):
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
    }


def _archetype(archetype_id, label="Platform lead", weight=1.0):
    return {
        "id": archetype_id,
        "label": label,
        "weight": weight,
        "role": "Head of Platform",
        "seniority": "director",
        "budget_authority": "decision_maker",
        "incumbent_tooling": ["Datadog"],
        "evaluation_criteria": ["cost"],
        "skepticism_triggers": ["vendor benchmarks"],
        "goals": ["cut spend"],
        "pains": ["the bill"],
    }


def _store(
    objections,
    *,
    archetypes=None,
    adversarial=None,
    analysis=None,
    variants=None,
    icp_profile_id=ICP,
):
    profile = {
        "category": "observability",
        "archetypes": [_archetype("buyer-1")] if archetypes is None else archetypes,
        "adversarial": adversarial or [],
    }
    return {
        "canonical_objections": objections,
        "simulations": [{
            "id": SIM,
            "organization_id": ORG,
            "name": "Test product",
            "prediction_goal": "Would they pay?",
            "icp_profile_id": icp_profile_id,
        }],
        "icp_profiles": [{
            "id": ICP,
            "organization_id": ORG,
            "profile": profile,
            "product_summary": "It watches things.",
        }],
        "simulation_analysis": analysis or [],
        "simulation_variants": variants or [],
    }


def _generated(steps=None, notes=None):
    return ob._Generated(steps=steps or [], notes=notes or [])


def _copy_for_every_step(subject="A subject", body="Some copy."):
    """What a well-behaved model returns: one block per skeleton step."""
    return _generated([
        ob._GeneratedStep(step=touch.step, subject=subject, body=body)
        for touch in ob.SEQUENCE_SKELETON
    ])


def _install(monkeypatch, store, generated):
    monkeypatch.setattr(ob, "get_supabase_admin", lambda: _Admin(store))

    async def fake_structured(_messages, _schema):
        return generated

    monkeypatch.setattr(ob, "llm_structured", fake_structured)


def _step(sequence, number):
    return next(s for s in sequence.steps if s.step == number)


# ---------------------------------------------------------------------------
# The refusals
# ---------------------------------------------------------------------------

async def test_a_run_with_no_measured_objections_refuses(monkeypatch):
    """The failure this module exists to prevent.

    A sequence generated with nothing measured is exactly the document the
    founder would have written alone — three invented pains, hit twice each —
    with the product's name on the end of it, sent at volume to people who can
    tell the difference.
    """
    _install(monkeypatch, _store([]), _copy_for_every_step())

    with pytest.raises(ValueError, match="no measured objections"):
        await ob.build_outbound_sequences(SIM, ORG)


async def test_a_run_with_no_buyer_profile_refuses(monkeypatch):
    """One sequence per buyer archetype. With no archetypes there is nobody to
    write to, and a single "generic buyer" sequence is the failure above wearing
    a different hat."""
    _install(
        monkeypatch,
        _store([_objection("price", "Too expensive")], icp_profile_id=None),
        _copy_for_every_step(),
    )

    with pytest.raises(ValueError, match="no buyer profile"):
        await ob.build_outbound_sequences(SIM, ORG)


async def test_the_route_can_refuse_before_it_charges(monkeypatch):
    """`available_inputs` is what the route refuses on, and it must count the
    same things the builder refuses on. A route that charged and a builder that
    then declined is a product taking money for an empty document."""
    _install(monkeypatch, _store([], archetypes=[]), _copy_for_every_step())
    assert ob.available_inputs(SIM, ORG) == ob.SequenceInputs(objections=0, archetypes=0)

    _install(
        monkeypatch,
        _store([_objection("price", "Too expensive")], archetypes=[_archetype("buyer-1")]),
        _copy_for_every_step(),
    )
    assert ob.available_inputs(SIM, ORG) == ob.SequenceInputs(objections=1, archetypes=1)


# ---------------------------------------------------------------------------
# The measurement decides the pains, and carries its own numbers
# ---------------------------------------------------------------------------

async def test_the_pain_slots_follow_the_measured_ranking(monkeypatch):
    """Load-bearing order is the product; a model's sense of priority is not.

    The model is never told which objection a step answers and has no field to
    say so in, so the ranking cannot be relitigated in the copy.
    """
    _install(
        monkeypatch,
        _store([
            _objection("kills-deals", "The one that kills deals", score=9.9),
            _objection("second", "The second one", score=6.0),
            _objection("loudest", "The loud one", score=2.0),
        ]),
        # Returned in a scrambled order, to prove the assembly does not follow it.
        _generated(list(reversed(_copy_for_every_step().steps))),
    )

    pack = await ob.build_outbound_sequences(SIM, ORG)
    sequence = pack.sequences[0]

    assert sequence.pains_addressed == ["kills-deals", "second", "loudest"]
    # Slot 1 is steps 7 and 10, slot 2 is 9 and 12, slot 3 is 11 and 14.
    assert _step(sequence, 7).objection_key == "kills-deals"
    assert _step(sequence, 10).objection_key == "kills-deals"
    assert _step(sequence, 9).objection_key == "second"
    assert _step(sequence, 11).objection_key == "loudest"
    # And the steps come back in cadence order regardless of the model's order.
    assert [s.step for s in sequence.steps] == [t.step for t in ob.SEQUENCE_SKELETON]


def test_the_model_is_never_asked_which_objection_a_touch_answers():
    """The structural half of the test above: a field the model cannot fill is
    a field the model cannot get wrong."""
    assert set(ob._GeneratedStep.model_fields) == {"step", "subject", "body"}


async def test_measured_numbers_come_from_the_database_not_the_model(monkeypatch):
    """A model asked to echo a score will eventually round it."""
    _install(
        monkeypatch,
        _store([_objection("price", "Too expensive", agents=14, score=9.5, quote="Way too much.")]),
        # The copy claims its own figures. They must not reach the artifact.
        _copy_for_every_step(body="999 buyers told us this scored 0.1."),
    )

    pack = await ob.build_outbound_sequences(SIM, ORG)
    pain_step = _step(pack.sequences[0], 7)

    assert pain_step.agents_raising == 14
    assert pain_step.load_bearing_score == pytest.approx(9.5)
    assert pain_step.evidence_quotes == ["Way too much."]
    assert pain_step.objection_label == "Too expensive"


async def test_a_pain_nobody_raised_leaves_its_touches_out(monkeypatch):
    """Three slots, one measured objection. The other two slots are dropped
    rather than filled — a 16-touch sequence where three touches are about
    nothing is worse than a shorter one where every touch is about something."""
    _install(
        monkeypatch,
        _store([_objection("price", "Too expensive")]),
        _copy_for_every_step(),
    )

    pack = await ob.build_outbound_sequences(SIM, ORG)
    steps = {s.step for s in pack.sequences[0].steps}

    assert {7, 10} <= steps                      # slot 1, both angles
    assert steps.isdisjoint({9, 11, 12, 14})     # slots 2 and 3, dropped whole
    assert pack.built_from_objections == 1
    assert any("rather than 3" in note for note in pack.notes)


# ---------------------------------------------------------------------------
# The cadence is code
# ---------------------------------------------------------------------------

def test_the_skeleton_is_a_real_multi_touch_sequence():
    """The defect this pins: most sequences stop at three or four touches, which
    is why most sequences fail. A cadence generated per build could quietly
    shrink to that and nothing downstream would notice."""
    steps = [t.step for t in ob.SEQUENCE_SKELETON]
    assert steps == sorted(steps) == list(range(1, len(steps) + 1))
    assert len(steps) >= 8

    days = [t.day for t in ob.SEQUENCE_SKELETON]
    assert days == sorted(days)
    assert max(days) == 14

    assert {t.channel for t in ob.SEQUENCE_SKELETON} == {
        ob.CHANNEL_EMAIL, ob.CHANNEL_LINKEDIN, ob.CHANNEL_PHONE
    }

    # Every pain is hit twice, on two channels, and the second hit is a
    # different framing that comes later. Angle 2 restating angle 1 is why
    # sequences get ignored.
    assert ob.PAIN_SLOTS == 3
    for slot in range(1, ob.PAIN_SLOTS + 1):
        touches = [t for t in ob.SEQUENCE_SKELETON if t.pain_slot == slot]
        assert [t.angle for t in touches] == [1, 2]
        assert touches[0].step < touches[1].step
        assert touches[0].channel != touches[1].channel


async def test_a_touch_the_model_invented_is_dropped(monkeypatch):
    """The cadence is the part a founder reviewed before paying for it."""
    generated = _copy_for_every_step()
    generated.steps.append(ob._GeneratedStep(step=17, subject="Bonus", body="One more."))
    _install(monkeypatch, _store([_objection("price", "Too expensive")]), generated)

    pack = await ob.build_outbound_sequences(SIM, ORG)

    assert 17 not in {s.step for s in pack.sequences[0].steps}


async def test_a_touch_with_no_copy_is_dropped_not_rendered_empty(monkeypatch):
    """An empty card in the middle of a sequence reads as a product bug rather
    than as a model that skipped a step."""
    generated = _generated([
        s for s in _copy_for_every_step().steps if s.step != 4
    ])
    _install(monkeypatch, _store([_objection("price", "Too expensive")]), generated)

    pack = await ob.build_outbound_sequences(SIM, ORG)

    assert 4 not in {s.step for s in pack.sequences[0].steps}
    assert all(s.body.strip() for s in pack.sequences[0].steps)


async def test_only_email_steps_carry_a_subject_line(monkeypatch):
    """A LinkedIn message with a subject line is a tell that the copy was
    written for a different channel and pasted."""
    _install(
        monkeypatch,
        _store([_objection("price", "Too expensive")]),
        _copy_for_every_step(subject="Invented subject"),
    )

    pack = await ob.build_outbound_sequences(SIM, ORG)

    for step in pack.sequences[0].steps:
        if step.channel == ob.CHANNEL_EMAIL:
            assert step.subject
        else:
            assert step.subject == ""


# ---------------------------------------------------------------------------
# The winning message, and the scoreboard's right to refuse
# ---------------------------------------------------------------------------

async def test_the_winning_message_comes_from_the_variant_row(monkeypatch):
    _install(
        monkeypatch,
        _store(
            [_objection("price", "Too expensive")],
            analysis=[{
                "simulation_id": SIM,
                "organization_id": ORG,
                "artifact": {"scoreboard": {"winner_variant_key": "b", "verdict": "B wins."}},
            }],
            variants=[{
                "simulation_id": SIM,
                "organization_id": ORG,
                "variant_key": "b",
                "label": "Proof-led",
                "content": "Cut your bill without ripping anything out.",
            }],
        ),
        _copy_for_every_step(),
    )

    pack = await ob.build_outbound_sequences(SIM, ORG)

    assert pack.winning_variant_key == "b"
    assert pack.winning_variant_label == "Proof-led"
    assert pack.winning_message == "Cut your bill without ripping anything out."


async def test_a_scoreboard_that_named_no_winner_is_not_overridden(monkeypatch):
    """The scoreboard refuses whenever the top two arenas overlap, and its
    ranking is display order rather than a claim. Reading the top row anyway
    would launder sampling noise into the opening line of every email."""
    _install(
        monkeypatch,
        _store(
            [_objection("price", "Too expensive")],
            analysis=[{
                "simulation_id": SIM,
                "organization_id": ORG,
                "artifact": {"scoreboard": {
                    "winner_variant_key": None,
                    "verdict": "No winner.",
                    "variants": [{"variant_key": "a", "content": "The top row."}],
                }},
            }],
            variants=[{
                "simulation_id": SIM,
                "organization_id": ORG,
                "variant_key": "a",
                "label": "Top row",
                "content": "The top row.",
            }],
        ),
        _copy_for_every_step(),
    )

    pack = await ob.build_outbound_sequences(SIM, ORG)

    assert pack.winning_variant_key is None
    assert pack.winning_message is None
    assert any("no message test named a winner" in note.lower() for note in pack.notes)


# ---------------------------------------------------------------------------
# Who gets a sequence
# ---------------------------------------------------------------------------

async def test_the_adversarial_cohort_gets_no_sequence(monkeypatch):
    """The incumbent-aligned cohort exists so a run contains the objection a
    pure-buyer swarm misses. Writing outbound to it would hand a founder a
    sequence aimed at people whose whole position is that they are not buying."""
    _install(
        monkeypatch,
        _store(
            [_objection("price", "Too expensive")],
            archetypes=[_archetype("buyer-1")],
            adversarial=[{"id": "sunk-cost-1", "label": "Defends the incumbent", "weight": 1.0}],
        ),
        _copy_for_every_step(),
    )

    pack = await ob.build_outbound_sequences(SIM, ORG)

    assert [s.archetype_id for s in pack.sequences] == ["buyer-1"]


async def test_more_archetypes_than_the_price_covers_are_reported_not_dropped_quietly(
    monkeypatch,
):
    """A founder discovering a missing buyer by noticing the gap is much worse
    than being told the cap exists."""
    _install(
        monkeypatch,
        _store(
            [_objection("price", "Too expensive")],
            archetypes=[
                _archetype(f"buyer-{i}", weight=float(i)) for i in range(1, 7)
            ],
        ),
        _copy_for_every_step(),
    )

    pack = await ob.build_outbound_sequences(SIM, ORG)

    assert len(pack.sequences) == ob.MAX_ARCHETYPES
    # The largest share of the audience, not whichever came back first.
    assert [s.archetype_id for s in pack.sequences] == [
        "buyer-6", "buyer-5", "buyer-4", "buyer-3"
    ]
    assert any("6 buyer archetypes" in note for note in pack.notes)


# ---------------------------------------------------------------------------
# Facts, and the boundary this module may not cross
# ---------------------------------------------------------------------------

async def test_placeholders_are_counted_so_a_founder_knows_what_is_unfinished(monkeypatch):
    """A sequence full of `[TODO: your number]` is not ready to send, and the
    founder should learn that here rather than from a reply."""
    _install(
        monkeypatch,
        _store([_objection("price", "Too expensive")]),
        _copy_for_every_step(body=f"We cut it by {ob.TODO_NUMBER}, like {ob.TODO_EXAMPLE}."),
    )

    pack = await ob.build_outbound_sequences(SIM, ORG)
    sequence = pack.sequences[0]

    assert sequence.placeholders_to_fill == 2 * len(sequence.steps)


@pytest.mark.parametrize(
    "body",
    [
        "Drop me a line at ops@acme.io and we can talk.",
        "Reach me on 555-0100-2233 whenever suits.",
    ],
    ids=["email address", "phone number"],
)
async def test_copy_carrying_personal_contact_detail_is_dropped_whole(monkeypatch, body):
    """`privacy.py` is binding: no personal email, phone or postal address is
    stored anywhere in this product, and generated copy is stored like anything
    else. Dropped whole rather than trimmed, for the same reason a contact
    record is — text that needed editing to be storable came from a model that
    was inventing."""
    _install(
        monkeypatch,
        _store([_objection("price", "Too expensive")]),
        _copy_for_every_step(body=body),
    )

    pack = await ob.build_outbound_sequences(SIM, ORG)

    assert pack.sequences[0].steps == []


def test_the_artifact_has_nowhere_to_put_a_person():
    """The privacy position made structural. A field that can hold a name is a
    field something will eventually fill with one."""
    forbidden = {
        "full_name", "name", "email", "email_address", "phone", "phone_number",
        "address", "postal_address", "contact", "contacts", "public_profile_url",
        "recipient", "recipients", "employer", "role_title",
    }
    for model in (ob.OutboundStep, ob.ArchetypeSequence, ob.OutboundSequences):
        assert forbidden.isdisjoint(model.model_fields), model.__name__


def test_the_module_stores_no_contacts_and_sends_nothing():
    """Two things that must stay absent, checked in the source rather than
    asserted in a docstring: neither module reads or writes the one table that
    may hold a named person, and neither imports a transport.

    Imports are read from the parse tree rather than grepped for, so the check
    cannot be satisfied or broken by prose in a comment.
    """
    transports = {
        "smtplib", "aiosmtplib", "sendgrid", "resend", "twilio", "mailgun", "postmarker",
    }
    for module in (ob, outbound_tasks):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert 'table("gtm_contacts")' not in source, module.__name__

        imported: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert imported.isdisjoint(transports), module.__name__

        assert not [name for name in vars(module) if name.startswith("send")]


def test_personalization_is_merge_tokens_rather_than_people():
    """The founder resolves these from their own list, in their own tooling.
    Saibyl has no list to resolve them from, which is the point."""
    assert ob.MERGE_TOKENS == ("{{first_name}}", "{{company}}", "{{sender.first_name}}")
    assert "{{first_name}}" in ob.SYSTEM
    assert ob.TODO_NUMBER in ob.SYSTEM
    assert "never" in ob.SYSTEM.lower()


# ---------------------------------------------------------------------------
# Price
# ---------------------------------------------------------------------------

def test_the_sequences_are_priced_at_the_target_margin():
    from app.services.billing.agent_pricing import (
        MIN_MARGIN_PCT,
        OUTBOUND_SEQUENCE_COGS_USD,
        outbound_sequence_credits,
    )

    price = outbound_sequence_credits()
    assert price == 2_500

    # The margin floor, asserted rather than assumed: a COGS revision that
    # pushes this under the floor should fail here, not on the ledger.
    revenue = price / 1000  # credits are $0.001 of COGS by definition
    margin_pct = (revenue - float(OUTBOUND_SEQUENCE_COGS_USD)) / revenue * 100
    assert margin_pct >= float(MIN_MARGIN_PCT)


def test_the_archetype_cap_is_what_the_fixed_price_can_cover():
    """One model call per archetype against one fixed price. The cap is the
    thing stopping a six-archetype profile being served at a loss, so it may
    not drift away from the COGS figure it was derived from."""
    from app.services.billing.agent_pricing import OUTBOUND_SEQUENCE_COGS_USD

    # ≈$0.10 per archetype, sized against the report's measured per-section
    # cost of ≈$0.145 on the main model — a ceiling for a call this size.
    assert ob.MAX_ARCHETYPES * 0.10 <= float(OUTBOUND_SEQUENCE_COGS_USD)
