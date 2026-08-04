"""The V1 reference defect, across every adapter.

Every adapter renders its feed as `[<id>] @author: text` and then asks the model
for `COMMENT <post_id>: …`. The model copies the id **with the brackets it was
shown in**, inconsistently — roughly four times in five on the run that exposed
this. Every `if p.id == post_id` in the package then silently failed.

The consequence was live for all of V1 and nothing ever errored: reactions never
found their post, `upvotes`/`likes` never incremented, and `_hot_score` ranked
every feed by recency alone. The feed was simply not the feed the design
describes, on every run ever made.

These tests are parameterised over the whole registry on purpose. The defect was
identical in twelve places, so a fix proved in one adapter proves nothing.
"""
from __future__ import annotations

import pytest

from app.services.platforms.base_adapter import BasePlatformAdapter
from app.services.platforms.registry import PLATFORM_REGISTRY, load_all_adapters

load_all_adapters()

ADAPTERS = sorted(PLATFORM_REGISTRY.items())


def test_every_adapter_is_registered():
    """A guard on the parameterisation itself — an empty registry would make
    every test below vacuously pass."""
    assert len(ADAPTERS) >= 12


# ── The helper ───────────────────────────────────────────

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("[a1b2c3]", "a1b2c3"),
        ("a1b2c3", "a1b2c3"),
        ("(a1b2c3)", "a1b2c3"),
        ("  a1b2c3,", "a1b2c3"),
        ("a1b2c3.", "a1b2c3"),
        ("'a1b2c3'", "a1b2c3"),
        ("<a1b2c3>", "a1b2c3"),
        ("[]", ""),
        ("", ""),
        (None, ""),
    ],
)
def test_post_ref_strips_decoration(raw, expected):
    assert BasePlatformAdapter.post_ref(raw) == expected


def test_post_ref_does_not_collapse_distinct_ids():
    """Stripping must never make two different posts the same post."""
    assert BasePlatformAdapter.post_ref("[a1b2c3]") != BasePlatformAdapter.post_ref("[a1b2c4]")


# ── The adapters ─────────────────────────────────────────

@pytest.mark.parametrize("platform_id,cls", ADAPTERS, ids=[p for p, _ in ADAPTERS])
@pytest.mark.asyncio
async def test_a_reaction_with_a_bracketed_id_still_finds_its_post(platform_id, cls):
    """The V1 defect, stated as the behaviour it broke.

    A reaction whose id arrives decorated must still register against the post.
    Before the fix this silently did nothing on every adapter.
    """
    adapter = cls()
    await adapter.initialize(
        config={"prediction_goal": "A new product", "simulation_id": "t"},
        agents=[{"agent_id": "1", "username": "alice", "persona": "buyer", "variant": "a"}],
    )
    post = await adapter.post("alice", "A headline | And a body.")

    from app.services.platforms.base_adapter import ReactionType

    await adapter.react("bob", f"[{post.id}]", ReactionType.LIKE)

    # The reaction landed somewhere the adapter can see it — either on the post's
    # own counters or in its reaction index, depending on the platform's model.
    # Deliberately not asserting a snapshot key: `get_state_snapshot` reports
    # different fields per platform, and pinning one here would test the
    # snapshot's shape rather than whether the reaction arrived.
    engagement = sum(
        v for v in post.metadata.values() if isinstance(v, int)
    )
    reacted = getattr(adapter, "_reactions", {})
    assert engagement > 0 or post.id in reacted, (
        f"{platform_id}: a bracketed reaction id did not reach the post"
    )


@pytest.mark.parametrize("platform_id,cls", ADAPTERS, ids=[p for p, _ in ADAPTERS])
@pytest.mark.asyncio
async def test_a_comment_with_a_bracketed_id_attaches_to_the_post(platform_id, cls):
    adapter = cls()
    await adapter.initialize(
        config={"prediction_goal": "A new product", "simulation_id": "t"},
        agents=[{"agent_id": "1", "username": "alice", "persona": "buyer", "variant": "a"}],
    )
    post = await adapter.post("alice", "A headline | And a body.")

    comment = await adapter.comment("bob", f"[{post.id}]", "I have a question about this.")

    assert comment.post_id == post.id, (
        f"{platform_id}: comment stored a decorated post_id, so it is attached "
        f"to a post that does not exist"
    )
