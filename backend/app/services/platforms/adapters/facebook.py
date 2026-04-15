from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from app.core.llm_client import llm_complete
from app.services.platforms.base_adapter import (
    BasePlatformAdapter,
    Comment,
    Post,
    ReactionType,
    SimulationEvent,
)
from app.services.platforms.registry import register_adapter

_ACTION_PROMPT = (
    "You are {username} on Facebook. Persona: {persona}\n"
    "Current feed (recent posts):\n{feed}\n\n"
    "{memory}"
    "Round {round}. Pick ONE action and reply in the EXACT format:\n"
    "POST: <text>\n"
    "COMMENT <post_id>: <text>\n"
    "REACT <post_id> <type> (where type is LIKE/LOVE/HAHA/WOW/SAD/ANGRY)\n"
    "SHARE <post_id>\n"
    "NOTHING\n"
    "Keep posts under 63206 chars."
)

_FB_REACTION_MAP: dict[str, ReactionType] = {
    "LIKE": ReactionType.LIKE,
    "LOVE": ReactionType.LOVE,
    "HAHA": ReactionType.HAHA,
    "WOW": ReactionType.WOW,
    "SAD": ReactionType.SAD,
    "ANGRY": ReactionType.ANGRY,
}


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
            memory=self.get_agent_memory(agent["username"]),
            round=round_number,
        )
        raw = await llm_complete([{"role": "user", "content": prompt}], max_tokens=200)
        await asyncio.sleep(0)

        now = datetime.now(tz=UTC)
        variant = agent.get("variant", "control")
        line = raw.strip().split("\n")[0].strip()

        if line.upper().startswith("POST:"):
            text = line[5:].strip()
            p = await self.post(agent["username"], text)
            self.record_action(agent["username"], round_number, f"Posted: {text[:80]}")
            return SimulationEvent(
                event_type="post", agent_username=agent["username"],
                platform=self.platform_id, round_number=round_number,
                variant=variant, content=p.content, target_id=p.id,
                metadata={}, timestamp=now,
            )

        if line.upper().startswith("COMMENT"):
            match = re.match(r"COMMENT\s+(\S+):\s*(.+)", line, re.IGNORECASE)
            if match:
                pid, text = match.group(1), match.group(2)
                c = await self.comment(agent["username"], pid, text)
                self.record_action(agent["username"], round_number, f"Commented on {pid}: {text[:80]}")
                return SimulationEvent(
                    event_type="comment", agent_username=agent["username"],
                    platform=self.platform_id, round_number=round_number,
                    variant=variant, content=c.content, target_id=pid,
                    timestamp=now,
                )

        if line.upper().startswith("REACT"):
            match = re.match(r"REACT\s+(\S+)\s+(\S+)", line, re.IGNORECASE)
            if match:
                pid, rtype = match.group(1), match.group(2).upper()
                reaction = _FB_REACTION_MAP.get(rtype, ReactionType.LIKE)
                await self.react(agent["username"], pid, reaction)
                self.record_action(agent["username"], round_number, f"Reacted {rtype} to {pid}")
                return SimulationEvent(
                    event_type="react", agent_username=agent["username"],
                    platform=self.platform_id, round_number=round_number,
                    variant=variant, target_id=pid,
                    metadata={"reaction": reaction.value},
                    timestamp=now,
                )

        if line.upper().startswith("SHARE"):
            pid = line.split(maxsplit=1)[1].strip() if len(line.split()) > 1 else ""
            if pid:
                await self.react(agent["username"], pid, ReactionType.SHARE)
                self.record_action(agent["username"], round_number, f"Shared post {pid}")
                return SimulationEvent(
                    event_type="react", agent_username=agent["username"],
                    platform=self.platform_id, round_number=round_number,
                    variant=variant, target_id=pid,
                    metadata={"reaction": "share"},
                    timestamp=now,
                )

        return None
