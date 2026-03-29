# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# persist_agents(simulation_id: UUID, agents: list[AgentProfile]) -> int
# get_simulation_agents(simulation_id: UUID) -> list[dict]
# ─────────────────────────────────────────────────────────
from __future__ import annotations

from uuid import UUID

import structlog

from app.core.database import get_supabase_admin
from app.services.engine.personas.agent_profile_generator import AgentProfile
from app.services.engine.personas.platform_formatters import format_for_platform

logger = structlog.get_logger()


def persist_agents(simulation_id: UUID, agents: list[AgentProfile]) -> int:
    """Write all agent profiles to the simulation_agents table."""
    admin = get_supabase_admin()

    # Get org_id from simulation
    sim = (
        admin.table("simulations")
        .select("organization_id")
        .eq("id", str(simulation_id))
        .single()
        .execute()
    ).data

    rows = []
    for agent in agents:
        platform_profile = format_for_platform(agent, agent.platform)
        full_profile = {
            **agent.model_dump(exclude={"behavior_config"}),
            "platform_profile": platform_profile,
            "behavior_config": agent.behavior_config.model_dump(),
        }

        rows.append({
            "simulation_id": str(simulation_id),
            "organization_id": sim["organization_id"],
            "entity_id": agent.entity_id,
            "entity_name": agent.entity_name,
            "persona_pack_id": agent.pack_id,
            "variant": "a",
            "platform": agent.platform,
            "profile": full_profile,
            "username": agent.username,
        })

    if rows:
        admin.table("simulation_agents").insert(rows).execute()

    logger.info(
        "agents_persisted",
        simulation_id=str(simulation_id),
        count=len(rows),
    )
    return len(rows)


def get_simulation_agents(simulation_id: UUID) -> list[dict]:
    """Retrieve all agents for a simulation."""
    admin = get_supabase_admin()
    result = (
        admin.table("simulation_agents")
        .select("*")
        .eq("simulation_id", str(simulation_id))
        .execute()
    )
    return result.data
