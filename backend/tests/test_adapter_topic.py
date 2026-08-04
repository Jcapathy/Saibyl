"""Regression tests for the two bugs that made a live run produce zero events.

Both predate Phase 1 and neither raised an error. A run simply completed with
nothing in it, which is the worst possible failure mode for a product whose
output is a measurement.
"""
from __future__ import annotations

import inspect
import re

import pytest

from app.services.platforms.base_adapter import BasePlatformAdapter
from app.services.platforms.registry import PLATFORM_REGISTRY, get_adapter, load_all_adapters

GOAL = "Whether founders will pay $99/month for synthetic audience testing"


@pytest.fixture(scope="module")
def adapters() -> list[BasePlatformAdapter]:
    load_all_adapters()
    return [get_adapter(pid) for pid in PLATFORM_REGISTRY]


def _bare_adapter() -> BasePlatformAdapter:
    """A concrete no-op adapter, for exercising the shared base-class helpers."""

    class _Probe(BasePlatformAdapter):
        platform_id = "probe"

        async def initialize(self, config, agents): ...
        async def run_round(self, round_number): ...  # type: ignore[override]
        async def get_feed(self, agent_username): ...
        async def post(self, agent_username, content, metadata=None): ...
        async def comment(self, agent_username, post_id, content): ...
        async def react(self, agent_username, post_id, reaction): ...
        def get_state_snapshot(self): return {}

    return _Probe()


def test_every_adapter_is_registered(adapters):
    assert len(adapters) >= 12


def test_topic_block_states_the_subject():
    adapter = _bare_adapter()
    adapter.set_topic({"prediction_goal": GOAL})
    assert GOAL in adapter.topic_block()


def test_topic_block_is_empty_without_a_goal():
    """No goal means no fabricated subject line."""
    adapter = _bare_adapter()
    adapter.set_topic({})
    assert adapter.topic_block() == ""
    adapter.set_topic({"prediction_goal": None})
    assert adapter.topic_block(feed_is_empty=True) == ""


def test_empty_feed_tells_the_agent_to_post():
    """The cold-start deadlock.

    On round one nobody has posted, so "observe before engaging" is the
    reasonable choice — and if every agent makes it, the feed never fills and
    the run ends at zero events across every round with no error raised.
    """
    adapter = _bare_adapter()
    adapter.set_topic({"prediction_goal": GOAL})

    cold = adapter.topic_block(feed_is_empty=True)
    warm = adapter.topic_block(feed_is_empty=False)

    assert "POST" in cold
    assert "POST" not in warm
    assert len(cold) > len(warm)


def test_every_adapter_prompt_carries_the_topic(adapters):
    """All twelve stored `prediction_goal` and none of them read it.

    The subject reached agents only through the persona bio, which is generated
    *from* the subject — so the simulation silently depended on the bio
    generator succeeding, and produced silent agents when it did not.
    """
    for adapter in adapters:
        module = inspect.getmodule(type(adapter))
        prompt = getattr(module, "_ACTION_PROMPT", None)
        assert prompt is not None, f"{adapter.platform_id} has no _ACTION_PROMPT"
        assert "{topic}" in prompt, (
            f"{adapter.platform_id} never tells its agents what the simulation "
            "is about"
        )


def test_every_adapter_captures_the_topic_on_initialize(adapters):
    for adapter in adapters:
        source = inspect.getsource(type(adapter).initialize)
        assert "set_topic(config)" in source, (
            f"{adapter.platform_id}.initialize does not capture prediction_goal"
        )


def test_every_adapter_passes_the_topic_into_its_prompt(adapters):
    for adapter in adapters:
        source = inspect.getsource(type(adapter)._decide_action)
        assert "topic=self.topic_block(" in source, (
            f"{adapter.platform_id}._decide_action does not pass the topic"
        )


def test_agent_generation_has_room_for_a_full_profile():
    """A truncated profile becomes a stub agent that knows nothing about the topic.

    `max_tokens=400` truncated 20 of 25 profiles mid-JSON, which is what turned
    the missing-topic bug from a quality problem into a zero-event run. Raising
    it to 900 fixed that — and then the Founder lens added an ICP context block
    to the same prompt, the model matched the richer prompt with a longer answer,
    and profiles started truncating again on the first live run.

    So this asserts a **floor**, not a literal. Pinning the exact number made the
    test fail on the fix rather than on the regression, which is backwards: what
    matters is that there is headroom above the ~376-token mean, not that the
    ceiling is any particular value.
    """
    from app.workers import simulation_tasks

    source = inspect.getsource(simulation_tasks.run_prepare_agents)
    match = re.search(r"max_tokens=(\d+)", source)
    assert match, "agent generation no longer sets max_tokens explicitly"
    assert int(match.group(1)) >= 1400, (
        f"agent generation max_tokens is {match.group(1)}; profiles truncate "
        "below ~1400 once an ICP context block is in the prompt"
    )


def test_agent_usernames_are_deduped_before_insert():
    """Adapters address agents by username and nothing else.

    Asked for 100 handles the model produced 45 distinct ones — nine agents
    named `mchen_itdir`. Those nine shared memory and all their events were
    attributed to one row, so nine independent observations counted as one and
    every confidence interval was drawn from a swarm less than half its size.
    """
    from app.workers import simulation_tasks

    source = inspect.getsource(simulation_tasks.run_prepare_agents)
    assert "seen_usernames" in source
    assert 'agent["profile"]["username"] = name' in source


def test_dedup_logic_produces_unique_names():
    """The exact loop used in run_prepare_agents, exercised on a collision."""
    agents = [{"username": u} for u in ["mchen", "mchen", "mchen", "sarah", "mchen2"]]
    seen: set[str] = set()
    for agent in agents:
        base = agent["username"]
        name, suffix = base, 2
        while name in seen:
            name = f"{base}{suffix}"
            suffix += 1
        seen.add(name)
        agent["username"] = name

    names = [a["username"] for a in agents]
    assert len(set(names)) == len(names), names
    assert names[0] == "mchen"
    # "mchen2" is taken by the second collision, so the pre-existing literal
    # "mchen2" must move rather than collide.
    assert "mchen2" in names and names.count("mchen2") == 1


def test_runner_detects_duplicate_usernames():
    """A run prepared before the fix must not fail silently."""
    from app.workers import simulation_tasks

    source = inspect.getsource(simulation_tasks.run_simulation)
    assert "duplicate_agent_usernames" in source


# ── Agent identity: username is a display handle, not an identity ──

def test_agent_key_prefers_the_id():
    adapter = _bare_adapter()
    assert adapter.agent_key({"agent_id": "uuid-1", "username": "mchen"}) == "uuid-1"


def test_agent_key_falls_back_to_username_when_no_id():
    """Adapter unit tests construct agents without ids; the live pipeline does not."""
    adapter = _bare_adapter()
    assert adapter.agent_key({"username": "mchen"}) == "mchen"


def test_colliding_usernames_do_not_share_memory():
    """The regression test for the whole class of bug.

    Two agents with identical handles and different ids must remain two agents.
    Before identity moved to `agent_id`, nine agents named `mchen_itdir` shared
    one memory and behaved as a single confused actor.
    """
    adapter = _bare_adapter()
    adapter._init_history()

    a = {"agent_id": "uuid-a", "username": "mchen_itdir"}
    b = {"agent_id": "uuid-b", "username": "mchen_itdir"}

    adapter.record_action(adapter.agent_key(a), 1, "Posted: we already use Datadog")
    adapter.record_action(adapter.agent_key(b), 1, "Posted: this looks useful")

    mem_a = adapter.get_agent_memory(adapter.agent_key(a))
    mem_b = adapter.get_agent_memory(adapter.agent_key(b))

    assert "Datadog" in mem_a and "Datadog" not in mem_b
    assert "useful" in mem_b and "useful" not in mem_a


def test_every_adapter_stamps_the_agent_id_on_its_events(adapters):
    """Attribution rides on the id, not on the display handle."""
    for adapter in adapters:
        source = inspect.getsource(type(adapter)._decide_action)
        assert 'agent_id=agent.get("agent_id")' in source, (
            f"{adapter.platform_id} emits events without an agent id"
        )


def test_every_adapter_keys_memory_on_identity(adapters):
    for adapter in adapters:
        source = inspect.getsource(type(adapter)._decide_action)
        assert 'get_agent_memory(agent["username"])' not in source, (
            f"{adapter.platform_id} keys agent memory on a display handle"
        )
        assert 'record_action(agent["username"]' not in source, (
            f"{adapter.platform_id} keys agent memory on a display handle"
        )


def test_simulation_event_carries_an_agent_id():
    from datetime import UTC, datetime

    from app.services.platforms.base_adapter import SimulationEvent

    event = SimulationEvent(
        event_type="post", agent_id="uuid-a", agent_username="mchen",
        platform="twitter_x", round_number=1, variant="a",
        timestamp=datetime.now(UTC),
    )
    assert event.agent_id == "uuid-a"


def test_runner_attributes_events_by_id_not_username():
    from app.workers import simulation_tasks

    source = inspect.getsource(simulation_tasks.run_simulation)
    assert '"agent_id": a["id"]' in source, "adapters are not given the agent id"
    assert "event.agent_id" in source, "runner does not attribute by agent id"


def test_migration_019_enforces_uniqueness_in_the_database():
    """Layer 3. Conventions in code are enforced by whoever writes the next
    caller; a database constraint is not."""
    import pathlib

    sql = pathlib.Path("scripts/migrations/019_agent_username_uniqueness.sql").read_text(
        encoding="utf-8"
    )
    assert "CREATE UNIQUE INDEX" in sql
    assert "simulation_agents (simulation_id, username)" in sql
    # Must stay gated until the merge — master has no dedup and would break.
    assert "DO NOT APPLY TO PRODUCTION UNTIL v2 IS MERGED" in sql
