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

_ROLES = {"member", "moderator", "admin"}

_ACTION_PROMPT = (
    "You are {username} ({role}) in a Discord server. Persona: {persona}\n"
    "Channel: #{channel}. Recent messages:\n{feed}\n\n"
    "{memory}"
    "Round {round}. Pick ONE action (exact format):\n"
    "MSG: <message text>\n"
    "REPLY <msg_id>: <reply text>\n"
    "REACT <msg_id> <emoji_name>\n"
    "DM <target_username>: <message text>\n"
    "NOTHING"
)


@register_adapter
class DiscordAdapter(BasePlatformAdapter):
    platform_id = "discord"
    platform_name = "Discord"
    supports_reactions = True
    supports_dms = True
    max_post_length = 2000
    max_comment_length = 2000

    async def initialize(self, config: dict, agents: list) -> None:
        self._init_history()
        self._config = config
        self._agents = agents
        self._channels: list[str] = config.get("channels", ["general"])
        self._active_channel = self._channels[0]
        self._posts: list[Post] = []
        self._comments: list[Comment] = []
        self._reactions: dict[str, dict[str, str]] = {}
        self._dms: list[dict] = []
        self._roles: dict[str, str] = {}
        for agent in agents:
            self._roles[agent["username"]] = agent.get("role", "member")
            if self._roles[agent["username"]] not in _ROLES:
                self._roles[agent["username"]] = "member"

    async def run_round(self, round_number: int) -> AsyncGenerator[SimulationEvent, None]:
        for agent in self._agents:
            action = await self._decide_action(agent, round_number)
            if action:
                yield action

    async def get_feed(self, agent_username: str) -> list[Post]:
        channel_msgs = [
            p for p in self._posts
            if p.metadata.get("channel") == self._active_channel
        ]
        return channel_msgs[-30:]

    async def post(self, agent_username: str, content: str, metadata: dict | None = None) -> Post:
        meta = metadata or {}
        meta.setdefault("channel", self._active_channel)
        meta["role"] = self._roles.get(agent_username, "member")
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
        self._reactions.setdefault(post_id, {})[agent_username] = reaction.value

    def get_state_snapshot(self) -> dict:
        return {
            "platform": self.platform_id,
            "channels": self._channels,
            "active_channel": self._active_channel,
            "total_messages": len(self._posts),
            "total_replies": len(self._comments),
            "total_dms": len(self._dms),
        }

    # ------------------------------------------------------------------
    def _send_dm(self, from_user: str, to_user: str, content: str) -> dict:
        dm = {
            "id": uuid.uuid4().hex[:12],
            "from": from_user,
            "to": to_user,
            "content": content[: self.max_post_length],
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }
        self._dms.append(dm)
        return dm

    async def _decide_action(self, agent: dict, round_number: int) -> SimulationEvent | None:
        feed = await self.get_feed(agent["username"])
        feed_text = "\n".join(
            f"[{p.id}] {p.author_username} ({p.metadata.get('role', 'member')}): {p.content[:100]}"
            for p in feed[-8:]
        ) or "(empty)"
        role = self._roles.get(agent["username"], "member")
        prompt = _ACTION_PROMPT.format(
            username=agent["username"],
            role=role,
            persona=agent.get("persona", "server member"),
            channel=self._active_channel,
            feed=feed_text,
            memory=self.get_agent_memory(agent["username"]),
            round=round_number,
        )
        raw = await llm_complete([{"role": "user", "content": prompt}], max_tokens=200)
        await asyncio.sleep(0)

        now = datetime.now(tz=UTC)
        variant = agent.get("variant", "control")
        line = raw.strip().split("\n")[0].strip()

        if line.upper().startswith("MSG:"):
            text = line[4:].strip()
            p = await self.post(agent["username"], text)
            self.record_action(agent["username"], round_number, f"Posted: {text[:80]}")
            return SimulationEvent(
                event_type="post", agent_username=agent["username"],
                platform=self.platform_id, round_number=round_number,
                variant=variant, content=p.content, target_id=p.id,
                metadata={"channel": self._active_channel}, timestamp=now,
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
                    variant=variant, content=c.content, target_id=pid, timestamp=now,
                )

        if line.upper().startswith("REACT"):
            match = re.match(r"REACT\s+(\S+)\s+(\S+)", line, re.IGNORECASE)
            if match:
                pid = match.group(1)
                await self.react(agent["username"], pid, ReactionType.LIKE)
                self.record_action(agent["username"], round_number, f"Reacted {match.group(2)} on {pid}")
                return SimulationEvent(
                    event_type="react", agent_username=agent["username"],
                    platform=self.platform_id, round_number=round_number,
                    variant=variant, target_id=pid,
                    metadata={"reaction": match.group(2)}, timestamp=now,
                )

        if line.upper().startswith("DM"):
            match = re.match(r"DM\s+(\S+):\s*(.+)", line, re.IGNORECASE)
            if match:
                target, text = match.group(1), match.group(2)
                dm = self._send_dm(agent["username"], target, text)
                self.record_action(agent["username"], round_number, f"DM to {target}: {text[:80]}")
                return SimulationEvent(
                    event_type="dm", agent_username=agent["username"],
                    platform=self.platform_id, round_number=round_number,
                    variant=variant, content=text, target_id=dm["id"],
                    metadata={"to": target}, timestamp=now,
                )

        return None
