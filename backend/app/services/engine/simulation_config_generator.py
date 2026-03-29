# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# generate_simulation_config(simulation_id: UUID) -> SimulationConfig
# ─────────────────────────────────────────────────────────
from __future__ import annotations

from uuid import UUID

import structlog
from pydantic import BaseModel

from app.core.database import get_supabase_admin
from app.core.llm_client import llm_structured

logger = structlog.get_logger()


class TimeConfig(BaseModel):
    timezone: str
    activity_by_hour: dict[int, float]  # 0-23 -> 0.0-1.0 activity weight


class PlatformConfig(BaseModel):
    platform_id: str
    algorithm_weights: dict
    viral_threshold: float
    content_format: dict


class AgentBehaviorConfig(BaseModel):
    posts_per_active_hour: tuple[float, float]
    comments_per_post: tuple[float, float]
    response_latency_seconds: tuple[int, int]
    sentiment_range: tuple[float, float]
    influence_weight: float


class SimulationConfig(BaseModel):
    simulation_id: UUID
    time_config: TimeConfig
    platform_configs: list[PlatformConfig]
    agent_behavior_configs: dict[str, AgentBehaviorConfig]
    initial_topics: list[str]
    batch_size: int = 15
    max_rounds: int


# Default activity curve — generic social media usage pattern
DEFAULT_ACTIVITY_CURVE: dict[int, float] = {
    0: 0.1, 1: 0.05, 2: 0.03, 3: 0.02, 4: 0.02, 5: 0.05,
    6: 0.15, 7: 0.35, 8: 0.55, 9: 0.7, 10: 0.75, 11: 0.8,
    12: 0.85, 13: 0.8, 14: 0.75, 15: 0.7, 16: 0.65, 17: 0.7,
    18: 0.8, 19: 0.85, 20: 0.9, 21: 0.8, 22: 0.5, 23: 0.25,
}

# Default platform configurations
DEFAULT_PLATFORM_CONFIGS: dict[str, PlatformConfig] = {
    "twitter": PlatformConfig(
        platform_id="twitter",
        algorithm_weights={"recency": 0.3, "engagement": 0.4, "relevance": 0.3},
        viral_threshold=0.7,
        content_format={"max_chars": 280, "supports_threads": True, "supports_media": True},
    ),
    "reddit": PlatformConfig(
        platform_id="reddit",
        algorithm_weights={"upvotes": 0.5, "recency": 0.3, "comments": 0.2},
        viral_threshold=0.6,
        content_format={"max_chars": 40000, "supports_threads": True, "supports_media": True},
    ),
    "linkedin": PlatformConfig(
        platform_id="linkedin",
        algorithm_weights={"connections": 0.3, "engagement": 0.4, "relevance": 0.3},
        viral_threshold=0.8,
        content_format={"max_chars": 3000, "supports_threads": False, "supports_media": True},
    ),
}

CONFIG_PROMPT = """Given the following simulation prediction goal and agent profiles, generate:
1. A list of 3-8 initial discussion topics relevant to the prediction goal
2. Per-agent behavior configs (posting frequency, sentiment, influence)

Prediction goal: {prediction_goal}

Agent profiles:
{agent_profiles}

Return JSON with keys:
- "initial_topics": list of topic strings
- "agent_configs": dict mapping agent entity_id to:
  - "posts_per_active_hour": [min, max] floats
  - "comments_per_post": [min, max] floats
  - "response_latency_seconds": [min, max] ints
  - "sentiment_range": [min, max] floats from -1.0 to 1.0
  - "influence_weight": float 0.0-1.0"""


class _LLMConfigResult(BaseModel):
    initial_topics: list[str]
    agent_configs: dict[str, AgentBehaviorConfig]


async def generate_simulation_config(simulation_id: UUID) -> SimulationConfig:
    """Generate full simulation configuration from simulation record and agents."""
    admin = get_supabase_admin()

    # Fetch simulation
    sim = (
        admin.table("simulations")
        .select("*")
        .eq("id", str(simulation_id))
        .single()
        .execute()
    ).data

    # Fetch agents
    agents = (
        admin.table("simulation_agents")
        .select("entity_id, entity_name, profile, platform")
        .eq("simulation_id", str(simulation_id))
        .execute()
    ).data

    # Build agent profile summary for LLM
    agent_summary = "\n".join(
        f"- {a['entity_name']} (platform: {a['platform']}): {a['profile'].get('description', '')}"
        for a in agents
    )

    # Generate topics and agent behavior via LLM
    prompt = CONFIG_PROMPT.format(
        prediction_goal=sim["prediction_goal"],
        agent_profiles=agent_summary,
    )
    llm_config = await llm_structured(
        messages=[{"role": "user", "content": prompt}],
        schema=_LLMConfigResult,
    )

    # Build platform configs for requested platforms
    platform_configs = []
    for platform in (sim.get("platforms") or []):
        if platform in DEFAULT_PLATFORM_CONFIGS:
            platform_configs.append(DEFAULT_PLATFORM_CONFIGS[platform])
        else:
            platform_configs.append(PlatformConfig(
                platform_id=platform,
                algorithm_weights={"recency": 0.4, "engagement": 0.4, "relevance": 0.2},
                viral_threshold=0.7,
                content_format={"max_chars": 5000, "supports_threads": True, "supports_media": True},
            ))

    config = SimulationConfig(
        simulation_id=simulation_id,
        time_config=TimeConfig(
            timezone=sim.get("timezone", "America/New_York"),
            activity_by_hour=DEFAULT_ACTIVITY_CURVE,
        ),
        platform_configs=platform_configs,
        agent_behavior_configs=llm_config.agent_configs,
        initial_topics=llm_config.initial_topics,
        batch_size=15,
        max_rounds=sim.get("max_rounds", 10),
    )

    logger.info(
        "simulation_config_generated",
        simulation_id=str(simulation_id),
        platforms=len(platform_configs),
        agents=len(llm_config.agent_configs),
        topics=len(llm_config.initial_topics),
    )

    return config
