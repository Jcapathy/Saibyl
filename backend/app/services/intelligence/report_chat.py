# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# chat_with_report(report_id, message, conversation_history,
#                  max_context_tools=3) -> ChatResponse
# ReportNotReadyError
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import json
from uuid import UUID

import redis
import structlog
from fastapi import HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.core.database import get_supabase_admin
from app.core.llm_client import llm_complete
from app.services.intelligence.react_tools import simulation_analytics

logger = structlog.get_logger()

CHAT_TTL_SECONDS = 86400  # 24 hours

AVAILABLE_TOOLS = {
    "simulation_analytics": simulation_analytics,
}

REACT_SYSTEM_PROMPT = """\
You are an AI assistant helping users understand a simulation report.
You have access to the following tool to gather additional context:
- simulation_analytics: Compute analytics metrics for a simulation.

When answering, decide whether you need to call a tool first.
If you do, respond ONLY with a JSON object: {"tool": "<tool_name>", "args": {...}}
If you have enough context, respond with your final answer as plain text (no JSON).
"""


class ChatResponse(BaseModel):
    answer: str
    tools_used: list[str]
    sources: list[str]


class ReportNotReadyError(HTTPException):
    """Asked a question of a report that has no body yet.

    `reports.markdown_content` is NULL from insert until the last section lands,
    so every question asked while a report is generating used to reach
    `markdown_content[:8000]` and 500 on a NoneType slice. Asking early is a
    normal thing for a user to do; it is not a server fault, so it is a 409.

    The report's `status` rides along because NULL content is the *same value*
    for "still generating, ask again in a minute" and "generation failed, this
    will never have a body" — opposite facts the caller cannot otherwise tell
    apart. It is an `HTTPException` subclass so it propagates through the route
    unchanged while still being catchable by name.
    """

    def __init__(self, report_id: UUID | str, status: str | None) -> None:
        if status == "failed":
            message = (
                "This report failed to generate, so there is nothing to ask "
                "questions about. Re-run the report to try again."
            )
        else:
            message = (
                "This report is still being written. Questions can be answered "
                "once it finishes — its progress is at "
                f"GET /api/reports/{report_id}/progress."
            )
        super().__init__(
            status_code=409,
            detail={
                "code": "report_not_ready",
                "report_id": str(report_id),
                "status": status,
                "message": message,
            },
        )


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
        .select("markdown_content, simulation_id, status")
        .eq("id", str(report_id))
        .execute()
    )
    if not report.data:
        raise HTTPException(status_code=404, detail="Report not found")
    report_data = report.data[0]

    # Refused before the model is called, not after: an answer written from an
    # empty report is a confident answer about nothing, and it would be billed.
    markdown_content = (report_data.get("markdown_content") or "").strip()
    if not markdown_content:
        status = report_data.get("status")
        logger.info(
            "report_chat_refused_not_ready",
            report_id=str(report_id),
            status=status,
        )
        raise ReportNotReadyError(report_id, status)

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
        response_text = await llm_complete(messages=messages)

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
        response_text = await llm_complete(messages=messages)

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
