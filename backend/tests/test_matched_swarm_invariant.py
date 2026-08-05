"""The matched swarm is a statistical precondition, not just a cost saving.

DECISIONS §16b scores the variant comparison as a **paired** design: the winner
test is computed from per-agent differences between arenas, which is only valid
because every arena receives the same agent rows, by id.

If a future change ever gives each arena its own agents, the paired estimator
does not become conservative — it becomes **wrong**, and silently. Every number
still computes, the scoreboard still renders, and the intervals it reports are
too narrow because they assume a correlation that no longer exists. A test that
is too narrow names winners that are not there, which is precisely the failure
the refusal rule exists to prevent.

That is the same shape as `test_each_arena_gets_its_own_adapter_instance`: a
structural property nothing would notice losing. This file guards the other
half of it — that instance is fresh, and the swarm is shared.

⚠ These two invariants pull in opposite directions and both must hold:

    adapters   MUST NOT be shared across arenas  (or every variant is in one
               conversation and the comparison measures nothing)
    agents     MUST be shared across arenas      (or the comparison is unpaired
               and the paired estimator overstates its confidence)

Anyone "simplifying" the arena loop needs to keep both.
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path

from app.workers import simulation_tasks


def _run_simulation_source() -> str:
    return inspect.getsource(simulation_tasks.run_simulation)


def test_every_arena_receives_the_same_agent_rows():
    """The agent list is built per platform, outside the arena loop.

    Built *inside* the loop it could diverge per arena — filtered, sampled or
    re-ordered — and nothing downstream would report it. Asserted on structure
    rather than on a comment, because a comment is a claim and this is the
    invariant DECISIONS §16b rests on.
    """
    source = _run_simulation_source()
    # dedent, not cleandoc: cleandoc treats the first line specially, which is
    # correct for a docstring and wrong for source.
    tree = ast.parse(textwrap.dedent(source))

    platform_agents_assign: ast.AST | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "platform_agents":
                    platform_agents_assign = node

    assert platform_agents_assign is not None, (
        "`platform_agents` is gone. If the swarm is now assembled some other "
        "way, re-establish that every arena gets the same agent rows before "
        "trusting the paired winner test — see DECISIONS §16b."
    )

    # The arena loop must not contain the agent-list construction.
    for node in ast.walk(tree):
        if not isinstance(node, ast.For):
            continue
        target = node.target
        if isinstance(target, ast.Name) and target.id == "arena":
            inner = {
                t.id
                for sub in ast.walk(node)
                if isinstance(sub, ast.Assign)
                for t in sub.targets
                if isinstance(t, ast.Name)
            }
            assert "platform_agents" not in inner, (
                "The agent list is being built inside the per-arena loop, so "
                "arenas can diverge. The paired winner test in DECISIONS §16b "
                "assumes every arena sees the same agents; it is not "
                "conservative when that breaks, it is wrong."
            )


def test_the_per_agent_variant_field_stays_meaningless():
    """Under matched swarms an agent belongs to every arena.

    `simulation_agents.variant` is a V1 artifact. If someone starts populating
    it per agent, that is the signal a swarm has been split — the arena is a
    property of the event, not of the agent.
    """
    source = _run_simulation_source()
    assert '"variant": None' in source, (
        "The runner is stamping a per-agent variant. Under matched swarms an "
        "agent is in every arena, so a per-agent variant means the swarm was "
        "split — which invalidates the paired comparison."
    )


def test_both_arena_invariants_are_documented_together():
    """The two invariants are easy to break by 'simplifying' one of them.

    Sharing adapters and sharing agents look like the same kind of change and
    are opposites. This asserts the reasoning is present where someone editing
    the loop will read it, because the defect it prevents is invisible at
    runtime.
    """
    source = _run_simulation_source()
    assert "matched swarm" in source.lower()
    assert "fresh" in source.lower() or "shared object" in source.lower()


def test_the_decision_record_exists():
    """§16b is what a future session will look for when the estimator confuses
    them. A decision that is implemented but unrecorded becomes folklore."""
    decisions = Path(__file__).resolve().parents[2] / "docs" / "DECISIONS_V2.md"
    if not decisions.exists():  # docs live outside some checkouts
        return
    text = decisions.read_text(encoding="utf-8")
    assert "16b" in text and "paired" in text.lower(), (
        "DECISIONS_V2 §16b is missing. The paired estimator changes how a "
        "shipped number is computed; without the record, the next session "
        "finds an unexplained statistic."
    )
