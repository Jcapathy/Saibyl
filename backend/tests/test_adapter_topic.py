"""Regression tests for the two bugs that made a live run produce zero events.

Both predate Phase 1 and neither raised an error. A run simply completed with
nothing in it, which is the worst possible failure mode for a product whose
output is a measurement.
"""
from __future__ import annotations

import inspect

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
    """max_tokens=400 truncated 20 of 25 profiles mid-JSON on the fast model.

    A truncated profile fails json.loads and falls back to a stub that knows
    nothing about the topic — which is what turned the missing-topic bug from a
    quality problem into a zero-event run.
    """
    from app.workers import simulation_tasks

    source = inspect.getsource(simulation_tasks.run_prepare_agents)
    assert "max_tokens=400" not in source
    assert "max_tokens=900" in source


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
