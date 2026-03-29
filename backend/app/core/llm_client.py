# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# llm_complete(messages, model=None, temperature=0.7, max_tokens=4096,
#              response_format=None) -> str
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

logger = structlog.get_logger()


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
    return schema.model_validate_json(response.choices[0].message.content)


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
