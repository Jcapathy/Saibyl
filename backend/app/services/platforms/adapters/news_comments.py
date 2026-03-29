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

_MAX_NESTING = 3

_ACTION_PROMPT = (
    "You are commenter '{username}' on a news site. Persona: {persona}\n"
    "Article: {article_title}\n"
    "Comments:\n{feed}\n\n"
    "Round {round}. Pick ONE action (exact format). Be concise, opinionated.\n"
    "COMMENT: <your comment on the article>\n"
    "REPLY <comment_id>: <reply text>\n"
    "UPVOTE <comment_id>\n"
    "NOTHING"
)


@register_adapter
class NewsCommentsAdapter(BasePlatformAdapter):
    platform_id = "news_comments"
    platform_name = "News Comments"
    supports_reactions = True
    supports_dms = False
    max_post_length = 2000
    max_comment_length = 2000

    async def initialize(self, config: dict, agents: list) -> None:
        self._config = config
        self._agents = agents
        self._posts: list[Post] = []
        self._comments: list[Comment] = []
        self._reactions: dict[str, dict[str, ReactionType]] = {}
        self._flagged: set[str] = set()
        # seed an article post
        article_title = config.get("article_title", "Breaking News Story")
        article_body = config.get("article_body", "A significant event has occurred...")
        article = Post(
            id=uuid.uuid4().hex[:12],
            platform=self.platform_id,
            author_username="__editorial__",
            content=article_body,
            created_at=datetime.now(tz=UTC),
            metadata={"title": article_title, "type": "article", "upvotes": 0},
        )
        self._posts.append(article)

    async def run_round(self, round_number: int) -> AsyncGenerator[SimulationEvent, None]:
        for agent in self._agents:
            action = await self._decide_action(agent, round_number)
            if action:
                yield action

    async def get_feed(self, agent_username: str) -> list[Post]:
        return list(self._posts)

    async def post(self, agent_username: str, content: str, metadata: dict | None = None) -> Post:
        meta = metadata or {}
        meta.setdefault("upvotes", 0)
        meta.setdefault("type", "article")
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
        # Determine nesting depth
        parent_comment_id = None
        # If post_id refers to a comment, nest under it (up to limit)
        depth = self._get_comment_depth(post_id)
        if depth < _MAX_NESTING:
            # Check if post_id is actually a comment id
            for c in self._comments:
                if c.id == post_id:
                    parent_comment_id = post_id
                    post_id = c.post_id
                    break

        display_name = agent_username
        # simulate anonymous-ish display
        if not self._config.get("show_usernames", False):
            display_name = f"Commenter_{hash(agent_username) % 10000:04d}"

        # Use display_name as author for anonymous-ish mode
        c = Comment(
            id=uuid.uuid4().hex[:12],
            post_id=post_id,
            platform=self.platform_id,
            author_username=display_name,
            content=content[: self.max_comment_length],
            parent_comment_id=parent_comment_id,
            created_at=datetime.now(tz=UTC),
        )
        self._comments.append(c)
        return c

    async def react(self, agent_username: str, post_id: str, reaction: ReactionType) -> None:
        self._reactions.setdefault(post_id, {})[agent_username] = reaction
        for p in self._posts:
            if p.id == post_id:
                p.metadata["upvotes"] = p.metadata.get("upvotes", 0) + 1
                break

    def get_state_snapshot(self) -> dict:
        return {
            "platform": self.platform_id,
            "articles": len([p for p in self._posts if p.metadata.get("type") == "article"]),
            "total_comments": len(self._comments),
            "flagged_comments": len(self._flagged),
        }

    # ------------------------------------------------------------------
    def _get_comment_depth(self, comment_id: str) -> int:
        depth = 0
        current = comment_id
        for _ in range(_MAX_NESTING + 1):
            found = False
            for c in self._comments:
                if c.id == current and c.parent_comment_id:
                    depth += 1
                    current = c.parent_comment_id
                    found = True
                    break
            if not found:
                break
        return depth

    async def _decide_action(self, agent: dict, round_number: int) -> SimulationEvent | None:
        article = self._posts[0] if self._posts else None
        if not article:
            return None
        article_title = article.metadata.get("title", "News Article")

        comments_text = "\n".join(
            f"[{c.id}] {c.author_username}: {c.content[:100]}"
            for c in self._comments[-10:]
        ) or "(no comments yet)"

        prompt = _ACTION_PROMPT.format(
            username=agent["username"],
            persona=agent.get("persona", "news reader"),
            article_title=article_title,
            feed=comments_text,
            round=round_number,
        )
        raw = await llm_complete([{"role": "user", "content": prompt}], max_tokens=200)
        await asyncio.sleep(0)

        now = datetime.now(tz=UTC)
        variant = agent.get("variant", "control")
        line = raw.strip().split("\n")[0].strip()

        if line.upper().startswith("COMMENT:"):
            text = line[8:].strip()
            c = await self.comment(agent["username"], article.id, text)
            return SimulationEvent(
                event_type="comment", agent_username=agent["username"],
                platform=self.platform_id, round_number=round_number,
                variant=variant, content=c.content, target_id=article.id,
                timestamp=now,
            )

        if line.upper().startswith("REPLY"):
            match = re.match(r"REPLY\s+(\S+):\s*(.+)", line, re.IGNORECASE)
            if match:
                cid, text = match.group(1), match.group(2)
                c = await self.comment(agent["username"], cid, text)
                return SimulationEvent(
                    event_type="comment", agent_username=agent["username"],
                    platform=self.platform_id, round_number=round_number,
                    variant=variant, content=c.content, target_id=cid,
                    timestamp=now,
                )

        if line.upper().startswith("UPVOTE"):
            cid = line.split(maxsplit=1)[1].strip() if len(line.split()) > 1 else ""
            if cid:
                await self.react(agent["username"], cid, ReactionType.UPVOTE)
                return SimulationEvent(
                    event_type="react", agent_username=agent["username"],
                    platform=self.platform_id, round_number=round_number,
                    variant=variant, target_id=cid,
                    metadata={"reaction": "upvote"}, timestamp=now,
                )

        return None
