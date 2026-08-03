from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class ReactionType(StrEnum):
    LIKE = "like"
    LOVE = "love"
    HAHA = "haha"
    WOW = "wow"
    SAD = "sad"
    ANGRY = "angry"
    DISLIKE = "dislike"
    REPOST = "repost"
    SHARE = "share"
    UPVOTE = "upvote"
    DOWNVOTE = "downvote"
    AWARD = "award"


class Post(BaseModel):
    id: str
    platform: str
    author_username: str
    content: str
    created_at: datetime
    metadata: dict = {}


class Comment(BaseModel):
    id: str
    post_id: str
    platform: str
    author_username: str
    content: str
    parent_comment_id: str | None = None
    created_at: datetime


class SimulationEvent(BaseModel):
    event_type: str  # post | comment | react | dm
    agent_username: str
    platform: str
    round_number: int
    variant: str
    content: str | None = None
    target_id: str | None = None
    metadata: dict = {}
    timestamp: datetime


class BasePlatformAdapter(ABC):
    platform_id: str = ""
    platform_name: str = ""
    supports_reactions: bool = True
    supports_dms: bool = False
    max_post_length: int = 1000
    max_comment_length: int = 500

    # Agent memory: tracks each agent's actions across rounds
    _agent_history: dict[str, list[str]]

    # What the simulation is about. Empty until set_topic() is called.
    _topic: str = ""

    def _init_history(self) -> None:
        self._agent_history = {}

    def set_topic(self, config: dict) -> None:
        """Capture the simulation's subject from the run config."""
        self._topic = (config or {}).get("prediction_goal", "") or ""

    def topic_block(self, feed_is_empty: bool = False) -> str:
        """The subject line every action prompt must carry.

        Until this existed, no adapter told its agents what the simulation was
        about: `prediction_goal` was stored in `self._config` by all twelve and
        read by none. The topic reached agents only through the persona bio,
        which is generated from it — so the simulation depended on the bio
        generator succeeding, and produced silent agents when it did not.

        The empty-feed nudge is the other half. On round one nobody has posted,
        and "observe before engaging" is what a careful person actually does —
        so every agent picks NOTHING, the feed stays empty, and the run
        deadlocks at zero events for however many rounds it was given.
        """
        if not self._topic:
            return ""
        block = f"The conversation is about: {self._topic.strip()}\n\n"
        if feed_is_empty:
            block += (
                "The feed is empty — you are among the first to react. Do not "
                "wait for someone else to start; POST your own reaction to the "
                "subject above.\n\n"
            )
        return block

    def record_action(self, username: str, round_num: int, summary: str) -> None:
        """Record an agent's action for memory across rounds."""
        self._agent_history.setdefault(username, []).append(f"[R{round_num}] {summary}")

    def get_agent_memory(self, username: str, max_items: int = 10) -> str:
        """Get formatted history of an agent's previous actions."""
        history = self._agent_history.get(username, [])
        if not history:
            return ""
        recent = history[-max_items:]
        return "Your previous actions:\n" + "\n".join(recent) + "\n\n"

    @abstractmethod
    async def initialize(self, config: dict, agents: list) -> None:
        """Set up platform state, assign agents."""

    @abstractmethod
    async def run_round(self, round_number: int) -> AsyncGenerator[SimulationEvent, None]:
        """Execute one simulation round. Yields events as they occur."""

    @abstractmethod
    async def get_feed(self, agent_username: str) -> list[Post]:
        """Get the current content feed for an agent."""

    @abstractmethod
    async def post(self, agent_username: str, content: str, metadata: dict | None = None) -> Post:
        """Agent creates a new post."""

    @abstractmethod
    async def comment(self, agent_username: str, post_id: str, content: str) -> Comment:
        """Agent comments on a post."""

    @abstractmethod
    async def react(self, agent_username: str, post_id: str, reaction: ReactionType) -> None:
        """Agent reacts to a post."""

    @abstractmethod
    def get_state_snapshot(self) -> dict:
        """Return current platform state for streaming visualizer."""
