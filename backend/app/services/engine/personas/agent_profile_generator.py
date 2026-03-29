# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# generate_agents(simulation_id: UUID, persona_pack_ids: list[str]) -> list[AgentProfile]
# generate_agent_for_entity(entity, archetype, context) -> AgentProfile
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import asyncio
import hashlib
import random
from uuid import UUID

import structlog
from pydantic import BaseModel

from app.core.database import get_supabase_admin
from app.core.llm_client import llm_structured
from app.services.engine.knowledge_graph_builder import GraphNode, get_all_nodes, search_graph
from app.services.engine.personas.pack_loader import Archetype, get_pack
from app.services.engine.simulation_config_generator import AgentBehaviorConfig

logger = structlog.get_logger()

MAX_CONCURRENT_LLM = 5


class AgentProfile(BaseModel):
    entity_id: str
    entity_name: str
    username: str
    display_name: str
    bio: str
    persona_type: str
    archetype_id: str
    pack_id: str
    age: int
    gender: str
    mbti: str
    country: str
    profession: str
    interests: list[str]
    political_lean: str
    platform: str
    behavior_config: AgentBehaviorConfig
    sentiment_baseline: float
    influence_weight: float
    backstory: str
    known_relationships: list[str]


class _LLMProfileResult(BaseModel):
    display_name: str
    bio: str
    age: int
    gender: str
    country: str
    profession: str
    backstory: str


PROFILE_PROMPT = """Generate a realistic social media persona profile for simulation.

Entity: {entity_name}
Context from knowledge graph: {context}
Archetype: {archetype_label} ({archetype_desc})
Age range: {age_min}-{age_max}
Platform: {platform}
Interests: {interests}
Values: {values}

Return JSON with:
- "display_name": a realistic full name
- "bio": a 1-2 sentence social media bio (in character)
- "age": specific age within the range
- "gender": based on distribution (most likely: {likely_gender})
- "country": realistic country
- "profession": specific job title
- "backstory": 2-3 sentences about this person's perspective on the entity/topic"""


def _select_archetype(pack_id: str, entity: GraphNode) -> Archetype:
    """Select an archetype from the pack using weighted random selection."""
    pack = get_pack(pack_id)
    weights = [a.weight for a in pack.archetypes]
    return random.choices(pack.archetypes, weights=weights, k=1)[0]


def _select_platform(archetype: Archetype) -> str:
    """Pick the most preferred platform from archetype preferences."""
    prefs = archetype.platform_preferences
    if not prefs:
        return "twitter_x"
    return max(prefs, key=prefs.get)


def _make_username(name: str, entity_id: str) -> str:
    """Generate a normalized username from name + entity hash."""
    base = name.lower().replace(" ", "_")[:15]
    suffix = hashlib.md5(entity_id.encode()).hexdigest()[:4]
    return f"{base}_{suffix}"


def _select_mbti(archetype: Archetype) -> str:
    return random.choice(archetype.personality.mbti_pool)


def _likely_gender(archetype: Archetype) -> str:
    dist = archetype.demographics.gender_distribution
    return max(dist, key=dist.get)


def _fallback_profile(entity: GraphNode, archetype: Archetype, pack_id: str) -> AgentProfile:
    """Rule-based fallback when LLM fails."""
    h = int(hashlib.md5(entity.uuid.encode()).hexdigest(), 16)
    age_min, age_max = archetype.demographics.age_range
    age = age_min + (h % (age_max - age_min + 1))
    platform = _select_platform(archetype)

    return AgentProfile(
        entity_id=entity.uuid,
        entity_name=entity.name,
        username=_make_username(entity.name, entity.uuid),
        display_name=entity.name,
        bio=f"{archetype.label} interested in {', '.join(archetype.interests[:3])}",
        persona_type=archetype.label,
        archetype_id=archetype.id,
        pack_id=pack_id,
        age=age,
        gender=_likely_gender(archetype),
        mbti=_select_mbti(archetype),
        country="United States",
        profession=archetype.label,
        interests=archetype.interests,
        political_lean=archetype.political_lean,
        platform=platform,
        behavior_config=AgentBehaviorConfig(
            posts_per_active_hour=(0.5, 2.0),
            comments_per_post=(1.0, 3.0),
            response_latency_seconds=(30, 300),
            sentiment_range=(-0.5, 0.5),
            influence_weight=archetype.behavior_traits.influence_multiplier / 5.0,
        ),
        sentiment_baseline=archetype.behavior_traits.sentiment_baseline,
        influence_weight=archetype.behavior_traits.influence_multiplier / 5.0,
        backstory=f"A {archetype.label} with interest in {entity.name}.",
        known_relationships=[],
    )


async def generate_agent_for_entity(
    entity: GraphNode,
    archetype: Archetype,
    pack_id: str,
    context: str,
    semaphore: asyncio.Semaphore,
) -> AgentProfile:
    """Generate a single agent profile via LLM."""
    platform = _select_platform(archetype)
    age_min, age_max = archetype.demographics.age_range

    async with semaphore:
        try:
            prompt = PROFILE_PROMPT.format(
                entity_name=entity.name,
                context=context[:2000],
                archetype_label=archetype.label,
                archetype_desc=", ".join(archetype.interests[:5]),
                age_min=age_min,
                age_max=age_max,
                platform=platform,
                interests=", ".join(archetype.interests),
                values=", ".join(archetype.values),
                likely_gender=_likely_gender(archetype),
            )
            result = await llm_structured(
                messages=[{"role": "user", "content": prompt}],
                schema=_LLMProfileResult,
            )

            return AgentProfile(
                entity_id=entity.uuid,
                entity_name=entity.name,
                username=_make_username(result.display_name, entity.uuid),
                display_name=result.display_name,
                bio=result.bio,
                persona_type=archetype.label,
                archetype_id=archetype.id,
                pack_id=pack_id,
                age=result.age,
                gender=result.gender,
                mbti=_select_mbti(archetype),
                country=result.country,
                profession=result.profession,
                interests=archetype.interests,
                political_lean=archetype.political_lean,
                platform=platform,
                behavior_config=AgentBehaviorConfig(
                    posts_per_active_hour=(
                        archetype.behavior_traits.posts_per_week[0] / 7 / 8,
                        archetype.behavior_traits.posts_per_week[1] / 7 / 8,
                    ),
                    comments_per_post=(1.0, 3.0),
                    response_latency_seconds=(30, 300),
                    sentiment_range=(
                        archetype.behavior_traits.sentiment_baseline - 0.3,
                        archetype.behavior_traits.sentiment_baseline + 0.3,
                    ),
                    influence_weight=archetype.behavior_traits.influence_multiplier / 5.0,
                ),
                sentiment_baseline=archetype.behavior_traits.sentiment_baseline,
                influence_weight=archetype.behavior_traits.influence_multiplier / 5.0,
                backstory=result.backstory,
                known_relationships=[],
            )
        except Exception as e:
            logger.warning("llm_profile_failed", entity=entity.name, error=str(e))
            return _fallback_profile(entity, archetype, pack_id)


async def generate_agents(
    simulation_id: UUID,
    persona_pack_ids: list[str],
) -> list[AgentProfile]:
    """Generate agent profiles for all entities in a simulation's knowledge graph."""
    admin = get_supabase_admin()

    # Get simulation and its project's knowledge graph
    sim = (
        admin.table("simulations")
        .select("project_id, organization_id")
        .eq("id", str(simulation_id))
        .single()
        .execute()
    ).data

    kg = (
        admin.table("knowledge_graphs")
        .select("id")
        .eq("project_id", sim["project_id"])
        .eq("build_status", "complete")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    ).data

    if not kg:
        raise ValueError("No completed knowledge graph found for this simulation's project")

    graph_id = kg[0]["id"]
    entities = await get_all_nodes(graph_id)

    if not entities:
        raise ValueError("Knowledge graph has no entities")

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM)
    profiles: list[AgentProfile] = []

    for entity in entities:
        # Get context from graph
        related = await search_graph(graph_id, entity.name, limit=5)
        context = "; ".join(
            f"{r.name}: {r.summary}" for r in related if r.uuid != entity.uuid
        )

        # Pick a pack and archetype
        pack_id = random.choice(persona_pack_ids) if persona_pack_ids else "retail-consumer"
        archetype = _select_archetype(pack_id, entity)

        profile = await generate_agent_for_entity(
            entity, archetype, pack_id, context, semaphore
        )
        profiles.append(profile)

    logger.info(
        "agents_generated",
        simulation_id=str(simulation_id),
        count=len(profiles),
    )
    return profiles
