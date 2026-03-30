from __future__ import annotations

import asyncio
import math
import re
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.core.llm_client import llm_complete
from app.services.platforms.base_adapter import (
    BasePlatformAdapter,
    Comment,
    Post,
    ReactionType,
    SimulationEvent,
)
from app.services.platforms.registry import register_adapter


class AlgorithmType(StrEnum):
    CHRONOLOGICAL = "chronological"
    ENGAGEMENT = "engagement"
    KARMA = "karma"


class CustomPlatformConfig(BaseModel):
    name: str = "Custom Platform"
    max_post_length: int = Field(default=2000, ge=1, le=100000)
    max_comment_length: int = Field(default=1000, ge=1, le=50000)
    supports_reactions: bool = True
    supports_dms: bool = False
    algorithm: AlgorithmType = AlgorithmType.CHRONOLOGICAL
    reaction_types: list[str] = Field(default_factory=lambda: ["like"])
    feed_size: int = Field(default=20, ge=1, le=100)
    tone_guidance: str = ""


_ACTION_PROMPT = (
    "You are {username} on {platform_name}. Persona: {persona}\n"
    "{tone}"
    "Feed:\n{feed}\n\n"
    "{memory}"
    "Round {round}. Pick ONE action (exact format):\n"
    "POST: <content>\n"
    "COMMENT <post_id>: <comment text>\n"
    "REACT <post_id>\n"
    "NOTHING"
)


def _engagement_score(post: Post) -> float:
    return post.metadata.get("reactions_count", 0) * 2 + post.metadata.get("comments_count", 0) * 3


def _karma_score(post: Post, now: datetime) -> float:
    karma = post.metadata.get("karma", 1)
    age_hours = max((now - post.created_at).total_seconds() / 3600, 0.1)
    return math.log(max(karma, 1) + 1) / (age_hours + 2) ** 1.5


@register_adapter
class CustomAdapter(BasePlatformAdapter):
    platform_id = "custom"
    platform_name = "Custom Platform"
    supports_reactions = True
    supports_dms = False
    max_post_length = 2000
    max_comment_length = 1000

    async def initialize(self, config: dict, agents: list) -> None:
        self._init_history()
        self._platform_config = CustomPlatformConfig(**config.get("platform_config", {}))
        self._agents = agents
        self._posts: list[Post] = []
        self._comments: list[Comment] = []
        self._reactions: dict[str, dict[str, str]] = {}
        self._karma: dict[str, int] = {a["username"]: 1 for a in agents}

        # Apply custom config to class attributes
        self.platform_name = self._platform_config.name
        self.max_post_length = self._platform_config.max_post_length
        self.max_comment_length = self._platform_config.max_comment_length
        self.supports_reactions = self._platform_config.supports_reactions
        self.supports_dms = self._platform_config.supports_dms

    async def run_round(self, round_number: int) -> AsyncGenerator[SimulationEvent, None]:
        for agent in self._agents:
            action = await self._decide_action(agent, round_number)
            if action:
                yield action

    async def get_feed(self, agent_username: str) -> list[Post]:
        algo = self._platform_config.algorithm
        now = datetime.now(tz=UTC)
        if algo == AlgorithmType.CHRONOLOGICAL:
            scored = sorted(self._posts, key=lambda p: p.created_at, reverse=True)
        elif algo == AlgorithmType.ENGAGEMENT:
            scored = sorted(self._posts, key=_engagement_score, reverse=True)
        else:  # karma
            scored = sorted(self._posts, key=lambda p: _karma_score(p, now), reverse=True)
        return scored[: self._platform_config.feed_size]

    async def post(self, agent_username: str, content: str, metadata: dict | None = None) -> Post:
        meta = metadata or {}
        meta.setdefault("reactions_count", 0)
        meta.setdefault("comments_count", 0)
        meta.setdefault("karma", 1)
        p = Post(
            id=uuid.uuid4().hex[:12],
            platform=self.platform_id,
            author_username=agent_username,
            content=content[: self.max_post_length],
            created_at=datetime.now(tz=UTC),
            metadata=meta,
        )
        self._posts.append(p)
        if self._platform_config.algorithm == AlgorithmType.KARMA:
            self._karma[agent_username] = self._karma.get(agent_username, 0) + 1
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
        self._reactions.setdefault(post_id, {})[agent_username] = reaction.value
        for p in self._posts:
            if p.id == post_id:
                p.metadata["reactions_count"] = p.metadata.get("reactions_count", 0) + 1
                if self._platform_config.algorithm == AlgorithmType.KARMA:
                    p.metadata["karma"] = p.metadata.get("karma", 0) + 1
                    self._karma[p.author_username] = self._karma.get(p.author_username, 0) + 1
                break

    def get_state_snapshot(self) -> dict:
        snapshot: dict = {
            "platform": self.platform_id,
            "platform_name": self.platform_name,
            "algorithm": self._platform_config.algorithm.value,
            "total_posts": len(self._posts),
            "total_comments": len(self._comments),
        }
        if self._platform_config.algorithm == AlgorithmType.KARMA:
            snapshot["karma_leaders"] = dict(
                sorted(self._karma.items(), key=lambda x: x[1], reverse=True)[:10]
            )
        return snapshot

    # ------------------------------------------------------------------
    async def _decide_action(self, agent: dict, round_number: int) -> SimulationEvent | None:
        feed = await self.get_feed(agent["username"])
        feed_text = "\n".join(
            f"[{p.id}] {p.author_username}: {p.content[:100]}"
            for p in feed[:8]
        ) or "(empty)"
        tone = ""
        if self._platform_config.tone_guidance:
            tone = f"Tone: {self._platform_config.tone_guidance}\n"
        prompt = _ACTION_PROMPT.format(
            username=agent["username"],
            platform_name=self.platform_name,
            persona=agent.get("persona", "user"),
            tone=tone,
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
                variant=variant, content=p.content, target_id=p.id, timestamp=now,
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
                    variant=variant, content=c.content, target_id=pid, timestamp=now,
                )

        if line.upper().startswith("REACT"):
            pid = line.split(maxsplit=1)[1].strip() if len(line.split()) > 1 else ""
            if pid:
                await self.react(agent["username"], pid, ReactionType.LIKE)
                self.record_action(agent["username"], round_number, f"Reacted on {pid}")
                return SimulationEvent(
                    event_type="react", agent_username=agent["username"],
                    platform=self.platform_id, round_number=round_number,
                    variant=variant, target_id=pid,
                    metadata={"reaction": "like"}, timestamp=now,
                )

        return None
