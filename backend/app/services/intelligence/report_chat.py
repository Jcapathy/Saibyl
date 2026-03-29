# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# chat_with_report(report_id, message, conversation_history,
#                  max_context_tools=3) -> ChatResponse
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import json
from uuid import UUID

import redis
import structlog
from pydantic import BaseModel

from app.core.config import settings
from app.core.database import get_supabase_admin
from app.core.llm_client import llm_complete
from app.services.intelligence.react_tools import (
    insight_forge,
    quick_search,
    simulation_analytics,
)

logger = structlog.get_logger()

CHAT_TTL_SECONDS = 86400  # 24 hours

AVAILABLE_TOOLS = {
    "insight_forge": insight_forge,
    "quick_search": quick_search,
    "simulation_analytics": simulation_analytics,
}

REACT_SYSTEM_PROMPT = """\
You are an AI assistant helping users understand a simulation report.
You have access to the following tools to gather additional context:
- insight_forge: Generate deeper insights from simulation data.
- quick_search: Search through simulation events and agent data.
- simulation_analytics: Compute analytics metrics for a simulation.

When answering, decide whether you need to call a tool first.
If you do, respond ONLY with a JSON object: {"tool": "<tool_name>", "args": {...}}
If you have enough context, respond with your final answer as plain text (no JSON).
"""


class ChatResponse(BaseModel):
    answer: str
    tools_used: list[str]
    sources: list[str]


def _get_redis() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def _cache_key(report_id: UUID) -> str:
    return f"report:{report_id}:chat"


def _load_history(r: redis.Redis, key: str) -> list[dict[str, str]]:
    raw = r.get(key)
    if raw:
        return json.loads(raw)
    return []


def _save_history(
    r: redis.Redis,
    key: str,
    history: list[dict[str, str]],
) -> None:
    r.set(key, json.dumps(history), ex=CHAT_TTL_SECONDS)


async def chat_with_report(
    report_id: UUID,
    message: str,
    conversation_history: list[dict[str, str]] | None = None,
    max_context_tools: int = 3,
) -> ChatResponse:
    """Chat with a report using a mini ReACT loop for tool-augmented answers."""
    admin = get_supabase_admin()

    # Load report context
    report = (
        admin.table("reports")
        .select("markdown_content, simulation_id")
        .eq("id", str(report_id))
        .single()
        .execute()
    )
    report_data = report.data
    markdown_content = report_data["markdown_content"]
    simulation_id = report_data["simulation_id"]

    # Restore or initialise conversation history
    r = _get_redis()
    cache_key = _cache_key(report_id)
    history = conversation_history or _load_history(r, cache_key)

    # Build initial messages
    messages: list[dict[str, str]] = [
        {"role": "system", "content": REACT_SYSTEM_PROMPT},
        {
            "role": "system",
            "content": f"Report context:\n{markdown_content[:8000]}",
        },
        *history,
        {"role": "user", "content": message},
    ]

    tools_used: list[str] = []
    sources: list[str] = []

    # Mini ReACT loop
    for _step in range(max_context_tools):
        response_text = await llm_complete(messages=messages, temperature=0.3)

        # Check if the model wants to call a tool
        try:
            parsed = json.loads(response_text)
            tool_name = parsed.get("tool")
            tool_args = parsed.get("args", {})
        except (json.JSONDecodeError, AttributeError):
            # Not a tool call — treat as final answer
            break

        if tool_name not in AVAILABLE_TOOLS:
            break

        logger.info(
            "react_tool_call",
            report_id=str(report_id),
            tool=tool_name,
            step=_step,
        )

        tool_fn = AVAILABLE_TOOLS[tool_name]
        tool_result = await tool_fn(
            simulation_id=UUID(simulation_id),
            **tool_args,
        )
        tools_used.append(tool_name)
        sources.append(f"{tool_name}: {json.dumps(tool_args)}")

        # Feed tool result back into the conversation
        messages.append({"role": "assistant", "content": response_text})
        messages.append({
            "role": "user",
            "content": f"Tool result from {tool_name}:\n{json.dumps(tool_result)}",
        })
    else:
        # Exhausted tool budget — generate final answer
        response_text = await llm_complete(messages=messages, temperature=0.3)

    # Persist conversation
    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": response_text})
    _save_history(r, cache_key, history)

    logger.info(
        "report_chat_complete",
        report_id=str(report_id),
        tools_used=tools_used,
    )

    return ChatResponse(
        answer=response_text,
        tools_used=tools_used,
        sources=sources,
    )
