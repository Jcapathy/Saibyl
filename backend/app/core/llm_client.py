# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# llm_complete(messages, model=None, temperature=0.7, max_tokens=4096,
#              response_format=None) -> str
# llm_fast(messages, temperature=0.7, max_tokens=4096) -> str
# llm_structured(messages, schema: Type[BaseModel], model=None) -> BaseModel
# llm_stream(messages, model=None) -> AsyncGenerator[str, None]
# ─────────────────────────────────────────────────────────
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import structlog
from litellm import acompletion
from pydantic import BaseModel

from app.core.config import settings
from app.services.billing.usage_ledger import record_llm_call

logger = structlog.get_logger()


def _record(resolved: str, usage: Any) -> None:
    """Send a call's token counts to the usage ledger.

    Tolerates providers that omit the cache fields. Never raises — a metering
    failure must not fail the caller's request.
    """
    if usage is None:
        return
    try:
        record_llm_call(
            model=resolved,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        )
    except Exception:
        logger.exception("llm_usage_hook_failed", model=resolved)


def _resolve_model(model: str | None, fast: bool = False) -> str:
    if model:
        return model
    base = settings.llm_fast_model if fast else settings.llm_model
    return f"{settings.llm_provider}/{base}"


def _api_key() -> str:
    return settings.anthropic_api_key


async def llm_complete(
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    **kwargs: Any,
) -> str:
    """Send messages to LLM and return text response."""
    resolved = _resolve_model(model)
    response = await acompletion(
        model=resolved,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        api_key=_api_key(),
        **kwargs,
    )
    usage = response.usage
    logger.info(
        "llm_complete",
        model=resolved,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
    )
    _record(resolved, usage)
    return response.choices[0].message.content


async def llm_fast(
    messages: list[dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    **kwargs: Any,
) -> str:
    """Complete on the fast model (`settings.llm_fast_model`).

    This is the model policy from DECISIONS_V2 §14 expressed as a call site:
    Haiku for the high-volume, low-judgment stages — agent actions and per-event
    measurement — and the main model for the stages that need judgment: ICP
    synthesis, objection canonicalization, variant scoring, report writing.

    Agent actions are ~5x cheaper here, which is the entire reason an 8-variant
    matched-swarm run is affordable. Routing them through `llm_complete` sends
    them to Opus and multiplies the dominant cost line by five.
    """
    resolved = _resolve_model(None, fast=True)
    response = await acompletion(
        model=resolved,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        api_key=_api_key(),
        **kwargs,
    )
    usage = response.usage
    logger.info(
        "llm_fast",
        model=resolved,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
    )
    _record(resolved, usage)
    return response.choices[0].message.content


async def llm_structured(
    messages: list[dict[str, str]],
    schema: type[BaseModel],
    model: str | None = None,
) -> BaseModel:
    """Send messages to LLM and return validated Pydantic model (uses fast model by default)."""
    resolved = _resolve_model(model, fast=True)
    response = await acompletion(
        model=resolved,
        messages=messages,
        response_format={"type": "json_object"},
        api_key=_api_key(),
    )
    logger.info(
        "llm_structured",
        model=resolved,
        schema=schema.__name__,
        tokens=response.usage.completion_tokens,
    )
    _record(resolved, response.usage)
    raw = response.choices[0].message.content
    # Extract clean JSON from LLM response which may include markdown
    # fences, trailing commentary, or other non-JSON text
    raw = _extract_json(raw)
    return schema.model_validate_json(raw)


def _extract_json(text: str) -> str:
    """Extract the first complete JSON object from LLM output."""
    text = text.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()
    # Find the first { and match to its closing }
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


async def llm_stream(
    messages: list[dict[str, str]],
    model: str | None = None,
    **kwargs: Any,
) -> AsyncGenerator[str, None]:
    """Stream LLM response tokens."""
    resolved = _resolve_model(model)
    response = await acompletion(
        model=resolved,
        messages=messages,
        stream=True,
        api_key=_api_key(),
        **kwargs,
    )
    async for chunk in response:
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content
