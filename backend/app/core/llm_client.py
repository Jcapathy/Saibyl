# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# llm_complete(messages, model=None, temperature=0.7, max_tokens=4096,
#              response_format=None) -> str
# llm_fast(messages, temperature=0.7, max_tokens=4096) -> str
# llm_vision(prompt, images, *, media_type="image/png", system=None,
#            temperature=0.3, max_tokens=4096) -> str
# llm_structured(messages, schema: Type[BaseModel], model=None) -> BaseModel
# llm_stream(messages, model=None) -> AsyncGenerator[str, None]
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import base64
from collections.abc import AsyncGenerator
from typing import Any

import structlog
from anthropic import AsyncAnthropic
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


def _record_anthropic(resolved: str, usage: Any) -> None:
    """`_record` for the Anthropic SDK's usage field names.

    The SDK reports `input_tokens`/`output_tokens` where litellm reports
    `prompt_tokens`/`completion_tokens`. Both land in the same ledger row shape,
    so a vision call is attributed by the ambient `usage_context` and priced by
    `model_pricing` exactly like every other call.
    """
    if usage is None:
        return
    try:
        record_llm_call(
            model=resolved,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
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


# A single image above this base64 size is rejected rather than downscaled:
# callers render the screenshots and control their dimensions, so an oversized
# image is a caller bug to fix at the source, not something to quietly degrade
# by recompressing here. The ceiling sits under Anthropic's 5MB per-image limit
# with margin for the JSON envelope around it.
_MAX_IMAGE_B64_CHARS = 4_500_000


async def llm_vision(
    prompt: str,
    images: list[bytes],
    *,
    media_type: str = "image/png",
    system: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> str:
    """Send images plus a text prompt to the vision-capable main model.

    Images become Anthropic content blocks ahead of the text block, base64
    encoded here — callers pass raw bytes.

    This talks to the Anthropic SDK directly rather than through litellm:
    litellm's OpenAI→Anthropic message conversion recognises only
    `image_url`-style content parts and silently DROPS Anthropic-native image
    blocks (verified against litellm 1.82.6, `anthropic_messages_pt`). A vision
    call whose images vanish still returns 200 with a fluent hallucination —
    the worst possible failure for a critic that claims to have looked at the
    page — so the images go on the wire in Anthropic's own format, with no
    conversion layer that can drop them. Retries stay with the SDK's built-in
    backoff, the same posture `llm_complete` takes with litellm's.
    """
    if settings.llm_provider != "anthropic":
        # The payload below is Anthropic's wire format. Routing it to another
        # provider would not error — the images would be ignored — so refuse
        # loudly instead of degrading silently.
        raise NotImplementedError(
            f"llm_vision supports only the 'anthropic' provider; configured provider "
            f"is '{settings.llm_provider}'. Add a provider-specific image payload "
            "before routing vision calls elsewhere."
        )
    if not images:
        raise ValueError("llm_vision requires at least one image")

    content: list[dict[str, Any]] = []
    for index, image in enumerate(images):
        data = base64.b64encode(image).decode("ascii")
        if len(data) > _MAX_IMAGE_B64_CHARS:
            raise ValueError(
                f"Image {index} is {len(data):,} characters as base64, over the "
                f"{_MAX_IMAGE_B64_CHARS:,} limit — resize or compress it before "
                "calling llm_vision (callers control image size)."
            )
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": data},
        })
    content.append({"type": "text", "text": prompt})

    # Ledger name keeps the provider prefix ("anthropic/…") like every other
    # call site; model_pricing normalizes it away when pricing.
    resolved = _resolve_model(None)
    extra: dict[str, Any] = {}
    if system is not None:
        extra["system"] = system

    client = AsyncAnthropic(api_key=_api_key())
    # The SDK refuses non-streaming requests whose max_tokens could exceed a
    # ten-minute operation (raised live by the 32K revision ceiling) — large
    # ceilings must stream and accumulate. Both paths end at the same usage
    # object and text join.
    if max_tokens > 8192:
        async with client.messages.stream(
            model=settings.llm_model,
            messages=[{"role": "user", "content": content}],
            temperature=temperature,
            max_tokens=max_tokens,
            **extra,
        ) as stream:
            response = await stream.get_final_message()
    else:
        response = await client.messages.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": content}],
            temperature=temperature,
            max_tokens=max_tokens,
            **extra,
        )
    usage = response.usage
    logger.info(
        "llm_vision",
        model=resolved,
        images=len(images),
        prompt_tokens=getattr(usage, "input_tokens", 0),
        completion_tokens=getattr(usage, "output_tokens", 0),
    )
    _record_anthropic(resolved, usage)
    return "".join(block.text for block in response.content if block.type == "text")


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
