# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# run_simulation(simulation_id: UUID) -> SimulationResult
# run_simulation_ab(simulation_id: UUID) -> ABSimulationResult
# stop_simulation(simulation_id: UUID) -> None
# get_simulation_status(simulation_id: UUID) -> SimulationStatus
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import redis
import structlog
from pydantic import BaseModel

from app.core.config import settings
from app.core.database import get_supabase_admin
from app.services.platforms.base_adapter import SimulationEvent
from app.services.platforms.registry import get_adapter, load_all_adapters

logger = structlog.get_logger()

BATCH_SIZE = 15
LLM_SEMAPHORE_LIMIT = 10


class SimulationResult(BaseModel):
    simulation_id: str
    variant: str
    total_events: int
    rounds_completed: int
    status: str


class ABSimulationResult(BaseModel):
    variant_a: SimulationResult
    variant_b: SimulationResult


class SimulationStatus(BaseModel):
    simulation_id: str
    status: str
    current_round: int
    total_rounds: int
    events_so_far: int


def _get_redis() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def _get_activity_scale(timezone: str, activity_by_hour: dict[int, float]) -> float:
    """Returns 0.0-1.0 activity multiplier based on time of day in simulation timezone."""
    try:
        tz = ZoneInfo(timezone)
        local_time = datetime.now(UTC).astimezone(tz)
        return activity_by_hour.get(local_time.hour, 0.5)
    except Exception:
        return 0.5


def _check_stop_signal(r: redis.Redis, simulation_id: str) -> bool:
    """Check if a stop signal has been set for this simulation."""
    return bool(r.get(f"simulation:{simulation_id}:stop"))


async def _publish_events(
    r: redis.Redis,
    simulation_id: str,
    events: list[SimulationEvent],
) -> None:
    """Publish events to Redis pub/sub for real-time streaming."""
    channel = f"simulation:{simulation_id}:events"
    for event in events:
        r.publish(channel, event.model_dump_json())


async def _persist_events(
    simulation_id: str,
    org_id: str,
    events: list[SimulationEvent],
    agent_id_map: dict[str, str],
) -> None:
    """Batch insert events into simulation_events table."""
    if not events:
        return

    admin = get_supabase_admin()
    rows = []
    for event in events:
        rows.append({
            "simulation_id": simulation_id,
            "organization_id": org_id,
            "event_type": event.event_type,
            "agent_id": agent_id_map.get(event.agent_username),
            "platform": event.platform,
            "variant": event.variant,
            "round_number": event.round_number,
            "content": event.content,
            "metadata": event.metadata,
        })

    # Batch insert in chunks of 100
    for i in range(0, len(rows), 100):
        admin.table("simulation_events").insert(rows[i:i + 100]).execute()


async def run_variant(
    simulation_id: UUID,
    variant: str = "a",
) -> SimulationResult:
    """Run a single simulation variant."""
    admin = get_supabase_admin()
    r = _get_redis()
    sim_id = str(simulation_id)

    # Load simulation config
    sim = (
        admin.table("simulations")
        .select("*")
        .eq("id", sim_id)
        .single()
        .execute()
    ).data

    org_id = sim["organization_id"]
    max_rounds = sim.get("max_rounds", 10)
    platforms = sim.get("platforms") or ["twitter_x"]
    timezone = sim.get("timezone", "America/New_York")

    # Load agents for this variant
    agents = (
        admin.table("simulation_agents")
        .select("*")
        .eq("simulation_id", sim_id)
        .eq("variant", variant)
        .execute()
    ).data

    # Build agent ID map (username -> db id)
    agent_id_map = {a["username"]: a["id"] for a in agents}

    # Group agents by platform
    agents_by_platform: dict[str, list] = {}
    for agent in agents:
        p = agent.get("platform", "twitter_x")
        agents_by_platform.setdefault(p, []).append(agent)

    # Initialize platform adapters
    load_all_adapters()
    adapters = {}
    variant_config = sim.get(f"variant_{variant}_config") or {}

    for platform_id in platforms:
        try:
            adapter = get_adapter(platform_id)
            platform_agents = agents_by_platform.get(platform_id, [])
            await adapter.initialize(
                config={**variant_config, "timezone": timezone},
                agents=platform_agents,
            )
            adapters[platform_id] = adapter
        except Exception as e:
            logger.error("adapter_init_failed", platform=platform_id, error=str(e))

    # Update status to running
    admin.table("simulations").update({"status": "running"}).eq("id", sim_id).execute()

    total_events = 0
    rounds_completed = 0

    # Default activity curve
    activity_curve = {i: 0.5 for i in range(24)}
    activity_curve.update({8: 0.6, 9: 0.7, 10: 0.8, 11: 0.8, 12: 0.85,
                           13: 0.8, 17: 0.7, 18: 0.8, 19: 0.85, 20: 0.9, 21: 0.8})

    for round_num in range(1, max_rounds + 1):
        # Check stop signal
        if _check_stop_signal(r, sim_id):
            logger.info("simulation_stopped", simulation_id=sim_id, round=round_num)
            admin.table("simulations").update({"status": "stopped"}).eq("id", sim_id).execute()
            break

        # Activity scaling
        scale = _get_activity_scale(timezone, activity_curve)
        logger.info(
            "simulation_round",
            simulation_id=sim_id,
            round=round_num,
            activity_scale=scale,
            variant=variant,
        )

        # Run all platforms concurrently for this round
        round_events: list[SimulationEvent] = []

        async def collect_from_adapter(platform_id: str, adapter):
            events = []
            async for event in adapter.run_round(round_num):
                events.append(event)
            return events

        tasks = [
            collect_from_adapter(pid, adapter)
            for pid, adapter in adapters.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error("adapter_round_error", error=str(result))
            else:
                round_events.extend(result)

        # Persist and publish events
        if round_events:
            await _persist_events(sim_id, org_id, round_events, agent_id_map)
            await _publish_events(r, sim_id, round_events)

        total_events += len(round_events)
        rounds_completed = round_num

        # Emit round_complete event
        round_complete = SimulationEvent(
            event_type="round_complete",
            agent_username="system",
            platform="system",
            round_number=round_num,
            variant=variant,
            content=json.dumps({
                "events_this_round": len(round_events),
                "total_events": total_events,
            }),
            timestamp=datetime.now(UTC),
        )
        r.publish(f"simulation:{sim_id}:events", round_complete.model_dump_json())

    # Mark complete
    admin.table("simulations").update({
        "status": "complete",
        "completed_at": datetime.now(UTC).isoformat(),
    }).eq("id", sim_id).execute()

    logger.info(
        "simulation_complete",
        simulation_id=sim_id,
        variant=variant,
        events=total_events,
        rounds=rounds_completed,
    )

    return SimulationResult(
        simulation_id=sim_id,
        variant=variant,
        total_events=total_events,
        rounds_completed=rounds_completed,
        status="complete",
    )


async def run_simulation(simulation_id: UUID) -> SimulationResult:
    """Run a single-variant simulation."""
    return await run_variant(simulation_id, variant="a")


async def run_simulation_ab(simulation_id: UUID) -> ABSimulationResult:
    """Run A/B simulation — both variants concurrently."""
    task_a = asyncio.create_task(run_variant(simulation_id, variant="a"))
    task_b = asyncio.create_task(run_variant(simulation_id, variant="b"))
    result_a, result_b = await asyncio.gather(task_a, task_b)
    return ABSimulationResult(variant_a=result_a, variant_b=result_b)


async def stop_simulation(simulation_id: UUID) -> None:
    """Send stop signal to a running simulation."""
    r = _get_redis()
    r.set(f"simulation:{str(simulation_id)}:stop", "1", ex=3600)
    logger.info("stop_signal_sent", simulation_id=str(simulation_id))


def get_simulation_status(simulation_id: UUID) -> SimulationStatus:
    """Get current simulation status from DB."""
    admin = get_supabase_admin()
    sim = (
        admin.table("simulations")
        .select("status, max_rounds")
        .eq("id", str(simulation_id))
        .single()
        .execute()
    ).data

    events = (
        admin.table("simulation_events")
        .select("round_number", count="exact")
        .eq("simulation_id", str(simulation_id))
        .execute()
    )

    max_round = 0
    if events.data:
        max_round = max((e.get("round_number", 0) or 0) for e in events.data)

    return SimulationStatus(
        simulation_id=str(simulation_id),
        status=sim["status"],
        current_round=max_round,
        total_rounds=sim.get("max_rounds", 10),
        events_so_far=events.count or 0,
    )
