# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# stop_simulation(simulation_id: UUID) -> None
# get_simulation_status(simulation_id: UUID) -> SimulationStatus
# ─────────────────────────────────────────────────────────
# Control-plane helpers for running simulations. The simulation itself is
# executed by app.workers.simulation_tasks.run_simulation — this module only
# signals and inspects it.
from __future__ import annotations

from uuid import UUID

import redis
import structlog
from pydantic import BaseModel

from app.core.config import settings
from app.core.database import get_supabase_admin

logger = structlog.get_logger()


class SimulationStatus(BaseModel):
    simulation_id: str
    status: str
    current_round: int
    total_rounds: int
    events_so_far: int


def _get_redis() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


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
