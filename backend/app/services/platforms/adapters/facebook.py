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

_ACTION_PROMPT = (
    "You are {username} on Facebook. Persona: {persona}\n"
    "Current feed (recent posts):\n{feed}\n\n"
    "{topic}"
    "{memory}"
    "Round {round}. Pick ONE action and reply in the EXACT format:\n"
    "POST: <text>\n"
    "COMMENT <post_id>: <text>\n"
    "REACT <post_id> <type> (where type is LIKE/LOVE/HAHA/WOW/SAD/ANGRY)\n"
    "SHARE <post_id>\n"
    "NOTHING\n"
    "Keep posts under 63206 chars."
)

# Keyed on the enum's own values, which is what `enum_ref` matches against
# after casefolding and decoration-stripping. It used to be keyed on uppercase
# literals and read with `.get(rtype, ReactionType.LIKE)` — see `_decide_action`
# for why that default was the defect.
_FB_REACTION_MAP: dict[str, ReactionType] = {
    ReactionType.LIKE.value: ReactionType.LIKE,
    ReactionType.LOVE.value: ReactionType.LOVE,
    ReactionType.HAHA.value: ReactionType.HAHA,
    ReactionType.WOW.value: ReactionType.WOW,
    ReactionType.SAD.value: ReactionType.SAD,
    ReactionType.ANGRY.value: ReactionType.ANGRY,
}
_FB_REACTION_VERBS = frozenset(_FB_REACTION_MAP)


def _engagement_score(post_meta: dict) -> float:
    likes = post_meta.get("likes", 0)
    loves = post_meta.get("loves", 0)
    comments_count = post_meta.get("comments_count", 0)
    shares = post_meta.get("shares", 0)
    angry = post_meta.get("angry", 0)
    return likes * 1 + loves * 2 + comments_count * 3 + shares * 5 + angry * 1


@register_adapter
class FacebookAdapter(BasePlatformAdapter):
    platform_id = "facebook"
    platform_name = "Facebook"
    supports_reactions = True
    supports_dms = False
    max_post_length = 63206
    max_comment_length = 8000

    async def initialize(self, config: dict, agents: list) -> None:
        self._init_history()
        self._config = config
        self.set_topic(config)
        self._agents = agents
        self._posts: list[Post] = []
        self._comments: list[Comment] = []
        self._reactions: dict[str, dict[str, ReactionType]] = {}

    async def run_round(self, round_number: int) -> AsyncGenerator[SimulationEvent, None]:
        for agent in self._agents:
            action = await self._decide_action(agent, round_number)
            if action:
                yield action

    async def get_feed(self, agent_username: str) -> list[Post]:
        scored = sorted(
            self._posts,
            key=lambda p: _engagement_score(p.metadata),
            reverse=True,
        )
        return scored[:20]

    async def post(self, agent_username: str, content: str, metadata: dict | None = None) -> Post:
        meta = metadata or {}
        meta.setdefault("likes", 0)
        meta.setdefault("loves", 0)
        meta.setdefault("comments_count", 0)
        meta.setdefault("shares", 0)
        meta.setdefault("reactions", {"like": 0, "love": 0, "haha": 0, "wow": 0, "sad": 0, "angry": 0})
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
        for p in self._posts:
            if p.id == post_id:
                p.metadata["comments_count"] = p.metadata.get("comments_count", 0) + 1
                break
        return c

    async def react(self, agent_username: str, post_id: str, reaction: ReactionType) -> None:
        # V1 defect: the model echoes the id in the brackets the feed showed
        # it, so an un-normalised post_id never matches p.id. See post_ref.
        post_id = self.post_ref(post_id)
        self._reactions.setdefault(post_id, {})[agent_username] = reaction
        for p in self._posts:
            if p.id == post_id:
                reactions = p.metadata.setdefault(
                    "reactions",
                    {"like": 0, "love": 0, "haha": 0, "wow": 0, "sad": 0, "angry": 0},
                )
                key = reaction.value
                if key in reactions:
                    reactions[key] = reactions.get(key, 0) + 1
                # Update top-level counters for engagement scoring
                if reaction == ReactionType.LIKE:
                    p.metadata["likes"] = p.metadata.get("likes", 0) + 1
                elif reaction == ReactionType.LOVE:
                    p.metadata["loves"] = p.metadata.get("loves", 0) + 1
                elif reaction == ReactionType.ANGRY:
                    p.metadata["angry"] = p.metadata.get("angry", 0) + 1
                elif reaction == ReactionType.SHARE:
                    p.metadata["shares"] = p.metadata.get("shares", 0) + 1
                break

    def get_state_snapshot(self) -> dict:
        return {
            "platform": self.platform_id,
            "total_posts": len(self._posts),
            "total_comments": len(self._comments),
            "total_shares": sum(p.metadata.get("shares", 0) for p in self._posts),
        }

    # ------------------------------------------------------------------
    async def _decide_action(self, agent: dict, round_number: int) -> SimulationEvent | None:
        feed = await self.get_feed(agent["username"])
        feed_text = "\n".join(
            f"[{p.id}] {p.author_username}: {p.content[:120]}" for p in feed[:8]
        ) or "(empty)"
        prompt = _ACTION_PROMPT.format(
            username=agent["username"],
            persona=agent.get("persona", "average user"),
            feed=feed_text,
            topic=self.topic_block(feed_is_empty=not feed),
            memory=self.get_agent_memory(self.agent_key(agent)),
            round=round_number,
        )
        raw = await llm_fast([{"role": "user", "content": prompt}], max_tokens=200)
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
                variant=variant, content=p.content, target_id=p.id,
                metadata={}, timestamp=now,
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
                    variant=variant, content=c.content, target_id=pid,
                    timestamp=now,
                )

        if line.upper().startswith("REACT"):
            match = re.match(r"REACT\s+(\S+)\s+(\S+)", line, re.IGNORECASE)
            if match:
                pid, rtype = self.post_ref(match.group(1)), match.group(2)
                # **An unrecognised verb is dropped, not defaulted.** This was
                # `.get(rtype, ReactionType.LIKE)`: every `ANGRY.`, `angry`,
                # `[ANGRY]` or `FURIOUS` the model produced — and the prompt
                # renders the vocabulary slash-joined, so it comes back
                # decorated — became a LIKE. Backlash is the signal this product
                # is sold on, and that default *inverted* it while every counter
                # still moved and every log still read clean.
                #
                # `enum_ref` absorbs the three ways a model restates a member of
                # a list it was shown (decoration, casing, separator). What
                # survives it is genuinely outside the vocabulary, and the
                # choice between the two honest options is made here, in favour
                # of dropping: a reaction whose *type* is unknown cannot be
                # scored, and emitting it with an out-of-vocabulary
                # `metadata.reaction` would carry the unknown into every
                # downstream aggregate instead of stopping at this log line.
                verb = enum_ref(rtype, _FB_REACTION_VERBS)
                if verb is None:
                    logger.warning(
                        "reaction_verb_unrecognised",
                        platform=self.platform_id,
                        verb=rtype,
                        detail="dropped rather than defaulted to LIKE; this "
                               "agent's action is unmeasured this round",
                    )
                    return None
                reaction = _FB_REACTION_MAP[verb]
                await self.react(agent["username"], pid, reaction)
                self.record_action(
                    self.agent_key(agent), round_number, f"Reacted {reaction.value} to {pid}"
                )
                return SimulationEvent(
                    event_type="react", agent_id=agent.get("agent_id"), agent_username=agent["username"],
                    platform=self.platform_id, round_number=round_number,
                    variant=variant, target_id=pid,
                    metadata={"reaction": reaction.value},
                    timestamp=now,
                )

        if line.upper().startswith("SHARE"):
            # The id only — not the rest of the line. See action_ref: a model
            # that volunteers a reason ("UPVOTE [a1b2c3] - solid") used to make
            # the whole tail the id, and post_ref cannot repair that.
            pid = self.action_ref(line)
            if pid:
                await self.react(agent["username"], pid, ReactionType.SHARE)
                self.record_action(self.agent_key(agent), round_number, f"Shared post {pid}")
                return SimulationEvent(
                    event_type="react", agent_id=agent.get("agent_id"), agent_username=agent["username"],
                    platform=self.platform_id, round_number=round_number,
                    variant=variant, target_id=pid,
                    metadata={"reaction": "share"},
                    timestamp=now,
                )

        return None
