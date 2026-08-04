# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# build_simulation_analysis(simulation_id, organization_id) -> SimulationAnalysis
# get_analysis(simulation_id) -> dict | None
# ─────────────────────────────────────────────────────────
"""Builds the `simulation_analysis` artifact — the only source of rendered numbers.

The pipeline is: measure every event from its content, cluster the objections,
then aggregate both into one typed artifact. Everything downstream — the report
viewer, the print page, the exporter, and from Phase 2 the Founder lens — reads
this artifact and nothing else. That constraint is what makes it possible to
state that a number is measured: there is exactly one place it could have come
from.

The aggregates here deliberately refuse to fill gaps. If a round produced no
scored events, it is absent from the timeline rather than interpolated. If one
agent carried a platform, that platform's interval spans the full scale. V1
produced a smooth, plausible, entirely synthetic curve; a gap that is visibly a
gap is worth more than a curve that is quietly invented.
"""
from __future__ import annotations

from datetime import UTC, datetime

import structlog

from app.core.database import get_supabase_admin
from app.services.intelligence.analysis_data import (
    MeasuredEvent,
    RunData,
    load_run_data,
    mean_intensity,
    mean_interval,
    stance_split,
)
from app.services.intelligence.analysis_schema import (
    SCHEMA_VERSION,
    AdversarialDisclosure,
    ArchetypeSlice,
    CohortSlice,
    Flashpoint,
    Headline,
    ObjectionSummary,
    PlatformSlice,
    PropagationEdge,
    QualityBlock,
    SimulationAnalysis,
    TimelinePoint,
)
from app.services.intelligence.objection_canonicalizer import (
    canonicalize_objections,
    persist_objections,
    prior_objections,
)
from app.services.intelligence.variant_scoreboard import build_scoreboard

logger = structlog.get_logger()

# A round-to-round move smaller than this is not called a flashpoint even when
# it clears the confidence bands. Below it the shift is real but not actionable,
# and a report that flags six of them flags nothing.
FLASHPOINT_MIN_DELTA = 0.15

# Interval widths that separate the three confidence labels. A 25-agent run
# lands in "low" and is told so; that is the honest read, not a defect.
_CI_WIDTH_MODERATE = 0.50
_CI_WIDTH_HIGH = 0.25

# Objections carried in the artifact. Applied **once**, before any slice
# builder sees the list — see `build_simulation_analysis`. The full set is
# persisted to `canonical_objections` either way.
MAX_OBJECTIONS_IN_ARTIFACT = 20


def _timeline(run: RunData) -> list[TimelinePoint]:
    by_round: dict[int, list[MeasuredEvent]] = {}
    for event in run.events:
        by_round.setdefault(event.round_number, []).append(event)

    points: list[TimelinePoint] = []
    for round_number in sorted(by_round):
        events = by_round[round_number]
        scored = [e for e in events if e.scored]
        if not scored:
            # No measured opinion this round. Omitted rather than carried
            # forward — a flat segment would read as "sentiment held steady".
            continue
        points.append(
            TimelinePoint(
                round_number=round_number,
                valence=mean_interval(scored),
                stance=stance_split(events),
                mean_intensity=mean_intensity(events),
                event_count=len(events),
                agent_count=len({e.agent_id or e.agent_username for e in events}),
                novel_claim_count=sum(1 for e in events if e.is_novel_claim),
            )
        )
    return points


def _objection_keys_for(
    events: list[MeasuredEvent], objections: list[ObjectionSummary], limit: int = 3
) -> list[str]:
    """The load-bearing objections present in this slice, in global rank order."""
    event_ids = {e.id for e in events}
    return [
        o.key for o in objections if event_ids.intersection(o.event_ids)
    ][:limit]


def _by_platform(
    run: RunData, objections: list[ObjectionSummary]
) -> list[PlatformSlice]:
    grouped: dict[str, list[MeasuredEvent]] = {}
    for event in run.events:
        grouped.setdefault(event.platform, []).append(event)

    slices = [
        PlatformSlice(
            platform=platform,
            valence=mean_interval(events),
            stance=stance_split(events),
            mean_intensity=mean_intensity(events),
            event_count=len(events),
            agent_count=len({e.agent_id or e.agent_username for e in events}),
            top_objection_keys=_objection_keys_for(events, objections),
        )
        for platform, events in grouped.items()
    ]
    # Most negative first: the platform where this is going worst is the one the
    # reader needs on screen before they scroll.
    slices.sort(key=lambda s: s.valence.mean)
    return slices


def _by_archetype(
    run: RunData, objections: list[ObjectionSummary]
) -> list[ArchetypeSlice]:
    grouped: dict[str, list[MeasuredEvent]] = {}
    for event in run.events:
        grouped.setdefault(event.archetype, []).append(event)

    slices = [
        ArchetypeSlice(
            archetype=archetype,
            valence=mean_interval(events),
            stance=stance_split(events),
            mean_intensity=mean_intensity(events),
            event_count=len(events),
            agent_count=len({e.agent_id or e.agent_username for e in events}),
            top_objection_keys=_objection_keys_for(events, objections),
        )
        for archetype, events in grouped.items()
    ]
    slices.sort(key=lambda s: s.valence.mean)
    return slices


def _by_cohort(
    run: RunData, objections: list[ObjectionSummary]
) -> list[CohortSlice]:
    """Buyers versus incumbent-aligned agents.

    Empty when the run had no adversarial cohort: a one-sided split is not a
    split, and rendering "buyers: 100%" is noise a reader has to skip past.
    """
    if not run.has_adversarial_cohort:
        return []

    grouped: dict[str, list[MeasuredEvent]] = {"buyer": [], "adversarial": []}
    for event in run.events:
        grouped["adversarial" if event.is_adversarial else "buyer"].append(event)

    totals = {
        "adversarial": run.agents_adversarial,
        "buyer": max(0, run.agents_total - run.agents_adversarial),
    }
    archetypes = {
        "adversarial": run.adversarial_archetypes,
        "buyer": [a for a in run.archetypes if a not in set(run.adversarial_archetypes)],
    }

    return [
        CohortSlice(
            cohort=cohort,  # type: ignore[arg-type]
            valence=mean_interval(events),
            stance=stance_split(events),
            mean_intensity=mean_intensity(events),
            event_count=len(events),
            agent_count=len({e.agent_id or e.agent_username for e in events}),
            agents_total=totals[cohort],
            archetypes=archetypes[cohort],
            top_objection_keys=_objection_keys_for(events, objections),
        )
        for cohort, events in (("buyer", grouped["buyer"]), ("adversarial", grouped["adversarial"]))
    ]


def _attribute_objection_cohorts(
    run: RunData, objections: list[ObjectionSummary]
) -> None:
    """Record, per objection, which side of the room raised it and who repeated it.

    "Competitor advocates start the narrative decline" is the second argument
    for the cohort existing at all (PRD §4). It is a claim about origin and
    spread, so it is only checkable if the artifact records both — and an
    objection that starts adversarial and never leaves that cohort is a
    competitor talking to themselves, which is a very different finding from one
    that crosses into buyers.

    Mutates in place: these fields belong to the objection, and returning
    copies would leave the canonicalizer's list and the artifact's list as two
    objects that have to be kept in step.
    """
    if not run.has_adversarial_cohort:
        return

    events_by_id = {e.id: e for e in run.events}
    for objection in objections:
        events = [events_by_id[eid] for eid in objection.event_ids if eid in events_by_id]
        if not events:
            continue

        adversarial_agents = {
            e.agent_id or e.agent_username for e in events if e.is_adversarial
        }
        buyer_agents = {
            e.agent_id or e.agent_username for e in events if not e.is_adversarial
        }
        objection.adversarial_agent_count = len(adversarial_agents)
        objection.buyer_agent_count = len(buyer_agents)

        first_round = min(e.round_number for e in events)
        first_voices = [e for e in events if e.round_number == first_round]
        # Originated adversarial only when *every* first-round voice was
        # adversarial. A mixed first round means the objection was already in
        # the market's mouth, and crediting the incumbent for it would
        # overstate the cohort's influence — which is the direction this
        # feature is most likely to be wrong in.
        objection.originated_adversarial = all(e.is_adversarial for e in first_voices)


def _adversarial_disclosure(run: RunData) -> AdversarialDisclosure:
    """The standing synthetic-agent label, composed once for every renderer.

    PRD §4 requires adversarial agents to be labelled synthetic in every report
    and export. Composing the sentence here rather than in each renderer is the
    difference between one obligation and four opportunities to forget it.
    """
    if not run.has_adversarial_cohort:
        return AdversarialDisclosure()

    realised = (
        round(run.agents_adversarial / run.agents_total, 4) if run.agents_total else 0.0
    )
    active = len({
        e.agent_id or e.agent_username for e in run.events if e.is_adversarial
    })

    named = (
        f" Competitor names appear only where the material uploaded to this "
        f"project named them ({', '.join(run.named_competitors)}); no claim about "
        f"a real company originates from the model."
        if run.named_competitors
        else " No competitor was named: the cohort argues about the category and "
        "the cost of switching, with no real company involved."
    )

    return AdversarialDisclosure(
        enabled=True,
        share_configured=run.adversarial_share_configured,
        share_realised=realised,
        agents_total=run.agents_adversarial,
        agents_active=active,
        archetypes=run.adversarial_archetypes,
        roles=run.adversarial_roles,
        named_competitors=run.named_competitors,
        disclosure=(
            f"{run.agents_adversarial} of {run.agents_total} agents "
            f"({realised * 100:.0f}%) were configured as incumbent-aligned: they "
            f"argue against adopting the subject by construction. They are "
            f"synthetic, like every agent in this run, and their reactions are "
            f"reported separately from buyers' so the headline can be read "
            f"either way.{named}"
        ),
    )


def _flashpoints(
    run: RunData, timeline: list[TimelinePoint], objections: list[ObjectionSummary]
) -> list[Flashpoint]:
    """Rounds where sentiment moved, with the events that moved it.

    A move counts as significant only when the two rounds' confidence intervals
    do not overlap. Non-overlapping intervals are a conservative test — they
    imply a significant difference but can miss a real one — and being told
    "this might be noise" about a true shift is a cheaper mistake than acting on
    a shift that was noise.
    """
    events_by_round: dict[int, list[MeasuredEvent]] = {}
    for event in run.events:
        events_by_round.setdefault(event.round_number, []).append(event)

    points: list[Flashpoint] = []
    for prev, curr in zip(timeline, timeline[1:], strict=False):
        delta = curr.valence.mean - prev.valence.mean
        if abs(delta) < FLASHPOINT_MIN_DELTA:
            continue

        significant = (
            curr.valence.lower > prev.valence.upper
            or curr.valence.upper < prev.valence.lower
        )

        round_events = events_by_round.get(curr.round_number, [])
        # The events that pushed it: the ones moving in the same direction as
        # the shift, hardest first.
        movers = [
            e for e in round_events
            if e.scored and ((e.valence < prev.valence.mean) == (delta < 0))
        ]
        movers.sort(key=lambda e: abs(e.valence - prev.valence.mean), reverse=True)
        trigger_ids = [e.id for e in movers[:8]]

        direction = "fell" if delta < 0 else "rose"
        qualifier = "" if significant else " (within the confidence bands — treat as directional)"
        points.append(
            Flashpoint(
                round_number=curr.round_number,
                valence_before=prev.valence.mean,
                valence_after=curr.valence.mean,
                delta=round(delta, 4),
                significant=significant,
                trigger_event_ids=trigger_ids,
                objection_keys=_objection_keys_for(movers[:8], objections),
                description=(
                    f"Sentiment {direction} {abs(delta):.2f} between round "
                    f"{prev.round_number} and {curr.round_number}{qualifier}."
                ),
            )
        )

    points.sort(key=lambda f: (not f.significant, -abs(f.delta)))
    return points


def _propagation(objections: list[ObjectionSummary], run: RunData) -> list[PropagationEdge]:
    """Where each objection started and which groups it reached later.

    Escaping the originating cohort is the single most important thing an
    objection can do — one confined to its cohort is a complaint, one that
    reaches neutral buyers is a problem — so the graph is edges out of the
    origin rather than a full co-occurrence mesh.
    """
    events_by_id = {e.id: e for e in run.events}
    edges: list[PropagationEdge] = []

    for objection in objections:
        events = [events_by_id[eid] for eid in objection.event_ids if eid in events_by_id]
        if not events:
            continue

        for kind, attr in (("archetype", "archetype"), ("platform", "platform")):
            first_seen: dict[str, int] = {}
            for event in events:
                group = getattr(event, attr)
                first_seen[group] = min(
                    first_seen.get(group, event.round_number), event.round_number
                )
            if len(first_seen) < 2:
                continue

            origin = min(first_seen.items(), key=lambda kv: kv[1])
            for group, round_number in sorted(first_seen.items(), key=lambda kv: kv[1]):
                if group == origin[0]:
                    continue
                edges.append(
                    PropagationEdge(
                        objection_key=objection.key,
                        from_group=origin[0],
                        to_group=group,
                        group_kind=kind,  # type: ignore[arg-type]
                        first_round=round_number,
                        event_ids=[
                            e.id for e in events
                            if getattr(e, attr) == group
                            and e.round_number == round_number
                        ][:5],
                    )
                )
    return edges


def _headline(
    run: RunData, timeline: list[TimelinePoint], objections: list[ObjectionSummary]
) -> Headline:
    scored = run.scored_events
    overall = mean_interval(scored)

    polarization = 0.0
    if scored:
        opposite = sum(
            1 for e in scored
            if (e.valence < 0) != (overall.mean < 0) and e.valence != 0
        )
        polarization = round(opposite * 100 / len(scored), 2)

    novel_pct = 0.0
    if run.events:
        novel_pct = round(
            sum(1 for e in run.events if e.is_novel_claim) * 100 / len(run.events), 2
        )

    trajectory: str = "flat"
    delta = 0.0
    if len(timeline) >= 2:
        first, last = timeline[0], timeline[-1]
        delta = round(last.valence.mean - first.valence.mean, 4)
        # Only called improving or declining when the endpoints' intervals do
        # not overlap. Otherwise the run drifted inside its own noise and
        # naming a direction would be a claim the data does not support.
        if last.valence.lower > first.valence.upper:
            trajectory = "improving"
        elif last.valence.upper < first.valence.lower:
            trajectory = "declining"

    return Headline(
        valence=overall,
        stance=stance_split(run.events),
        mean_intensity=mean_intensity(run.events),
        polarization_pct=polarization,
        novel_claim_pct=novel_pct,
        trajectory=trajectory,  # type: ignore[arg-type]
        trajectory_delta=delta,
        top_objection_key=objections[0].key if objections else None,
    )


def _quality(run: RunData, timeline: list[TimelinePoint], overall_n: int) -> QualityBlock:
    coverage = (
        round(run.events_measured * 100 / run.events_total, 2)
        if run.events_total
        else 0.0
    )
    widths = [p.valence.upper - p.valence.lower for p in timeline]
    mean_width = round(sum(widths) / len(widths), 4) if widths else 2.0

    if mean_width <= _CI_WIDTH_HIGH:
        confidence = "high"
    elif mean_width <= _CI_WIDTH_MODERATE:
        confidence = "moderate"
    else:
        confidence = "low"

    caveats: list[str] = []
    if coverage < 95:
        caveats.append(
            f"{round(100 - coverage, 1)}% of events could not be measured and are "
            "excluded from every figure here."
        )
    if overall_n < 30:
        caveats.append(
            f"{overall_n} agents produced measurable opinions. Intervals are wide "
            "at this swarm size — treat differences smaller than the bands as "
            "unresolved."
        )
    if len(timeline) < 2:
        caveats.append(
            "Fewer than two rounds produced measurable opinion, so no trajectory "
            "is reported."
        )
    contentless = run.events_measured - len(run.scored_events)
    if contentless > 0 and run.events_measured:
        caveats.append(
            f"{contentless} events were reactions or off-topic; they count as "
            "engagement but carry no sentiment."
        )
    if run.has_adversarial_cohort and run.agents_total:
        # The headline mixes both cohorts, which is the right default — a real
        # thread contains both — but a reader who does not know that will read a
        # configured hostility share as a market measurement. Said here because
        # this is the block the viewer puts next to the headline number.
        share = run.agents_adversarial * 100 / run.agents_total
        caveats.append(
            f"{share:.0f}% of this swarm was configured as incumbent-aligned and "
            "argues against adoption by construction. The headline includes them; "
            "the cohort breakdown separates them."
        )

    return QualityBlock(
        events_total=run.events_total,
        events_measured=run.events_measured,
        coverage_pct=coverage,
        agents_total=run.agents_total,
        agents_active=len({e.agent_id or e.agent_username for e in run.events}),
        rounds=len(timeline),
        measurement_model=run.measurement_model,
        mean_ci_width=mean_width,
        confidence=confidence,  # type: ignore[arg-type]
        caveats=caveats,
    )


async def build_simulation_analysis(
    simulation_id: str, organization_id: str
) -> SimulationAnalysis:
    """Build and persist the analysis artifact for a finished run."""
    run = load_run_data(simulation_id)

    # A re-simulation clusters against its parent's canonical objections so the
    # two runs' keys line up. Without this the before/after comparison matches
    # nothing and reports every asset as effective — see canonicalize_objections.
    objections = await canonicalize_objections(
        run, prior_objections(run.parent_simulation_id)
    )
    # Cohort attribution runs before persistence so the stored objections and
    # the artifact's copies agree on where each objection started.
    _attribute_objection_cohorts(run, objections)
    # Persisted in full. `canonical_objections` is the table the inoculation
    # loop's priors and asset drafting read from, and truncating it there would
    # drop objections the artifact never claimed to carry.
    persist_objections(run, objections)

    # **Truncated once, before anything reads it.** Every slice builder emits
    # `top_objection_keys` by looking the slice's events up in this list, so
    # handing them the full list and truncating only the `objections` field
    # produced slices naming keys the artifact does not contain — a field
    # pointing at an object that is not there, which is the frontend/backend
    # mismatch class this build keeps hitting. The list is already sorted by
    # load-bearing score, so the cut is the tail.
    artifact_objections = objections[:MAX_OBJECTIONS_IN_ARTIFACT]

    timeline = _timeline(run)
    headline = _headline(run, timeline, artifact_objections)

    analysis = SimulationAnalysis(
        schema_version=SCHEMA_VERSION,
        simulation_id=simulation_id,
        generated_at=datetime.now(UTC),
        headline=headline,
        sentiment_timeline=timeline,
        by_platform=_by_platform(run, artifact_objections),
        by_archetype=_by_archetype(run, artifact_objections),
        by_cohort=_by_cohort(run, artifact_objections),
        objections=artifact_objections,
        flashpoints=_flashpoints(run, timeline, artifact_objections),
        propagation=_propagation(artifact_objections, run),
        adversarial=_adversarial_disclosure(run),
        # None on every single-arena run. Built last because it is the one block
        # that reads the run's arenas rather than only its events.
        scoreboard=build_scoreboard(run),
        quality=_quality(run, timeline, headline.valence.n),
    )

    _persist(analysis, run, organization_id)
    logger.info(
        "analysis_built",
        simulation_id=simulation_id,
        rounds=len(timeline),
        objections=len(objections),
        # Persisted against carried. No silent caps: a run whose tail was cut
        # should say so rather than let the artifact read as the whole set.
        objections_in_artifact=len(artifact_objections),
        flashpoints=len(analysis.flashpoints),
        coverage_pct=analysis.quality.coverage_pct,
        confidence=analysis.quality.confidence,
        adversarial_agents=run.agents_adversarial,
        objections_crossing_from_adversarial=sum(
            1 for o in analysis.objections if o.crossed_into_buyers
        ),
        variants=len(run.arenas),
        # Logged rather than only stored: a run that produced a scoreboard with
        # no winner is the normal, honest outcome of an underpowered test, and
        # it should be visible without opening the artifact.
        scoreboard_winner=(
            analysis.scoreboard.winner_variant_key if analysis.scoreboard else None
        ),
    )
    return analysis


def _persist(
    analysis: SimulationAnalysis, run: RunData, organization_id: str
) -> None:
    admin = get_supabase_admin()
    payload = {
        "simulation_id": analysis.simulation_id,
        "organization_id": organization_id or run.organization_id,
        "schema_version": analysis.schema_version,
        "artifact": analysis.model_dump(mode="json"),
        "events_total": analysis.quality.events_total,
        "events_measured": analysis.quality.events_measured,
        "agents_total": analysis.quality.agents_total,
        "build_status": "complete",
        "error_message": None,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    admin.table("simulation_analysis").upsert(
        payload, on_conflict="simulation_id"
    ).execute()


def get_analysis(simulation_id: str) -> dict | None:
    """Read a stored artifact. Returns None when the run has not been analysed."""
    admin = get_supabase_admin()
    rows = (
        admin.table("simulation_analysis")
        .select("*")
        .eq("simulation_id", simulation_id)
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None
