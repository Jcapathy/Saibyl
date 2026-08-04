"""Every objection key the artifact names is an objection the artifact carries.

The artifact is the only source of rendered numbers. Everything downstream — the
report viewer, the print page, the exporter, the ReAct tools — reads it and
nothing else, and reads it by *key*: a slice says `top_objection_keys`, a
flashpoint says `objection_keys`, and the renderer looks each one up in
`objections`.

Truncation used to happen last. `objections` was cut to twenty *after* every
slice builder had already run against the full list, so a platform slice could
name the 31st-ranked objection and the artifact did not contain it. The lookup
returns nothing, the renderer shows a blank or throws, and the failure is the
frontend/backend mismatch class this build keeps hitting — a field pointing at
an object that is not there.
"""
from __future__ import annotations

import pytest

from app.services.intelligence import analysis_builder
from app.services.intelligence.analysis_builder import (
    MAX_OBJECTIONS_IN_ARTIFACT,
    build_simulation_analysis,
)
from app.services.intelligence.analysis_data import MeasuredEvent, RunData
from app.services.intelligence.analysis_schema import Interval, ObjectionSummary

_PLATFORMS = ("hacker_news", "reddit")
_ARCHETYPES = ("Buyer", "Incumbent user")


def _event(index: int) -> MeasuredEvent:
    return MeasuredEvent(
        id=f"e{index}",
        agent_id=f"agent-{index}",
        agent_username=f"agent-{index}",
        archetype=_ARCHETYPES[index % 2],
        platform=_PLATFORMS[index % 2],
        # Two rounds, and the second swings hard so a flashpoint is produced —
        # `Flashpoint.objection_keys` is one of the fields that could name a
        # truncated objection.
        round_number=1 if index < 30 else 2,
        event_type="post",
        content="text",
        valence=0.8 if index < 30 else -0.8,
        stance="support" if index < 30 else "oppose",
        intensity=0.6,
        intent=None,
        is_novel_claim=False,
        objections=["objection"],
        is_adversarial=index % 2 == 1,
        adversarial_role="incumbent_power_user" if index % 2 else None,
    )


def _objection(rank: int, event_ids: list[str]) -> ObjectionSummary:
    """Rank 0 is the heaviest; the artifact keeps the top twenty."""
    return ObjectionSummary(
        key=f"objection-{rank:02d}",
        label=f"Objection {rank}",
        summary="",
        event_ids=event_ids,
        agent_count=len(event_ids),
        event_count=len(event_ids),
        first_round_seen=1,
        load_bearing_score=100.0 - rank,
    )


def _artifact(monkeypatch):
    events = [_event(i) for i in range(60)]
    run = RunData(
        simulation_id="sim-1",
        organization_id="org-1",
        prediction_goal="goal",
        max_rounds=2,
        events=events,
        agents_total=60,
        agents_adversarial=30,
        adversarial_archetypes=["Incumbent user"],
        archetypes=list(_ARCHETYPES),
        platforms=list(_PLATFORMS),
        events_total=60,
        events_measured=60,
        measurement_model="test",
    )

    # More objections than the artifact carries, split so that the ones past the
    # cut are the **only** objections touching one platform and one cohort.
    #
    # That split is the point. `_objection_keys_for` walks the list in rank
    # order, so a fixture where every objection touches every slice hides the
    # defect behind the heaviest twenty. A slice whose events belong only to
    # low-ranked objections is what actually happens on a real run — the reddit
    # half of a two-platform run raising objections the hacker_news half did
    # not — and it is what put a truncated key into a rendered field.
    hacker_news = [e.id for e in events if e.platform == "hacker_news"]
    reddit = [e.id for e in events if e.platform == "reddit"]
    total = MAX_OBJECTIONS_IN_ARTIFACT + 15
    objections = [
        _objection(
            rank,
            (hacker_news if rank < MAX_OBJECTIONS_IN_ARTIFACT else reddit)[rank % 8 :: 8],
        )
        for rank in range(total)
    ]

    async def _canonicalize(_run, _priors=None):
        return objections

    monkeypatch.setattr(analysis_builder, "load_run_data", lambda _id: run)
    monkeypatch.setattr(analysis_builder, "canonicalize_objections", _canonicalize)
    monkeypatch.setattr(analysis_builder, "prior_objections", lambda _id: [])
    monkeypatch.setattr(analysis_builder, "persist_objections", lambda *_a: None)
    monkeypatch.setattr(analysis_builder, "build_scoreboard", lambda _run: None)
    monkeypatch.setattr(analysis_builder, "_persist", lambda *_a: None)
    return objections


@pytest.mark.asyncio
async def test_no_slice_names_an_objection_the_artifact_does_not_carry(monkeypatch):
    _artifact(monkeypatch)

    analysis = await build_simulation_analysis("sim-1", "org-1")

    carried = {o.key for o in analysis.objections}
    assert len(carried) == MAX_OBJECTIONS_IN_ARTIFACT

    named: set[str] = set()
    for slice_ in (*analysis.by_platform, *analysis.by_archetype, *analysis.by_cohort):
        named.update(slice_.top_objection_keys)
    for flashpoint in analysis.flashpoints:
        named.update(flashpoint.objection_keys)
    for edge in analysis.propagation:
        named.add(edge.objection_key)
    if analysis.headline.top_objection_key:
        named.add(analysis.headline.top_objection_key)

    assert named, "the fixture produced no key references, so it guards nothing"
    assert named <= carried, sorted(named - carried)


@pytest.mark.asyncio
async def test_the_artifact_keeps_the_heaviest_objections(monkeypatch):
    """The cut is the tail. Truncating the front would drop the finding."""
    objections = _artifact(monkeypatch)

    analysis = await build_simulation_analysis("sim-1", "org-1")

    assert [o.key for o in analysis.objections] == [
        o.key for o in objections[:MAX_OBJECTIONS_IN_ARTIFACT]
    ]


@pytest.mark.asyncio
async def test_the_full_set_is_still_persisted(monkeypatch):
    """`canonical_objections` is what the inoculation loop's priors and asset
    drafting read from. Truncating it there would drop objections the artifact
    never claimed to carry in the first place."""
    objections = _artifact(monkeypatch)
    persisted: list[list[ObjectionSummary]] = []
    monkeypatch.setattr(
        analysis_builder,
        "persist_objections",
        lambda _run, objs: persisted.append(objs),
    )

    await build_simulation_analysis("sim-1", "org-1")

    assert len(persisted[0]) == len(objections) > MAX_OBJECTIONS_IN_ARTIFACT


def test_an_interval_is_still_an_interval():
    """Guards the fixture, not the code: a zero-width interval would make every
    flashpoint significant and quietly weaken the test above."""
    assert Interval(mean=0.0, lower=-0.1, upper=0.1, n=2).width == pytest.approx(0.2)
