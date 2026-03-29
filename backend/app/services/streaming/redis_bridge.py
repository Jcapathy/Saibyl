# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# start_redis_bridge() -> coroutine (run as background task)
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import asyncio
import json

import redis.asyncio as aioredis
import structlog

from app.core.config import settings
from app.services.streaming.ws_manager import manager

logger = structlog.get_logger()


async def start_redis_bridge() -> None:
    """Background task: subscribe to Redis pub/sub and forward to WebSocket clients."""
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    pubsub = r.pubsub()

    await pubsub.psubscribe("simulation:*:events", "report:*:progress")
    logger.info("redis_bridge_started", patterns=["simulation:*:events", "report:*:progress"])

    try:
        async for message in pubsub.listen():
            if message["type"] != "pmessage":
                continue

            channel = message["channel"]
            try:
                event = json.loads(message["data"])
            except (json.JSONDecodeError, TypeError):
                continue

            # Extract simulation_id from channel pattern
            parts = channel.split(":")
            if len(parts) >= 3:
                resource_id = parts[1]
                await manager.broadcast(resource_id, event)

    except asyncio.CancelledError:
        logger.info("redis_bridge_stopped")
    except Exception as e:
        logger.error("redis_bridge_error", error=str(e))
    finally:
        await pubsub.punsubscribe()
        await r.aclose()
