# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# score_simulation(simulation_id) -> SimulationQualityScore
# ─────────────────────────────────────────────────────────
from __future__ import annotations

from uuid import UUID

import structlog
from pydantic import BaseModel, Field

from app.core.database import get_supabase_admin

logger = structlog.get_logger()


class SimulationQualityScore(BaseModel):
    overall: float = Field(ge=0, le=1)
    agent_diversity: float = Field(ge=0, le=1)
    event_coverage: float = Field(ge=0, le=1)
    evidence_density: float = Field(ge=0, le=1)
    confidence_level: str
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


# Weights for the overall score
_W_DIVERSITY = 0.3
_W_COVERAGE = 0.4
_W_DENSITY = 0.3


def _confidence_level(score: float) -> str:
    if score < 0.3:
        return "low"
    if score < 0.6:
        return "medium"
    if score < 0.8:
        return "high"
    return "very_high"


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


async def score_simulation(simulation_id: UUID) -> SimulationQualityScore:
    """Score a simulation's quality across diversity, coverage, and density."""
    admin = get_supabase_admin()

    # Fetch simulation metadata for total rounds
    sim = (
        admin.table("simulations")
        .select("num_rounds")
        .eq("id", str(simulation_id))
        .single()
        .execute()
    )
    total_rounds = sim.data.get("num_rounds", 1)

    # Fetch agents
    agents_resp = (
        admin.table("agents")
        .select("id, persona_type")
        .eq("simulation_id", str(simulation_id))
        .execute()
    )
    agents = agents_resp.data or []

    # Fetch events
    events_resp = (
        admin.table("events")
        .select("id, event_type, round_number, agent_id")
        .eq("simulation_id", str(simulation_id))
        .execute()
    )
    events = events_resp.data or []

    total_agents = len(agents)
    total_events = len(events)

    # --- Agent diversity ---
    if total_agents == 0:
        agent_diversity = 0.0
    else:
        unique_personas = len({a["persona_type"] for a in agents if a.get("persona_type")})
        agent_diversity = _clamp(unique_personas / total_agents)

    # --- Event coverage ---
    unique_event_types = len({e["event_type"] for e in events if e.get("event_type")})
    rounds_with_events = len({e["round_number"] for e in events if e.get("round_number")})
    if total_rounds > 0:
        round_coverage = _clamp(rounds_with_events / total_rounds)
    else:
        round_coverage = 0.0
    # Normalise event-type richness (cap at 10 unique types = 1.0)
    type_richness = _clamp(unique_event_types / 10)
    event_coverage = _clamp((round_coverage + type_richness) / 2)

    # --- Evidence density ---
    if total_agents == 0:
        evidence_density = 0.0
    else:
        events_per_agent = total_events / total_agents
        # 5+ events per agent = perfect density
        evidence_density = _clamp(events_per_agent / 5)

    # --- Overall ---
    overall = _clamp(
        _W_DIVERSITY * agent_diversity
        + _W_COVERAGE * event_coverage
        + _W_DENSITY * evidence_density
    )

    confidence_level = _confidence_level(overall)

    # --- Warnings and recommendations ---
    warnings: list[str] = []
    recommendations: list[str] = []

    if agent_diversity < 0.3:
        warnings.append("Very low agent diversity — most agents share the same persona type.")
        recommendations.append(
            "Add agents with distinct persona types to improve simulation variety."
        )
    elif agent_diversity < 0.6:
        warnings.append("Moderate agent diversity — consider adding more persona variety.")

    if event_coverage < 0.3:
        warnings.append("Low event coverage — many rounds produced no events.")
        recommendations.append(
            "Review simulation prompts to ensure agents generate events each round."
        )
    elif event_coverage < 0.6:
        warnings.append("Moderate event coverage — some rounds or event types are missing.")

    if evidence_density < 0.3:
        warnings.append("Low evidence density — very few events per agent.")
        recommendations.append(
            "Increase the number of rounds or adjust agent behaviour to produce more events."
        )
    elif evidence_density < 0.6:
        warnings.append("Moderate evidence density — agents could produce more events.")

    if total_agents == 0:
        warnings.append("No agents found for this simulation.")
        recommendations.append("Ensure agents are created before running the simulation.")

    if total_events == 0:
        warnings.append("No events found — the simulation may not have run.")
        recommendations.append("Run the simulation or check for errors in the execution log.")

    logger.info(
        "simulation_scored",
        simulation_id=str(simulation_id),
        overall=round(overall, 3),
        agent_diversity=round(agent_diversity, 3),
        event_coverage=round(event_coverage, 3),
        evidence_density=round(evidence_density, 3),
        confidence=confidence_level,
    )

    return SimulationQualityScore(
        overall=round(overall, 3),
        agent_diversity=round(agent_diversity, 3),
        event_coverage=round(event_coverage, 3),
        evidence_density=round(evidence_density, 3),
        confidence_level=confidence_level,
        warnings=warnings,
        recommendations=recommendations,
    )
