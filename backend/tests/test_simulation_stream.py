"""The live run feed has a publisher, and it speaks the browser's language.

P0-3, both halves of it:

1. **Nothing ever published.** `ws.py` subscribed to `simulation:{id}:events`
   and `redis_bridge.py` psubscribed `simulation:*:events`; the only
   `r.publish` in the backend wrote `report:{id}:progress`. A founder clicked
   "a run is going now — watch it" and sat on *"Waiting for the first
   reaction…"* through a paid run that completed perfectly server-side.

2. **The two sides used different words.** The browser dispatches on the wire
   field `event_type` and listens for `agent_action` / `round_start` /
   `round_end` / `simulation_completed`. The adapters' `EventType` is
   `post | comment | react | dm`. Publishing the adapter's word into
   `event_type` would have produced a stream nothing listened for — a fix that
   looks like a fix and changes nothing on screen.

The tests below pin the channel, the vocabulary, and the rule that matters
most in production: **publishing may never fail a run.** The founder has
already been charged; a Redis hiccup costs them a progress bar, never the run.
"""
from __future__ import annotations

import json

import pytest

from app.services.streaming import publish as pub

SIM = "11111111-1111-1111-1111-111111111111"


class _Recorder:
    """Stands in for Redis, and records what would have gone on the wire."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, dict]] = []

    def install(self, monkeypatch) -> _Recorder:
        async def _publish(simulation_id: str, payload: dict) -> None:
            self.messages.append(
                (f"simulation:{simulation_id}:events", payload)
            )

        monkeypatch.setattr(pub, "_publish", _publish)
        return self

    @property
    def types(self) -> list[str]:
        return [p["event_type"] for _c, p in self.messages]


@pytest.fixture
def wire(monkeypatch) -> _Recorder:
    return _Recorder().install(monkeypatch)


# ---------------------------------------------------------------------------
# The vocabulary the browser actually listens for
# ---------------------------------------------------------------------------

# Read off `SimulationRunPage.tsx`'s `socket.on(...)` calls. Duplicated here on
# purpose: if the page renames one, this list is where the mismatch surfaces,
# and a mismatch is the entire defect.
BROWSER_LISTENS_FOR = {
    "agent_action",
    "round_start",
    "round_end",
    "simulation_completed",
    "simulation_failed",
}


def test_the_publisher_only_emits_words_the_browser_listens_for():
    assert set(pub.STREAM_EVENT_TYPES) == BROWSER_LISTENS_FOR, (
        "the publisher and the run page disagree about the vocabulary; a "
        "stream nothing listens for is the same as no stream"
    )


@pytest.mark.asyncio
async def test_a_round_start_reaches_the_runs_own_channel(wire):
    await pub.publish_round_start(SIM, 1, arenas=2)

    channel, payload = wire.messages[0]
    assert channel == f"simulation:{SIM}:events", (
        "published somewhere ws.py and redis_bridge.py are not listening"
    )
    assert payload["event_type"] == "round_start"
    assert payload["round_number"] == 1
    assert payload["metadata"]["arenas"] == 2


@pytest.mark.asyncio
async def test_the_agents_action_rides_beside_the_wire_type_not_inside_it(wire):
    """The vocabulary collision, pinned. `post` in `event_type` would be
    dispatched to a handler the page never registered."""
    await pub.publish_agent_action(SIM, {
        "event_type": "comment",
        "round_number": 2,
        "variant": "b",
        "platform": "reddit",
        "content": "This is the part I do not believe.",
        "agent_id": "abc",
        "metadata": {"sentiment": None},
    })

    _channel, payload = wire.messages[0]
    assert payload["event_type"] == "agent_action", "the wire word was overwritten"
    assert payload["action"] == "comment", "the agent's action was lost"
    assert payload["variant"] == "b"
    assert payload["platform"] == "reddit"
    assert payload["content"].startswith("This is the part")


@pytest.mark.asyncio
async def test_the_runners_transient_keys_never_reach_the_wire(wire):
    """`_arena` and `_ref` are stripped before the insert for the same reason
    they must be stripped here: they are the runner's bookkeeping."""
    await pub.publish_agent_action(SIM, {
        "event_type": "post",
        "round_number": 1,
        "variant": "a",
        "platform": "x",
        "content": "hello",
        "_arena": ("x", "a"),
        "_ref": "tmp-1",
    })

    _channel, payload = wire.messages[0]
    assert "_arena" not in payload
    assert "_ref" not in payload


@pytest.mark.asyncio
async def test_long_content_is_previewed_not_shipped_whole(wire):
    await pub.publish_agent_action(SIM, {
        "event_type": "post", "round_number": 1, "variant": "a",
        "platform": "x", "content": "x" * 5_000,
    })

    _channel, payload = wire.messages[0]
    assert len(payload["content"]) <= pub._CONTENT_PREVIEW_CHARS


@pytest.mark.asyncio
async def test_a_finished_run_says_so_in_the_word_the_page_stops_on(wire):
    await pub.publish_simulation_finished(SIM, "complete", 412)

    _channel, payload = wire.messages[0]
    assert payload["event_type"] == "simulation_completed", (
        "the table stores 'complete' and the wire says 'simulation_completed'; "
        "an unmapped status leaves the spinner running forever"
    )
    assert payload["metadata"]["total_events"] == 412


@pytest.mark.asyncio
async def test_a_failed_run_publishes_too(wire):
    """A founder watching a run that died deserves to be told, rather than
    left on a feed that simply stops."""
    await pub.publish_simulation_finished(SIM, "failed", 0)

    assert wire.types == ["simulation_failed"]


@pytest.mark.asyncio
async def test_a_stopped_run_is_an_ending_not_a_failure(wire):
    await pub.publish_simulation_finished(SIM, "stopped", 40)

    assert wire.types == ["simulation_completed"]


# ---------------------------------------------------------------------------
# The rule that matters in production
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_dead_redis_costs_a_progress_bar_never_the_run(monkeypatch):
    """The founder has already been charged. Every publish swallows its own
    failure after logging, because the database is the record of what happened
    and this is only a view onto it."""
    import redis.asyncio as aioredis

    def _explode(*_args, **_kwargs):
        raise ConnectionError("redis is gone")

    monkeypatch.setattr(aioredis, "from_url", _explode)

    # None of these may raise.
    await pub.publish_round_start(SIM, 1, arenas=1)
    await pub.publish_agent_action(SIM, {"event_type": "post", "content": "x"})
    await pub.publish_round_end(SIM, 1, 10, 10)
    await pub.publish_simulation_finished(SIM, "complete", 10)


@pytest.mark.asyncio
async def test_every_payload_is_json_serialisable(wire):
    """It is serialised at the boundary, so a non-serialisable value would
    surface as a swallowed exception and a silently missing event."""
    await pub.publish_round_start(SIM, 1, arenas=1)
    await pub.publish_agent_action(SIM, {
        "event_type": "post", "round_number": 1, "variant": "a",
        "platform": "x", "content": "hi", "agent_id": None, "metadata": {},
    })
    await pub.publish_round_end(SIM, 1, 3, 3)
    await pub.publish_simulation_finished(SIM, "complete", 3)

    for _channel, payload in wire.messages:
        json.dumps(payload)
        assert payload["simulation_id"] == SIM
        assert payload["timestamp"]
