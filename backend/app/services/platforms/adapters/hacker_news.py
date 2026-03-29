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
    "You are {username} on Hacker News. Persona: {persona}\n"
    "Front page:\n{feed}\n\n"
    "Round {round}. Pick ONE action (exact format). Be technical and skeptical.\n"
    "POST: <title> | <url_or_text>\n"
    "COMMENT <post_id>: <comment text>\n"
    "UPVOTE <post_id>\n"
    "FLAG <post_id>\n"
    "NOTHING"
)


def _hn_rank(post: Post, now: datetime) -> float:
    points = post.metadata.get("points", 1)
    flags = post.metadata.get("flags", 0)
    age_hours = max((now - post.created_at).total_seconds() / 3600, 0.1)
    penalty = 1.0 + flags * 0.5
    return (points - 1) / ((age_hours + 2) ** 1.8 * penalty)


@register_adapter
class HackerNewsAdapter(BasePlatformAdapter):
    platform_id = "hacker_news"
    platform_name = "Hacker News"
    supports_reactions = True
    supports_dms = False
    max_post_length = 10000
    max_comment_length = 5000

    async def initialize(self, config: dict, agents: list) -> None:
        self._config = config
        self._agents = agents
        self._posts: list[Post] = []
        self._comments: list[Comment] = []
        self._karma: dict[str, int] = {a["username"]: 1 for a in agents}
        self._reactions: dict[str, dict[str, str]] = {}

    async def run_round(self, round_number: int) -> AsyncGenerator[SimulationEvent, None]:
        for agent in self._agents:
            action = await self._decide_action(agent, round_number)
            if action:
                yield action

    async def get_feed(self, agent_username: str) -> list[Post]:
        now = datetime.now(tz=UTC)
        scored = sorted(self._posts, key=lambda p: _hn_rank(p, now), reverse=True)
        return scored[:30]

    async def post(self, agent_username: str, content: str, metadata: dict | None = None) -> Post:
        meta = metadata or {}
        meta.setdefault("points", 1)
        meta.setdefault("flags", 0)
        parts = content.split("|", 1)
        title = parts[0].strip()
        body = parts[1].strip() if len(parts) > 1 else ""
        meta["title"] = title
        meta["url"] = body if body.startswith("http") else ""
        p = Post(
            id=uuid.uuid4().hex[:12],
            platform=self.platform_id,
            author_username=agent_username,
            content=body[: self.max_post_length] if body else title,
            created_at=datetime.now(tz=UTC),
            metadata=meta,
        )
        self._posts.append(p)
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
        self._karma[agent_username] = self._karma.get(agent_username, 0) + 1
        return c

    async def react(self, agent_username: str, post_id: str, reaction: ReactionType) -> None:
        self._reactions.setdefault(post_id, {})[agent_username] = reaction.value
        for p in self._posts:
            if p.id == post_id:
                if reaction == ReactionType.UPVOTE:
                    p.metadata["points"] = p.metadata.get("points", 0) + 1
                    self._karma[p.author_username] = self._karma.get(p.author_username, 0) + 1
                break

    def get_state_snapshot(self) -> dict:
        return {
            "platform": self.platform_id,
            "total_posts": len(self._posts),
            "total_comments": len(self._comments),
            "karma_leaders": dict(sorted(self._karma.items(), key=lambda x: x[1], reverse=True)[:10]),
        }

    # ------------------------------------------------------------------
    def _flag_post(self, post_id: str) -> None:
        for p in self._posts:
            if p.id == post_id:
                p.metadata["flags"] = p.metadata.get("flags", 0) + 1
                break

    async def _decide_action(self, agent: dict, round_number: int) -> SimulationEvent | None:
        feed = await self.get_feed(agent["username"])
        feed_text = "\n".join(
            f"[{p.id}] {p.metadata.get('title', '')} ({p.metadata.get('points', 0)} pts)"
            for p in feed[:8]
        ) or "(empty)"
        prompt = _ACTION_PROMPT.format(
            username=agent["username"],
            persona=agent.get("persona", "tech enthusiast"),
            feed=feed_text,
            round=round_number,
        )
        raw = await llm_complete([{"role": "user", "content": prompt}], max_tokens=256)
        await asyncio.sleep(0)

        now = datetime.now(tz=UTC)
        variant = agent.get("variant", "control")
        line = raw.strip().split("\n")[0].strip()

        if line.upper().startswith("POST:"):
            text = line[5:].strip()
            p = await self.post(agent["username"], text)
            return SimulationEvent(
                event_type="post", agent_username=agent["username"],
                platform=self.platform_id, round_number=round_number,
                variant=variant, content=p.metadata.get("title", ""),
                target_id=p.id, timestamp=now,
            )

        if line.upper().startswith("COMMENT"):
            match = re.match(r"COMMENT\s+(\S+):\s*(.+)", line, re.IGNORECASE)
            if match:
                pid, text = match.group(1), match.group(2)
                c = await self.comment(agent["username"], pid, text)
                return SimulationEvent(
                    event_type="comment", agent_username=agent["username"],
                    platform=self.platform_id, round_number=round_number,
                    variant=variant, content=c.content, target_id=pid, timestamp=now,
                )

        if line.upper().startswith("UPVOTE"):
            pid = line.split(maxsplit=1)[1].strip() if len(line.split()) > 1 else ""
            if pid:
                await self.react(agent["username"], pid, ReactionType.UPVOTE)
                return SimulationEvent(
                    event_type="react", agent_username=agent["username"],
                    platform=self.platform_id, round_number=round_number,
                    variant=variant, target_id=pid, metadata={"reaction": "upvote"},
                    timestamp=now,
                )

        if line.upper().startswith("FLAG"):
            pid = line.split(maxsplit=1)[1].strip() if len(line.split()) > 1 else ""
            if pid:
                self._flag_post(pid)
                return SimulationEvent(
                    event_type="react", agent_username=agent["username"],
                    platform=self.platform_id, round_number=round_number,
                    variant=variant, target_id=pid, metadata={"reaction": "flag"},
                    timestamp=now,
                )

        return None
