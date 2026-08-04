from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import structlog

from app.core.llm_client import llm_fast
from app.services.platforms.base_adapter import (
    BasePlatformAdapter,
    Comment,
    Post,
    ReactionType,
    SimulationEvent,
)
from app.services.platforms.registry import register_adapter
from app.services.refs import enum_ref

logger = structlog.get_logger()

# LinkedIn's five verbs, as `ReactionType` members rather than bare strings.
# They were bare strings, and `react()` mapped anything that was not literally
# `"like"` back onto `"like"` — which, since `ReactionType` carried no
# `celebrate`/`support`/`insightful`/`curious`, was *all five of them*. The
# breakdown this adapter maintains therefore had one non-zero key on every run.
_LINKEDIN_REACTION_MAP: dict[str, ReactionType] = {
    r.value: r
    for r in (
        ReactionType.LIKE,
        ReactionType.CELEBRATE,
        ReactionType.SUPPORT,
        ReactionType.INSIGHTFUL,
        ReactionType.CURIOUS,
    )
}
_LINKEDIN_REACTIONS = frozenset(_LINKEDIN_REACTION_MAP)

_ACTION_PROMPT = (
    "You are {username} on LinkedIn. Persona: {persona}\n"
    "Professional feed:\n{feed}\n\n"
    "{topic}"
    "{memory}"
    "Round {round}. Pick ONE action (exact format). Keep a professional tone.\n"
    "POST: <professional post text>\n"
    "COMMENT <post_id>: <comment text>\n"
    "REACT <post_id> <like|celebrate|support|insightful|curious>\n"
    "NOTHING"
)


def _connection_weight(agent: dict, post: Post) -> float:
    connections = agent.get("connections", [])
    base = 1.0
    if post.author_username in connections:
        base = 3.0
    engagement = post.metadata.get("reactions_count", 0)
    return base + engagement * 0.5


@register_adapter
class LinkedInAdapter(BasePlatformAdapter):
    platform_id = "linkedin"
    platform_name = "LinkedIn"
    supports_reactions = True
    supports_dms = False
    max_post_length = 3000
    max_comment_length = 1250

    async def initialize(self, config: dict, agents: list) -> None:
        self._init_history()
        self._config = config
        self.set_topic(config)
        self._agents = agents
        self._posts: list[Post] = []
        self._comments: list[Comment] = []
        self._reactions: dict[str, dict[str, str]] = {}

    async def run_round(self, round_number: int) -> AsyncGenerator[SimulationEvent, None]:
        for agent in self._agents:
            action = await self._decide_action(agent, round_number)
            if action:
                yield action

    async def get_feed(self, agent_username: str) -> list[Post]:
        agent = next((a for a in self._agents if a["username"] == agent_username), {})
        scored = sorted(
            self._posts,
            key=lambda p: _connection_weight(agent, p),
            reverse=True,
        )
        return scored[:15]

    async def post(self, agent_username: str, content: str, metadata: dict | None = None) -> Post:
        meta = metadata or {}
        meta.setdefault("reactions_count", 0)
        meta.setdefault("reactions_breakdown", {r: 0 for r in _LINKEDIN_REACTIONS})
        p = Post(
            id=uuid.uuid4().hex[:12],
            platform=self.platform_id,
            author_username=agent_username,
            content=content[: self.max_post_length],
            created_at=datetime.now(tz=UTC),
            metadata=meta,
        )
        self._posts.append(p)
        return p

    async def comment(self, agent_username: str, post_id: str, content: str) -> Comment:
        # V1 defect: the model echoes the id in the brackets the feed showed
        # it, so an un-normalised post_id never matches p.id. See post_ref.
        post_id = self.post_ref(post_id)
        c = Comment(
            id=uuid.uuid4().hex[:12],
            post_id=post_id,
            platform=self.platform_id,
            author_username=agent_username,
            content=content[: self.max_comment_length],
            created_at=datetime.now(tz=UTC),
        )
        self._comments.append(c)
        return c

    async def react(self, agent_username: str, post_id: str, reaction: ReactionType) -> None:
        # V1 defect: the model echoes the id in the brackets the feed showed
        # it, so an un-normalised post_id never matches p.id. See post_ref.
        post_id = self.post_ref(post_id)
        self._reactions.setdefault(post_id, {})[agent_username] = reaction.value
        for p in self._posts:
            if p.id == post_id:
                p.metadata["reactions_count"] = p.metadata.get("reactions_count", 0) + 1
                breakdown = p.metadata.setdefault("reactions_breakdown", {})
                # Recorded under the verb that actually happened. A reaction
                # outside LinkedIn's vocabulary gets its own key rather than
                # being folded into `like`: a value we did not expect must stay
                # visible, and the caller has already rejected the ones that are
                # not real verbs at all.
                breakdown[reaction.value] = breakdown.get(reaction.value, 0) + 1
                if reaction.value not in _LINKEDIN_REACTIONS:
                    logger.warning(
                        "reaction_outside_platform_vocabulary",
                        platform=self.platform_id,
                        reaction=reaction.value,
                    )
                return

    def get_state_snapshot(self) -> dict:
        return {
            "platform": self.platform_id,
            "total_posts": len(self._posts),
            "total_comments": len(self._comments),
            "total_reactions": sum(len(v) for v in self._reactions.values()),
        }

    # ------------------------------------------------------------------
    async def _decide_action(self, agent: dict, round_number: int) -> SimulationEvent | None:
        feed = await self.get_feed(agent["username"])
        feed_text = "\n".join(
            f"[{p.id}] {p.author_username}: {p.content[:120]}... ({p.metadata.get('reactions_count', 0)} reactions)"
            for p in feed[:6]
        ) or "(empty)"
        prompt = _ACTION_PROMPT.format(
            username=agent["username"],
            persona=agent.get("persona", "professional"),
            feed=feed_text,
            topic=self.topic_block(feed_is_empty=not feed),
            memory=self.get_agent_memory(self.agent_key(agent)),
            round=round_number,
        )
        raw = await llm_fast([{"role": "user", "content": prompt}], max_tokens=256)
        await asyncio.sleep(0)

        now = datetime.now(tz=UTC)
        variant = agent.get("variant", "control")
        line = raw.strip().split("\n")[0].strip()

        if line.upper().startswith("POST:"):
            text = line[5:].strip()
            p = await self.post(agent["username"], text)
            self.record_action(self.agent_key(agent), round_number, f"Posted: {text[:80]}")
            return SimulationEvent(
                event_type="post", agent_id=agent.get("agent_id"), agent_username=agent["username"],
                platform=self.platform_id, round_number=round_number,
                variant=variant, content=p.content, target_id=p.id, timestamp=now,
            )

        if line.upper().startswith("COMMENT"):
            match = re.match(r"COMMENT\s+(\S+):\s*(.+)", line, re.IGNORECASE)
            if match:
                pid, text = self.post_ref(match.group(1)), match.group(2)
                c = await self.comment(agent["username"], pid, text)
                self.record_action(self.agent_key(agent), round_number, f"Commented on {pid}: {text[:80]}")
                return SimulationEvent(
                    event_type="comment", agent_id=agent.get("agent_id"), agent_username=agent["username"],
                    platform=self.platform_id, round_number=round_number,
                    variant=variant, content=c.content, target_id=pid, timestamp=now,
                )

        if line.upper().startswith("REACT"):
            match = re.match(r"REACT\s+(\S+)\s+(\S+)", line, re.IGNORECASE)
            if match:
                pid, rtype = self.post_ref(match.group(1)), match.group(2)
                # **An unrecognised verb is dropped, not defaulted.** This was
                # `if rtype not in _LINKEDIN_REACTIONS: rtype = "like"`, so an
                # agent reacting with anything outside the five — including a
                # dissenting verb the model reached for because the persona was
                # dissenting — was recorded as approval. A signal the product is
                # sold on must never silently invert.
                #
                # `enum_ref` first absorbs decoration, casing and separators,
                # because the prompt renders the vocabulary pipe-joined and the
                # model copies it back the way it was shown. What survives that
                # is dropped and logged rather than guessed at — the same choice
                # as Facebook, for the same reason.
                verb = enum_ref(rtype, _LINKEDIN_REACTIONS)
                if verb is None:
                    logger.warning(
                        "reaction_verb_unrecognised",
                        platform=self.platform_id,
                        verb=rtype,
                        detail="dropped rather than defaulted to LIKE; this "
                               "agent's action is unmeasured this round",
                    )
                    return None
                await self.react(agent["username"], pid, _LINKEDIN_REACTION_MAP[verb])
                self.record_action(self.agent_key(agent), round_number, f"Reacted {verb} on {pid}")
                return SimulationEvent(
                    event_type="react", agent_id=agent.get("agent_id"), agent_username=agent["username"],
                    platform=self.platform_id, round_number=round_number,
                    variant=variant, target_id=pid,
                    metadata={"reaction": verb}, timestamp=now,
                )

        return None
