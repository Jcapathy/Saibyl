"""A decorated model action line must resolve to the right post id.

The sibling of `test_adapter_post_refs.py`, one layer earlier. That file proved
`post_ref` repairs a *value* the model decorated — `[a1b2c3]` → `a1b2c3`. This
one proves the adapters extract the right value in the first place.

Every adapter read the id out of a bare verb line as
`line.split(maxsplit=1)[1].strip()`, which is **the rest of the line, not the
id**. A model that volunteers a reason — `UPVOTE [a1b2c3] - solid point`, which
is exactly what a persona prompt encourages — produced the id
`a1b2c3] - solid point`. `post_ref` could not repair it: it strips edges by
design, so the separator *inside* the value survives. Fifteen sites, twelve
adapters, and the same silent outcome as the V1 defect — a reaction that
registers against nothing, a counter that never moves, a feed that ranks by
recency.

Parameterised over the whole registry, because a fix proved in one adapter
proves nothing about the other eleven.
"""
from __future__ import annotations

import inspect
import sys

import pytest

from app.services.platforms.base_adapter import BasePlatformAdapter
from app.services.platforms.registry import PLATFORM_REGISTRY, load_all_adapters

load_all_adapters()

ADAPTERS = sorted(PLATFORM_REGISTRY.items())

# The reaction line each adapter's own prompt asks for, with a trailing comment
# the model was never asked for and routinely supplies anyway. `{ref}` is
# substituted with the id as the feed displayed it, in brackets.
#
# Written out per platform rather than derived from `_ACTION_PROMPT`, because a
# test that parses the prompt would fail in the same way as the code it guards.
REACTION_LINES = {
    "custom": "REACT {ref} - nice one",
    "discord": "REACT {ref} thumbsup - nice one",
    "facebook": "REACT {ref} ANGRY - this is a bad move",
    "hacker_news": "UPVOTE {ref} - solid point",
    "instagram": "LIKE {ref} - nice one",
    "linkedin": "REACT {ref} insightful - good read",
    "news_comments": "UPVOTE {ref} - agreed",
    "reddit": "UPVOTE {ref} - solid point",
    "threads": "LIKE {ref} - nice one",
    "tiktok": "LIKE {ref} - nice one",
    "twitter_x": "LIKE {ref} - nice one",
    "youtube": "LIKE {ref} - nice one",
}

AGENT = {"agent_id": "agent-1", "username": "alice", "persona": "buyer", "variant": "a"}
REACTOR = {"agent_id": "agent-2", "username": "bob", "persona": "skeptic", "variant": "a"}


def test_every_adapter_has_a_reaction_line():
    """A guard on the parameterisation. A thirteenth adapter must be added here
    rather than skipped, which is how `_flag_post` stayed broken for a year."""
    assert set(REACTION_LINES) == {p for p, _ in ADAPTERS}


def _stub_llm(monkeypatch, cls, line: str) -> None:
    async def _fake(*_args, **_kwargs) -> str:
        return line

    monkeypatch.setattr(sys.modules[cls.__module__], "llm_fast", _fake)


async def _seed_target(platform_id: str, adapter) -> str:
    """The id this platform's reaction verb is actually pointed at.

    News comments is the exception and it is the whole of audit item 15: its
    feed renders *comments* and asks for `UPVOTE <comment_id>`, so the id an
    agent can type is a comment's, never the seeded article's.
    """
    post = await adapter.post("alice", "A headline | And a body.")
    if platform_id == "news_comments":
        comment = await adapter.comment("alice", post.id, "First reaction to this.")
        return comment.id
    return post.id


# ── The shared helper ────────────────────────────────────

@pytest.mark.parametrize(
    "line,expected",
    [
        # The audit's own example.
        ("UPVOTE [a1b2c3] - solid", "a1b2c3"),
        ("UPVOTE a1b2c3", "a1b2c3"),
        ("UPVOTE [a1b2c3]", "a1b2c3"),
        ("LIKE (a1b2c3) because it is true", "a1b2c3"),
        ("SHARE 'a1b2c3', worth passing on", "a1b2c3"),
        ("DOWNVOTE  [a1b2c3]  ", "a1b2c3"),
        ("FLAG <a1b2c3>: spam", "a1b2c3"),
        # No id at all — the caller's "no action" path, not a guess.
        ("UPVOTE", ""),
        ("", ""),
    ],
)
def test_action_ref_takes_the_id_and_not_the_rest_of_the_line(line, expected):
    assert BasePlatformAdapter.action_ref(line) == expected


def test_action_ref_does_not_collapse_distinct_ids():
    assert BasePlatformAdapter.action_ref("UPVOTE [a1b2c3] - x") != (
        BasePlatformAdapter.action_ref("UPVOTE [a1b2c4] - x")
    )


@pytest.mark.parametrize("platform_id,cls", ADAPTERS, ids=[p for p, _ in ADAPTERS])
def test_no_adapter_reads_an_id_as_the_rest_of_the_line(platform_id, cls):
    """The defect, stated as the code shape that produced it.

    Behaviour tests below prove today's adapters are right; this one stops the
    shape being reintroduced by the next person who copies an existing branch.
    """
    source = inspect.getsource(cls._decide_action)
    assert "split(maxsplit=1)" not in source, (
        f"{platform_id} reads a post id as the rest of the line; use action_ref"
    )


# ── The adapters ─────────────────────────────────────────

@pytest.mark.parametrize("platform_id,cls", ADAPTERS, ids=[p for p, _ in ADAPTERS])
@pytest.mark.asyncio
async def test_a_decorated_reaction_line_resolves_to_the_right_id(
    platform_id, cls, monkeypatch
):
    """`UPVOTE [a1b2c3] - solid point` must react to `a1b2c3`."""
    adapter = cls()
    await adapter.initialize(
        config={"prediction_goal": "A new product", "simulation_id": "t"},
        agents=[AGENT, REACTOR],
    )
    target_id = await _seed_target(platform_id, adapter)

    _stub_llm(monkeypatch, cls, REACTION_LINES[platform_id].format(ref=f"[{target_id}]"))
    event = await adapter._decide_action(REACTOR, 1)

    assert event is not None, f"{platform_id}: the reaction produced no event"
    assert event.target_id == target_id, (
        f"{platform_id}: reacted to {event.target_id!r} instead of {target_id!r}"
    )
    assert target_id in adapter._reactions, (
        f"{platform_id}: the reaction never reached the adapter's index"
    )


@pytest.mark.parametrize("platform_id,cls", ADAPTERS, ids=[p for p, _ in ADAPTERS])
@pytest.mark.asyncio
async def test_an_undecorated_reaction_line_still_resolves(
    platform_id, cls, monkeypatch
):
    """The other four times in five. A fix for the decorated form that broke the
    bare form would trade one silent failure for another."""
    adapter = cls()
    await adapter.initialize(
        config={"prediction_goal": "A new product", "simulation_id": "t"},
        agents=[AGENT, REACTOR],
    )
    target_id = await _seed_target(platform_id, adapter)

    _stub_llm(monkeypatch, cls, REACTION_LINES[platform_id].format(ref=target_id))
    event = await adapter._decide_action(REACTOR, 1)

    assert event is not None and event.target_id == target_id


@pytest.mark.asyncio
async def test_news_comments_upvote_reaches_the_comment(monkeypatch):
    """Audit item 15. The feed renders comments; `react` resolved against
    `self._posts`, which holds only the seeded article whose id is never shown,
    so 100% of upvotes on this platform matched nothing."""
    from app.services.platforms.adapters.news_comments import NewsCommentsAdapter

    adapter = NewsCommentsAdapter()
    await adapter.initialize(
        config={"prediction_goal": "A new product", "simulation_id": "t"},
        agents=[AGENT, REACTOR],
    )
    article = adapter._posts[0]
    comment = await adapter.comment("alice", article.id, "This will not scale.")

    _stub_llm(monkeypatch, NewsCommentsAdapter, f"UPVOTE [{comment.id}] - agreed")
    event = await adapter._decide_action(REACTOR, 1)

    assert event is not None and event.target_id == comment.id
    assert adapter._comment_upvotes.get(comment.id) == 1, (
        "the upvote did not land on the comment it named"
    )
    assert adapter.get_state_snapshot()["comment_upvotes"] == 1


@pytest.mark.asyncio
async def test_hacker_news_flag_reaches_the_post(monkeypatch):
    """Audit item 14. `_flag_post` is a private helper rather than one of the
    three abstract methods, so the twelve-adapter fix missed it and HN's
    moderation weighting was inert on every run ever made."""
    from app.services.platforms.adapters.hacker_news import HackerNewsAdapter

    adapter = HackerNewsAdapter()
    await adapter.initialize(
        config={"prediction_goal": "A new product", "simulation_id": "t"},
        agents=[AGENT, REACTOR],
    )
    post = await adapter.post("alice", "A headline | And a body.")

    _stub_llm(monkeypatch, HackerNewsAdapter, f"FLAG [{post.id}] - this is spam")
    event = await adapter._decide_action(REACTOR, 1)

    assert event is not None and event.target_id == post.id
    assert post.metadata["flags"] == 1, "the flag never reached the post"


# ── Unrecognised reaction verbs ──────────────────────────

@pytest.mark.asyncio
async def test_facebook_keeps_an_angry_reaction_angry(monkeypatch):
    """Audit item 17. `_FB_REACTION_MAP.get(rtype, ReactionType.LIKE)` turned
    every backlash reaction the model decorated into its opposite."""
    from app.services.platforms.adapters.facebook import FacebookAdapter

    adapter = FacebookAdapter()
    await adapter.initialize(
        config={"prediction_goal": "A new product", "simulation_id": "t"},
        agents=[AGENT, REACTOR],
    )
    post = await adapter.post("alice", "We are raising prices.")

    _stub_llm(monkeypatch, FacebookAdapter, f"REACT [{post.id}] [ANGRY.] - awful")
    event = await adapter._decide_action(REACTOR, 1)

    assert event is not None
    assert event.metadata["reaction"] == "angry", "a decorated ANGRY became a LIKE"
    assert post.metadata["angry"] == 1
    assert post.metadata["likes"] == 0


@pytest.mark.asyncio
async def test_facebook_drops_an_unrecognised_verb_rather_than_liking_it(monkeypatch):
    from app.services.platforms.adapters.facebook import FacebookAdapter

    adapter = FacebookAdapter()
    await adapter.initialize(
        config={"prediction_goal": "A new product", "simulation_id": "t"},
        agents=[AGENT, REACTOR],
    )
    post = await adapter.post("alice", "We are raising prices.")

    _stub_llm(monkeypatch, FacebookAdapter, f"REACT [{post.id}] FURIOUS")
    event = await adapter._decide_action(REACTOR, 1)

    assert event is None, "an unrecognised verb produced an event anyway"
    assert post.metadata["likes"] == 0, "an unrecognised verb was counted as approval"


@pytest.mark.asyncio
async def test_linkedin_records_the_verb_the_agent_used(monkeypatch):
    """Audit item 17, second site. All five LinkedIn verbs collapsed to `like`:
    the unrecognised ones by an explicit default, the recognised ones because
    `ReactionType` carried no member for them."""
    from app.services.platforms.adapters.linkedin import LinkedInAdapter

    adapter = LinkedInAdapter()
    await adapter.initialize(
        config={"prediction_goal": "A new product", "simulation_id": "t"},
        agents=[AGENT, REACTOR],
    )
    post = await adapter.post("alice", "A thought about hiring.")

    _stub_llm(monkeypatch, LinkedInAdapter, f"REACT [{post.id}] Insightful - good read")
    event = await adapter._decide_action(REACTOR, 1)

    assert event is not None and event.metadata["reaction"] == "insightful"
    breakdown = post.metadata["reactions_breakdown"]
    assert breakdown["insightful"] == 1
    assert breakdown["like"] == 0, "an insightful reaction was recorded as a like"


@pytest.mark.asyncio
async def test_linkedin_drops_an_unrecognised_verb(monkeypatch):
    from app.services.platforms.adapters.linkedin import LinkedInAdapter

    adapter = LinkedInAdapter()
    await adapter.initialize(
        config={"prediction_goal": "A new product", "simulation_id": "t"},
        agents=[AGENT, REACTOR],
    )
    post = await adapter.post("alice", "A thought about hiring.")

    _stub_llm(monkeypatch, LinkedInAdapter, f"REACT [{post.id}] outraged")
    event = await adapter._decide_action(REACTOR, 1)

    assert event is None
    assert post.metadata["reactions_count"] == 0


# ── The isolation guard, restated ────────────────────────

@pytest.mark.asyncio
async def test_a_reaction_in_one_arena_is_invisible_to_another():
    """Matched swarms depend on each arena owning its own feed. A reaction that
    leaked across instances would still compute every number."""
    from app.services.platforms.registry import get_adapter

    a, b = get_adapter("twitter_x"), get_adapter("twitter_x")
    for adapter in (a, b):
        await adapter.initialize(
            config={"prediction_goal": "A new product", "simulation_id": "t"},
            agents=[AGENT, REACTOR],
        )
    post = await a.post("alice", "Arena A only.")

    from app.services.platforms.base_adapter import ReactionType

    await a.react("bob", f"[{post.id}]", ReactionType.LIKE)

    assert a is not b
    assert b._posts == []
    assert b._reactions == {}
