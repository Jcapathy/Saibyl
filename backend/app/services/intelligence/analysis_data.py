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
from app.services.engine.variants import DEFAULT_VARIANT_KEY, Arena, load_arenas
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

    # Which arena produced this. Under matched swarms the same agent appears in
    # every arena, so `variant` is the only thing separating an agent's reaction
    # to variant A from its reaction to variant B — grouping by agent alone
    # would average a marketer's six headlines into one number.
    variant: str = DEFAULT_VARIANT_KEY
    # What this replied to or reacted to, as an event id. None for a top-level
    # post and for every event written before migration 022.
    target_event_id: str | None = None
    # What the agent came away believing the subject said, in its own words.
    # Compared against the variant's actual copy for takeaway accuracy — the
    # PRD §6 metric reported on every objective.
    takeaway: str | None = None
    # Which side of the room the agent that produced this is on. Read from the
    # agent row rather than inferred from the archetype label — a
    # label-matching rule would break the first time a founder renames an
    # archetype in their ICP.
    is_adversarial: bool = False
    adversarial_role: str | None = None

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

    # ── The adversarial cohort, as it actually ran ──────────────────────
    # Agents allocated to the cohort, not events produced by it. A cohort that
    # was allocated 40 agents and spoke twice is a finding, and it is only
    # visible if the denominator is the allocation.
    agents_adversarial: int = 0
    adversarial_archetypes: list[str] = field(default_factory=list)
    # adversarial_role -> agent count.
    adversarial_roles: dict[str, int] = field(default_factory=dict)
    # What the run was configured with, before weight rounding.
    adversarial_share_configured: float = 0.0
    # Competitors named in this run's ICP, grounded in uploaded material. Empty
    # when the cohort ran with no named entity, which is the normal case.
    named_competitors: list[str] = field(default_factory=list)

    lens: str | None = None
    founder_stage: str | None = None
    # Set when this run is an inoculation re-simulation. Its canonicalization
    # clusters against the parent's objections so the two runs' keys line up.
    parent_simulation_id: str | None = None

    # ── The Marketing lens ──────────────────────────────────────────────
    # What winning means for this run. None on every Founder- and Crisis-lens
    # run, where sentiment stays the headline — which is also what every run
    # created before Phase 3 reads as.
    objective: str | None = None
    # The arenas this run executed, in display order. Empty on a single-arena
    # run: one arena is not a comparison, and an artifact carrying a
    # one-variant scoreboard invites a reader to treat it as one.
    arenas: list[Arena] = field(default_factory=list)

    @property
    def is_multi_variant(self) -> bool:
        return len(self.arenas) > 1

    def events_for(self, variant_key: str) -> list[MeasuredEvent]:
        return [e for e in self.events if e.variant == variant_key]

    @property
    def scored_events(self) -> list[MeasuredEvent]:
        return [e for e in self.events if e.scored]

    @property
    def rounds_seen(self) -> list[int]:
        return sorted({e.round_number for e in self.events if e.round_number})

    @property
    def has_adversarial_cohort(self) -> bool:
        return self.agents_adversarial > 0


def _archetype_of(profile: dict[str, Any]) -> str:
    for key in ("archetype", "persona_type", "entity_type"):
        value = profile.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Unclassified"


def _named_competitors(icp_profile_id: str | None) -> list[str]:
    """Competitors this run's ICP named, and only the grounded ones.

    Read back from `icp_profiles` rather than from the agents, because the
    disclosure has to name what the run was *entitled* to name. An ungrounded
    competitor never reaches an agent — `_ground_adversarial` strips it — so
    filtering on `mentioned_in` here reproduces the same rule at the point where
    the run is described to a reader.
    """
    if not icp_profile_id:
        return []
    try:
        rows = (
            get_supabase_admin()
            .table("icp_profiles")
            .select("competitors")
            .eq("id", icp_profile_id)
            .limit(1)
            .execute()
        ).data or []
    except Exception:
        logger.warning("named_competitors_lookup_failed", icp_profile_id=icp_profile_id)
        return []
    if not rows:
        return []

    competitors = rows[0].get("competitors") or []
    return sorted({
        str(c.get("name")).strip()
        for c in competitors
        if isinstance(c, dict) and c.get("name") and c.get("mentioned_in")
    })


def _configured_arenas(simulation_id: str, prediction_goal: str) -> list[Arena]:
    """The run's arenas, or an empty list when it only ever had one.

    `load_arenas` never returns empty — the runner must always have something to
    execute. The artifact wants the opposite: a single-arena run has no
    comparison to report, and handing the viewer a one-row scoreboard invites a
    reader to treat one variant as a result.
    """
    arenas = load_arenas(simulation_id, prediction_goal)
    return arenas if len(arenas) > 1 else []


def load_run_data(simulation_id: str) -> RunData:
    """Load a run's agents and measured events."""
    admin = get_supabase_admin()

    sim = (
        admin.table("simulations")
        .select(
            "id, organization_id, prediction_goal, max_rounds, lens, objective, "
            "founder_stage, adversarial_share, icp_profile_id, parent_simulation_id"
        )
        .eq("id", simulation_id)
        .single()
        .execute()
    ).data or {}

    agents = fetch_all(
        admin.table("simulation_agents")
        .select("id, username, platform, profile, is_adversarial, adversarial_role")
        .eq("simulation_id", simulation_id)
        .order("id")
    )

    agent_index: dict[str, dict[str, Any]] = {}
    adversarial_archetypes: set[str] = set()
    adversarial_roles: dict[str, int] = {}
    agents_adversarial = 0
    for agent in agents:
        profile = agent.get("profile") or {}
        archetype = _archetype_of(profile)
        # The column is authoritative; the profile copy is a fallback for agents
        # created before migration 020, which are all non-adversarial anyway.
        is_adversarial = bool(
            agent.get("is_adversarial") or profile.get("is_adversarial")
        )
        role = agent.get("adversarial_role") or profile.get("adversarial_role")
        if is_adversarial:
            agents_adversarial += 1
            adversarial_archetypes.add(archetype)
            if role:
                adversarial_roles[role] = adversarial_roles.get(role, 0) + 1
        agent_index[agent["id"]] = {
            "username": agent.get("username") or "unknown",
            "archetype": archetype,
            "is_adversarial": is_adversarial,
            "adversarial_role": role,
        }

    rows = fetch_all(
        admin.table("simulation_events")
        .select(
            "id, agent_id, platform, variant, target_event_id, round_number, "
            "event_type, content, valence, stance, intensity, intent, takeaway, "
            "is_novel_claim, objections, measured_at, measure_model"
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
                # Every event written before Phase 3 carries "a", so a historical
                # run reads as a single-arena run rather than as an unlabelled one.
                variant=row.get("variant") or DEFAULT_VARIANT_KEY,
                target_event_id=row.get("target_event_id"),
                takeaway=row.get("takeaway"),
                is_adversarial=bool(agent.get("is_adversarial")),
                adversarial_role=agent.get("adversarial_role"),
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
        agents_adversarial=agents_adversarial,
        adversarial_archetypes=sorted(adversarial_archetypes),
        adversarial_roles=adversarial_roles,
        adversarial_share_configured=float(sim.get("adversarial_share") or 0.0),
        named_competitors=_named_competitors(sim.get("icp_profile_id")),
        lens=sim.get("lens"),
        founder_stage=sim.get("founder_stage"),
        parent_simulation_id=sim.get("parent_simulation_id"),
        objective=sim.get("objective"),
        # Read from the configured variants rather than from the distinct
        # `variant` values on the events. An arena that produced zero events is
        # a finding — a variant nobody engaged with — and deriving the list from
        # the events would delete it from the scoreboard instead of showing it
        # scoring nothing.
        arenas=_configured_arenas(
            simulation_id, sim.get("prediction_goal", "")
        ),
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
