# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# load_run_data(simulation_id) -> RunData
# MeasuredEvent, RunData
# mean_interval(values) -> Interval
# ─────────────────────────────────────────────────────────
"""Loads a finished run into the shape the analysis passes work on.

Both the objection canonicalizer and the artifact builder need the same thing:
every measured event joined to the agent that produced it, so that a valence can
be attributed to an archetype and a quote to a username. Loading it once in one
place keeps the two passes from drifting apart on questions like "does an
off-topic event count toward the platform mean" (it does not).

`mean_interval` lives here because the same clustering rule has to apply
everywhere an average is reported: aggregate per agent first, then take the
interval across agents. See its docstring.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import structlog

from app.core.database import fetch_all, get_supabase_admin
from app.services.intelligence.analysis_schema import Interval, StanceSplit

logger = structlog.get_logger()

# Stances that represent a position on the subject. Off-topic events are
# measured and counted, but including them in a sentiment mean would let an
# agent talking about the weather pull the number toward zero.
_ON_TOPIC_STANCES = {"support", "oppose", "undecided"}

# 95% normal approximation. The t-distribution would be more correct at small n,
# but the difference is dwarfed by the model's own scoring variance, and a
# constant keeps the interval explicable to a customer.
_Z_95 = 1.96


@dataclass
class MeasuredEvent:
    id: str
    agent_id: str | None
    agent_username: str
    archetype: str
    platform: str
    round_number: int
    event_type: str
    content: str
    valence: float | None
    stance: str | None
    intensity: float | None
    intent: str | None
    is_novel_claim: bool
    objections: list[str]

    @property
    def scored(self) -> bool:
        """Has a valence and takes a position — eligible for sentiment means."""
        return self.valence is not None and self.stance in _ON_TOPIC_STANCES


@dataclass
class RunData:
    simulation_id: str
    organization_id: str
    prediction_goal: str
    max_rounds: int
    events: list[MeasuredEvent] = field(default_factory=list)
    # Every agent generated, whether or not it ever produced an event. The
    # denominator for "what share of the swarm holds this objection".
    agents_total: int = 0
    archetypes: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)
    events_total: int = 0
    events_measured: int = 0
    measurement_model: str = ""

    @property
    def scored_events(self) -> list[MeasuredEvent]:
        return [e for e in self.events if e.scored]

    @property
    def rounds_seen(self) -> list[int]:
        return sorted({e.round_number for e in self.events if e.round_number})


def _archetype_of(profile: dict[str, Any]) -> str:
    for key in ("archetype", "persona_type", "entity_type"):
        value = profile.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Unclassified"


def load_run_data(simulation_id: str) -> RunData:
    """Load a run's agents and measured events."""
    admin = get_supabase_admin()

    sim = (
        admin.table("simulations")
        .select("id, organization_id, prediction_goal, max_rounds")
        .eq("id", simulation_id)
        .single()
        .execute()
    ).data or {}

    agents = fetch_all(
        admin.table("simulation_agents")
        .select("id, username, platform, profile")
        .eq("simulation_id", simulation_id)
        .order("id")
    )

    agent_index: dict[str, dict[str, str]] = {}
    for agent in agents:
        profile = agent.get("profile") or {}
        agent_index[agent["id"]] = {
            "username": agent.get("username") or "unknown",
            "archetype": _archetype_of(profile),
        }

    rows = fetch_all(
        admin.table("simulation_events")
        .select(
            "id, agent_id, platform, round_number, event_type, content, "
            "valence, stance, intensity, intent, is_novel_claim, objections, "
            "measured_at, measure_model"
        )
        .eq("simulation_id", simulation_id)
        .order("id")
    )

    events: list[MeasuredEvent] = []
    measured = 0
    model = ""
    for row in rows:
        if row.get("measured_at"):
            measured += 1
            candidate = row.get("measure_model") or ""
            if candidate and not candidate.startswith("n/a"):
                model = candidate
        else:
            # Unmeasured events are excluded from every aggregate. Their count
            # still lands in the quality block, where a low coverage figure is
            # visible instead of quietly shrinking every denominator.
            continue

        agent = agent_index.get(row.get("agent_id") or "", {})
        raw_objections = row.get("objections")
        events.append(
            MeasuredEvent(
                id=row["id"],
                agent_id=row.get("agent_id"),
                agent_username=agent.get("username", "unknown"),
                archetype=agent.get("archetype", "Unclassified"),
                platform=row.get("platform") or "unknown",
                round_number=int(row.get("round_number") or 0),
                event_type=row.get("event_type") or "post",
                content=row.get("content") or "",
                valence=row.get("valence"),
                stance=row.get("stance"),
                intensity=row.get("intensity"),
                intent=row.get("intent"),
                is_novel_claim=bool(row.get("is_novel_claim")),
                objections=raw_objections if isinstance(raw_objections, list) else [],
            )
        )

    data = RunData(
        simulation_id=simulation_id,
        organization_id=sim.get("organization_id", ""),
        prediction_goal=sim.get("prediction_goal", ""),
        max_rounds=int(sim.get("max_rounds") or 0),
        events=events,
        agents_total=len(agents),
        archetypes=sorted({a["archetype"] for a in agent_index.values()}),
        platforms=sorted({e.platform for e in events}),
        events_total=len(rows),
        events_measured=measured,
        measurement_model=model,
    )
    logger.info(
        "run_data_loaded",
        simulation_id=simulation_id,
        agents=data.agents_total,
        events_total=data.events_total,
        events_measured=data.events_measured,
    )
    return data


def mean_interval(events: list[MeasuredEvent]) -> Interval:
    """Mean valence with a 95% interval, clustered by agent.

    Agents are the independent observations, not events. One agent posting ten
    times is one opinion repeated, and treating those ten as independent would
    shrink the interval by roughly sqrt(10) — manufacturing precision out of an
    agent's verbosity. So each agent's events are averaged first, and the
    interval is taken across the per-agent means.

    This is what "confidence bands derived from actual agent count" means: a
    25-agent run reports a visibly wider band than a 250-agent one, which is
    both true and the most honest argument for buying more agents.
    """
    per_agent: dict[str, list[float]] = {}
    for event in events:
        if not event.scored:
            continue
        key = event.agent_id or event.agent_username
        per_agent.setdefault(key, []).append(float(event.valence))

    means = [sum(vals) / len(vals) for vals in per_agent.values()]
    n = len(means)
    if n == 0:
        return Interval(mean=0.0, lower=0.0, upper=0.0, n=0)

    mean = sum(means) / n
    if n == 1:
        # One agent is an anecdote. Reporting a zero-width interval around it
        # would claim certainty from a single observation, so the band spans
        # the full scale.
        return Interval(mean=round(mean, 4), lower=-1.0, upper=1.0, n=1)

    variance = sum((m - mean) ** 2 for m in means) / (n - 1)
    half_width = _Z_95 * math.sqrt(variance / n)
    return Interval(
        mean=round(mean, 4),
        lower=round(max(-1.0, mean - half_width), 4),
        upper=round(min(1.0, mean + half_width), 4),
        n=n,
    )


def stance_split(events: list[MeasuredEvent]) -> StanceSplit:
    """Share of measured, content-bearing events taking each stance."""
    counts = {"support": 0, "oppose": 0, "undecided": 0, "off_topic": 0}
    total = 0
    for event in events:
        if event.stance in counts:
            counts[event.stance] += 1
            total += 1
    if total == 0:
        return StanceSplit()
    return StanceSplit(
        support_pct=round(counts["support"] * 100 / total, 2),
        oppose_pct=round(counts["oppose"] * 100 / total, 2),
        undecided_pct=round(counts["undecided"] * 100 / total, 2),
        off_topic_pct=round(counts["off_topic"] * 100 / total, 2),
    )


def mean_intensity(events: list[MeasuredEvent]) -> float:
    values = [e.intensity for e in events if e.intensity is not None]
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)
