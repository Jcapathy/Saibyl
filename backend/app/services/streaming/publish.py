# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# publish_round_start(simulation_id, round_number, arenas)      [async]
# publish_agent_action(simulation_id, event)                    [async]
# publish_round_end(simulation_id, round_number, events, total) [async]
# publish_simulation_finished(simulation_id, status, total)     [async]
# STREAM_EVENT_TYPES
# ─────────────────────────────────────────────────────────
"""The live run feed's missing half (P0-3).

`ws.py` subscribes to `simulation:{id}:events` and `redis_bridge.py`
psubscribes `simulation:*:events`. **Nothing in the backend ever published
there.** The only `r.publish` in the codebase writes `report:{id}:progress`.
So a founder clicked "a run is going now — watch it", the socket connected
cleanly, and they sat on *"Waiting for the first reaction…"* for the whole of
a run they had paid for, which completed perfectly server-side.

**Two vocabularies had to become one.** The browser dispatches on the wire
field `event_type` (`websocket.ts:16`) and listens for `agent_action`,
`round_start`, `round_end`, `simulation_completed`. The adapters' `EventType`
is `post | comment | react | dm` — a different axis entirely: one says *what
kind of moment this is in the run*, the other says *what the agent did*. They
were never alternatives, and the earlier attempt to pick a winner is why a
third vocabulary exists in `event_schema.py` that nothing produces.

So the wire vocabulary owns `event_type`, and the agent's action rides beside
it as `action`. Nothing is renamed at the adapter, nothing is lost, and the
mapping happens once, here, at the edge.

**Publishing may never fail a run.** Every function swallows its errors after
logging. The founder has already been charged; a Redis hiccup must cost them a
progress bar, never the run. The database remains the record of what happened
— this is a view onto it, and `_write_round_events` still owns the truth.
"""
from __future__ import annotations

import json
from typing import Any

import structlog

log = structlog.get_logger()

# The wire vocabulary, which is the browser's. Listed so a test can assert the
# publisher and the client still agree without either side being read by hand.
STREAM_EVENT_TYPES = (
    "round_start",
    "agent_action",
    "round_end",
    "simulation_completed",
    "simulation_failed",
)

# A run is charged per agent, round and arena, so a large one produces
# thousands of actions. The feed exists to show a founder that something is
# happening, not to mirror the table — past this many in one round the
# remainder are counted in `round_end` instead of streamed one by one.
MAX_ACTIONS_STREAMED_PER_ROUND = 60

_CONTENT_PREVIEW_CHARS = 400


async def _publish(simulation_id: str, payload: dict[str, Any]) -> None:
    """One message onto the run's channel. Never raises."""
    try:
        import redis.asyncio as aioredis

        from app.core.config import settings

        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            await client.publish(
                f"simulation:{simulation_id}:events", json.dumps(payload)
            )
        finally:
            await client.aclose()
    except Exception:  # noqa: BLE001 - a progress bar is never worth a run
        log.warning(
            "simulation_stream_publish_failed",
            simulation_id=simulation_id,
            event_type=payload.get("event_type"),
        )


def _envelope(simulation_id: str, event_type: str) -> dict[str, Any]:
    from datetime import UTC, datetime

    return {
        "event_type": event_type,
        "simulation_id": str(simulation_id),
        "timestamp": datetime.now(UTC).isoformat(),
    }


async def publish_round_start(
    simulation_id: str, round_number: int, arenas: int
) -> None:
    """A round has begun. The first thing a watching founder ever sees."""
    await _publish(simulation_id, {
        **_envelope(simulation_id, "round_start"),
        "round_number": round_number,
        "variant": "",
        "platform": None,
        "content": None,
        "metadata": {"arenas": arenas},
    })


async def publish_agent_action(simulation_id: str, event: dict[str, Any]) -> None:
    """One agent did one thing.

    Takes the row the runner is about to write rather than a second shape, so
    the feed cannot drift from the record. `_arena` and `_ref` are the
    runner's transient keys and are dropped here for the same reason they are
    dropped before the insert.
    """
    content = event.get("content")
    await _publish(simulation_id, {
        **_envelope(simulation_id, "agent_action"),
        # The wire vocabulary owns `event_type`; the agent's action rides here.
        "action": event.get("event_type"),
        "round_number": event.get("round_number"),
        "variant": event.get("variant") or "",
        "platform": event.get("platform"),
        "content": content[:_CONTENT_PREVIEW_CHARS] if content else None,
        "agent_id": str(event.get("agent_id") or "") or None,
        "metadata": event.get("metadata") or {},
    })


async def publish_round_end(
    simulation_id: str, round_number: int, events_this_round: int, total_events: int
) -> None:
    """A round is done, with its real counts attached."""
    await _publish(simulation_id, {
        **_envelope(simulation_id, "round_end"),
        "round_number": round_number,
        "variant": "",
        "platform": None,
        "content": None,
        "metadata": {
            "events_this_round": events_this_round,
            "total_events": total_events,
        },
    })


async def publish_simulation_finished(
    simulation_id: str, status: str, total_events: int
) -> None:
    """The run ended.

    A failed run publishes too. The browser stops its spinner on
    `simulation_failed` exactly as it does on completion, and a founder
    watching a run that died deserves to be told rather than left on a feed
    that simply stops.
    """
    # The table stores `complete`; the wire says `simulation_completed`. Both
    # spellings are accepted rather than one being canonical, because this
    # mapping existing at all is what the whole bug was made of.
    event_type = (
        "simulation_completed"
        if status in ("complete", "completed", "stopped")
        else "simulation_failed"
    )
    await _publish(simulation_id, {
        **_envelope(simulation_id, event_type),
        "round_number": None,
        "variant": "",
        "platform": None,
        "content": None,
        "metadata": {"status": status, "total_events": total_events},
    })
