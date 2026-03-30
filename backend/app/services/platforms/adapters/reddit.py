from __future__ import annotations

import asyncio
import math
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

_MAX_COMMENT_DEPTH = 5

_ACTION_PROMPT = (
    "You are u/{username} on Reddit. Persona: {persona}\n"
    "Subreddit: r/{subreddit}. Hot posts:\n{feed}\n\n"
    "{memory}"
    "Round {round}. Pick ONE action (exact format):\n"
    "POST: <title> | <body>\n"
    "COMMENT <post_id>: <comment text>\n"
    "UPVOTE <post_id>\n"
    "DOWNVOTE <post_id>\n"
    "NOTHING"
)


def _hot_score(post: Post, now: datetime) -> float:
    ups = post.metadata.get("upvotes", 1)
    downs = post.metadata.get("downvotes", 0)
    score = ups - downs
    sign = 1 if score > 0 else -1 if score < 0 else 0
    age_hours = max((now - post.created_at).total_seconds() / 3600, 0.1)
    return sign * math.log(max(abs(score), 1)) / (age_hours + 2) ** 1.8


@register_adapter
class RedditAdapter(BasePlatformAdapter):
    platform_id = "reddit"
    platform_name = "Reddit"
    supports_reactions = True
    supports_dms = False
    max_post_length = 40000
    max_comment_length = 10000

    async def initialize(self, config: dict, agents: list) -> None:
        self._init_history()
        self._config = config
        self._agents = agents
        self._subreddit = config.get("subreddit", "general")
        self._posts: list[Post] = []
        self._comments: list[Comment] = []
        self._reactions: dict[str, dict[str, ReactionType]] = {}

    async def run_round(self, round_number: int) -> AsyncGenerator[SimulationEvent, None]:
        for agent in self._agents:
            action = await self._decide_action(agent, round_number)
            if action:
                yield action

    async def get_feed(self, agent_username: str) -> list[Post]:
        now = datetime.now(tz=UTC)
        scored = sorted(self._posts, key=lambda p: _hot_score(p, now), reverse=True)
        return scored[:25]

    async def post(self, agent_username: str, content: str, metadata: dict | None = None) -> Post:
        meta = metadata or {}
        meta.setdefault("upvotes", 1)
        meta.setdefault("downvotes", 0)
        meta.setdefault("subreddit", self._subreddit)
        parts = content.split("|", 1)
        title = parts[0].strip()
        body = parts[1].strip() if len(parts) > 1 else ""
        meta["title"] = title
        p = Post(
            id=uuid.uuid4().hex[:12],
            platform=self.platform_id,
            author_username=agent_username,
            content=body[: self.max_post_length],
            created_at=datetime.now(tz=UTC),
            metadata=meta,
        )
        self._posts.append(p)
        return p

    async def comment(self, agent_username: str, post_id: str, content: str) -> Comment:
        depth = 0
        parent_id = None
        # check nesting depth
        for c in self._comments:
            if c.post_id == post_id and c.parent_comment_id:
                depth += 1
        if depth >= _MAX_COMMENT_DEPTH:
            parent_id = None  # flatten if too deep
        c = Comment(
            id=uuid.uuid4().hex[:12],
            post_id=post_id,
            platform=self.platform_id,
            author_username=agent_username,
            content=content[: self.max_comment_length],
            parent_comment_id=parent_id,
            created_at=datetime.now(tz=UTC),
        )
        self._comments.append(c)
        return c

    async def react(self, agent_username: str, post_id: str, reaction: ReactionType) -> None:
        self._reactions.setdefault(post_id, {})[agent_username] = reaction
        for p in self._posts:
            if p.id == post_id:
                if reaction == ReactionType.UPVOTE:
                    p.metadata["upvotes"] = p.metadata.get("upvotes", 0) + 1
                elif reaction == ReactionType.DOWNVOTE:
                    p.metadata["downvotes"] = p.metadata.get("downvotes", 0) + 1
                break

    def get_state_snapshot(self) -> dict:
        return {
            "platform": self.platform_id,
            "subreddit": self._subreddit,
            "total_posts": len(self._posts),
            "total_comments": len(self._comments),
        }

    # ------------------------------------------------------------------
    async def _decide_action(self, agent: dict, round_number: int) -> SimulationEvent | None:
        feed = await self.get_feed(agent["username"])
        feed_text = "\n".join(
            f"[{p.id}] u/{p.author_username}: {p.metadata.get('title', '')} ({p.metadata.get('upvotes', 0)} pts)"
            for p in feed[:8]
        ) or "(empty)"
        prompt = _ACTION_PROMPT.format(
            username=agent["username"],
            persona=agent.get("persona", "average redditor"),
            subreddit=self._subreddit,
            feed=feed_text,
            memory=self.get_agent_memory(agent["username"]),
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
            self.record_action(agent["username"], round_number, f"Posted: {text[:80]}")
            return SimulationEvent(
                event_type="post", agent_username=agent["username"],
                platform=self.platform_id, round_number=round_number,
                variant=variant, content=p.content, target_id=p.id,
                metadata={"title": p.metadata.get("title", "")}, timestamp=now,
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

        if line.upper().startswith("UPVOTE"):
            pid = line.split(maxsplit=1)[1].strip() if len(line.split()) > 1 else ""
            if pid:
                await self.react(agent["username"], pid, ReactionType.UPVOTE)
                self.record_action(agent["username"], round_number, f"Upvoted post {pid}")
                return SimulationEvent(
                    event_type="react", agent_username=agent["username"],
                    platform=self.platform_id, round_number=round_number,
                    variant=variant, target_id=pid, metadata={"reaction": "upvote"},
                    timestamp=now,
                )

        if line.upper().startswith("DOWNVOTE"):
            pid = line.split(maxsplit=1)[1].strip() if len(line.split()) > 1 else ""
            if pid:
                await self.react(agent["username"], pid, ReactionType.DOWNVOTE)
                self.record_action(agent["username"], round_number, f"Downvoted post {pid}")
                return SimulationEvent(
                    event_type="react", agent_username=agent["username"],
                    platform=self.platform_id, round_number=round_number,
                    variant=variant, target_id=pid, metadata={"reaction": "downvote"},
                    timestamp=now,
                )

        return None
