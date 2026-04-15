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
    "You are @{username} on TikTok. Persona: {persona}\n"
    "Feed (recent posts):\n{feed}\n\n"
    "{memory}"
    "Round {round}. Pick ONE action (exact format). Content is video-first.\n"
    "POST: <video caption> | <description>\n"
    "DUET <post_id>: <caption>\n"
    "COMMENT <post_id>: <comment text>\n"
    "LIKE <post_id>\n"
    "NOTHING"
)


def _explore_score(post: Post) -> float:
    likes = post.metadata.get("likes", 0)
    comments = post.metadata.get("comments_count", 0)
    shares = post.metadata.get("shares", 0)
    return likes + comments * 3 + shares * 5


@register_adapter
class TikTokAdapter(BasePlatformAdapter):
    platform_id = "tiktok"
    platform_name = "TikTok"
    supports_reactions = True
    supports_dms = False
    max_post_length = 2200
    max_comment_length = 500

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
        combined = sorted(self._posts, key=lambda p: _explore_score(p), reverse=True)
        return combined[:20]

    async def post(self, agent_username: str, content: str, metadata: dict | None = None) -> Post:
        meta = metadata or {}
        meta.setdefault("likes", 0)
        meta.setdefault("comments_count", 0)
        meta.setdefault("shares", 0)
        parts = content.split("|", 1)
        caption = parts[0].strip()
        description = parts[1].strip() if len(parts) > 1 else ""
        meta["video_description"] = description
        p = Post(
            id=uuid.uuid4().hex[:12],
            platform=self.platform_id,
            author_username=agent_username,
            content=caption[: self.max_post_length],
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
                p.metadata["likes"] = p.metadata.get("likes", 0) + 1
                break

    def get_state_snapshot(self) -> dict:
        return {
            "platform": self.platform_id,
            "total_posts": len(self._posts),
            "total_comments": len(self._comments),
        }

    # ------------------------------------------------------------------
    async def _decide_action(self, agent: dict, round_number: int) -> SimulationEvent | None:
        feed = await self.get_feed(agent["username"])
        feed_text = "\n".join(
            f"[{p.id}] @{p.author_username}: {p.content[:80]} ({p.metadata.get('likes', 0)} likes, {p.metadata.get('shares', 0)} shares)"
            for p in feed[:6]
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
                metadata={"video_description": p.metadata.get("video_description", "")},
                timestamp=now,
            )

        if line.upper().startswith("DUET"):
            match = re.match(r"DUET\s+(\S+):\s*(.+)", line, re.IGNORECASE)
            if match:
                pid, caption = match.group(1), match.group(2)
                p = await self.post(agent["username"], caption, metadata={"type": "duet", "duet_of": pid})
                self.record_action(agent["username"], round_number, f"Duet of {pid}: {caption[:80]}")
                return SimulationEvent(
                    event_type="post", agent_username=agent["username"],
                    platform=self.platform_id, round_number=round_number,
                    variant=variant, content=p.content, target_id=p.id,
                    metadata={"type": "duet", "duet_of": pid}, timestamp=now,
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

        return None
