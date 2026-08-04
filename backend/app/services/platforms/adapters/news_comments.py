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

logger = structlog.get_logger()

_MAX_NESTING = 3

_ACTION_PROMPT = (
    "You are commenter '{username}' on a news site. Persona: {persona}\n"
    "Article: {article_title}\n"
    "Comments:\n{feed}\n\n"
    "{topic}"
    "{memory}"
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
        self._init_history()
        self._config = config
        self.set_topic(config)
        self._agents = agents
        self._posts: list[Post] = []
        self._comments: list[Comment] = []
        self._reactions: dict[str, dict[str, ReactionType]] = {}
        # comment id -> upvotes. Comments are what the feed shows and what
        # agents are asked to upvote, and `Comment` has no metadata dict to hold
        # a counter, so the count lives here — per instance, like every other
        # piece of arena state.
        self._comment_upvotes: dict[str, int] = {}
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
        # V1 defect: the model echoes the id in the brackets the feed showed
        # it, so an un-normalised post_id never matches p.id. See post_ref.
        post_id = self.post_ref(post_id)
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
        """An upvote, on a comment or on the article.

        **Comments first, because that is what the feed shows.** This adapter
        renders `[{c.id}] author: text` for comments and asks for
        `UPVOTE <comment_id>`, but resolved the reference against `self._posts`,
        which holds only the seeded article — whose id is never displayed. Every
        id an agent could type therefore matched nothing, so *100% of upvotes on
        this platform were discarded*, silently, on every run.

        The article stays reachable because `COMMENT:` targets `article.id`
        directly, so it is a real id even though no agent is ever shown it.
        """
        # V1 defect: the model echoes the id in the brackets the feed showed
        # it, so an un-normalised post_id never matches p.id. See post_ref.
        post_id = self.post_ref(post_id)
        self._reactions.setdefault(post_id, {})[agent_username] = reaction
        for c in self._comments:
            if c.id == post_id:
                self._comment_upvotes[post_id] = self._comment_upvotes.get(post_id, 0) + 1
                return
        for p in self._posts:
            if p.id == post_id:
                p.metadata["upvotes"] = p.metadata.get("upvotes", 0) + 1
                return
        # A lookup miss and a legitimate absence must not be the same value.
        logger.warning(
            "reaction_target_not_found",
            platform=self.platform_id,
            target_id=post_id,
            detail="an agent upvoted an id matching no comment or article in "
                   "this arena",
        )

    def get_state_snapshot(self) -> dict:
        return {
            "platform": self.platform_id,
            "articles": len([p for p in self._posts if p.metadata.get("type") == "article"]),
            "total_comments": len(self._comments),
            "comment_upvotes": sum(self._comment_upvotes.values()),
            "flagged_comments": len(self._flagged),
        }

    # ------------------------------------------------------------------
    def _get_comment_depth(self, comment_id: str) -> int:
        depth = 0
        # Normalised on the way in even though today's only caller normalises
        # first. `_flag_post` on Hacker News was inert for the whole of V1 for
        # exactly this reason: a private helper that compares a model-supplied
        # id raw is correct only for as long as every caller remembers.
        current = self.post_ref(comment_id)
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
            f"[{c.id}] {c.author_username}: {c.content[:100]} "
            f"({self._comment_upvotes.get(c.id, 0)} upvotes)"
            for c in self._comments[-10:]
        ) or "(no comments yet)"

        prompt = _ACTION_PROMPT.format(
            username=agent["username"],
            persona=agent.get("persona", "news reader"),
            article_title=article_title,
            feed=comments_text,
            topic=self.topic_block(feed_is_empty=not self._comments),
            memory=self.get_agent_memory(self.agent_key(agent)),
            round=round_number,
        )
        raw = await llm_fast([{"role": "user", "content": prompt}], max_tokens=200)
        await asyncio.sleep(0)

        now = datetime.now(tz=UTC)
        variant = agent.get("variant", "control")
        line = raw.strip().split("\n")[0].strip()

        if line.upper().startswith("COMMENT:"):
            text = line[8:].strip()
            c = await self.comment(agent["username"], article.id, text)
            self.record_action(self.agent_key(agent), round_number, f"Commented: {text[:80]}")
            return SimulationEvent(
                event_type="comment", agent_id=agent.get("agent_id"), agent_username=agent["username"],
                platform=self.platform_id, round_number=round_number,
                variant=variant, content=c.content, target_id=article.id,
                timestamp=now,
            )

        if line.upper().startswith("REPLY"):
            match = re.match(r"REPLY\s+(\S+):\s*(.+)", line, re.IGNORECASE)
            if match:
                cid, text = self.post_ref(match.group(1)), match.group(2)
                c = await self.comment(agent["username"], cid, text)
                self.record_action(self.agent_key(agent), round_number, f"Replied to {cid}: {text[:80]}")
                return SimulationEvent(
                    event_type="comment", agent_id=agent.get("agent_id"), agent_username=agent["username"],
                    platform=self.platform_id, round_number=round_number,
                    variant=variant, content=c.content, target_id=cid,
                    timestamp=now,
                )

        if line.upper().startswith("UPVOTE"):
            # The id only — not the rest of the line. See action_ref: a model
            # that volunteers a reason ("UPVOTE [a1b2c3] - solid") used to make
            # the whole tail the id, and post_ref cannot repair that.
            cid = self.action_ref(line)
            if cid:
                await self.react(agent["username"], cid, ReactionType.UPVOTE)
                self.record_action(self.agent_key(agent), round_number, f"Upvoted comment {cid}")
                return SimulationEvent(
                    event_type="react", agent_id=agent.get("agent_id"), agent_username=agent["username"],
                    platform=self.platform_id, round_number=round_number,
                    variant=variant, target_id=cid,
                    metadata={"reaction": "upvote"}, timestamp=now,
                )

        return None
