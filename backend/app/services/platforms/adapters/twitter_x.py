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
    "You are {username} on Twitter/X. Persona: {persona}\n"
    "Current feed (recent tweets):\n{feed}\n\n"
    "{memory}"
    "Round {round}. Pick ONE action and reply in the EXACT format:\n"
    "POST: <tweet text>\n"
    "REPLY <post_id>: <reply text>\n"
    "LIKE <post_id>\n"
    "REPOST <post_id>\n"
    "NOTHING\n"
    "Keep tweets under 280 chars. Use hashtags naturally."
)


def _extract_hashtags(text: str) -> list[str]:
    return re.findall(r"#(\w+)", text)


def _engagement_score(post_meta: dict) -> float:
    likes = post_meta.get("likes", 0)
    reposts = post_meta.get("reposts", 0)
    return likes * 2 + reposts * 5


@register_adapter
class TwitterXAdapter(BasePlatformAdapter):
    platform_id = "twitter_x"
    platform_name = "Twitter / X"
    supports_reactions = True
    supports_dms = False
    max_post_length = 280
    max_comment_length = 280

    async def initialize(self, config: dict, agents: list) -> None:
        self._init_history()
        self._config = config
        self._agents = agents
        self._posts: list[Post] = []
        self._comments: list[Comment] = []
        self._reactions: dict[str, dict[str, ReactionType]] = {}
        self._trending: dict[str, int] = {}

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
        meta.setdefault("reposts", 0)
        meta["hashtags"] = _extract_hashtags(content)
        for tag in meta["hashtags"]:
            self._trending[tag] = self._trending.get(tag, 0) + 1
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
        return c

    async def react(self, agent_username: str, post_id: str, reaction: ReactionType) -> None:
        self._reactions.setdefault(post_id, {})[agent_username] = reaction
        for p in self._posts:
            if p.id == post_id:
                if reaction == ReactionType.LIKE:
                    p.metadata["likes"] = p.metadata.get("likes", 0) + 1
                elif reaction == ReactionType.REPOST:
                    p.metadata["reposts"] = p.metadata.get("reposts", 0) + 1
                break

    def get_state_snapshot(self) -> dict:
        top_trending = sorted(self._trending.items(), key=lambda x: x[1], reverse=True)[:10]
        return {
            "platform": self.platform_id,
            "total_posts": len(self._posts),
            "total_comments": len(self._comments),
            "trending": dict(top_trending),
        }

    # ------------------------------------------------------------------
    async def _decide_action(self, agent: dict, round_number: int) -> SimulationEvent | None:
        feed = await self.get_feed(agent["username"])
        feed_text = "\n".join(
            f"[{p.id}] @{p.author_username}: {p.content}" for p in feed[:8]
        ) or "(empty)"
        prompt = _ACTION_PROMPT.format(
            username=agent["username"],
            persona=agent.get("persona", "average user"),
            feed=feed_text,
            memory=self.get_agent_memory(agent["username"]),
            round=round_number,
        )
        raw = await llm_complete([{"role": "user", "content": prompt}], max_tokens=160)
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
                metadata={"hashtags": _extract_hashtags(text)}, timestamp=now,
            )

        if line.upper().startswith("REPLY"):
            match = re.match(r"REPLY\s+(\S+):\s*(.+)", line, re.IGNORECASE)
            if match:
                pid, text = match.group(1), match.group(2)
                c = await self.comment(agent["username"], pid, text)
                self.record_action(agent["username"], round_number, f"Replied to {pid}: {text[:80]}")
                return SimulationEvent(
                    event_type="comment", agent_username=agent["username"],
                    platform=self.platform_id, round_number=round_number,
                    variant=variant, content=c.content, target_id=pid,
                    timestamp=now,
                )

        if line.upper().startswith("LIKE"):
            pid = line.split(maxsplit=1)[1].strip() if len(line.split()) > 1 else ""
            if pid:
                await self.react(agent["username"], pid, ReactionType.LIKE)
                self.record_action(agent["username"], round_number, f"Liked post {pid}")
                return SimulationEvent(
                    event_type="react", agent_username=agent["username"],
                    platform=self.platform_id, round_number=round_number,
                    variant=variant, target_id=pid, metadata={"reaction": "like"},
                    timestamp=now,
                )

        if line.upper().startswith("REPOST"):
            pid = line.split(maxsplit=1)[1].strip() if len(line.split()) > 1 else ""
            if pid:
                await self.react(agent["username"], pid, ReactionType.REPOST)
                self.record_action(agent["username"], round_number, f"Reposted {pid}")
                return SimulationEvent(
                    event_type="react", agent_username=agent["username"],
                    platform=self.platform_id, round_number=round_number,
                    variant=variant, target_id=pid, metadata={"reaction": "repost"},
                    timestamp=now,
                )

        return None
