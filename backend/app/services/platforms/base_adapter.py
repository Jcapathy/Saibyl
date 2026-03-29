from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class ReactionType(StrEnum):
    LIKE = "like"
    LOVE = "love"
    ANGRY = "angry"
    REPOST = "repost"
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
