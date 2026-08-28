# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# llm_complete(messages, model=None, max_tokens=8192) -> str
# llm_fast(messages, max_tokens=4096) -> str
# llm_vision(prompt, images, *, media_type="image/png", system=None,
#            max_tokens=8192) -> str
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
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.services.billing.usage_ledger import record_llm_call

logger = structlog.get_logger()

# **Sampling parameters are gone, and that is not a style choice.**
# `temperature`, `top_p` and `top_k` are rejected with a 400 on Opus 4.7 and
# later. Every function here used to pass `temperature`, and twelve call sites
# passed their own value; on 2026-08-28 all of it was removed so the model could
# move to `claude-opus-5`. Adding any of them back breaks every LLM call in the
# product, not just the one that was edited. Determinism is now `effort`.
#
# **Why the ceiling went up.** On Opus 5 thinking is ON by default, and
# `max_tokens` is a hard cap on thinking PLUS the response text. The old 4096
# was sized around the answer alone on a model that did not think, so the same
# request can now truncate mid-sentence — which lands here as a JSON parse
# failure in `llm_structured`, having already been paid for. 8192 restores the
# old headroom for the answer and leaves room for the reasoning.
#
# It is deliberately not higher: `llm_vision` streams above 8192 (the SDK
# refuses long non-streaming requests), so this is the largest value that keeps
# both paths on their current behaviour.
_OPUS_MAX_TOKENS = 8192


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
    max_tokens: int = _OPUS_MAX_TOKENS,
    **kwargs: Any,
) -> str:
    """Send messages to LLM and return text response."""
    resolved = _resolve_model(model)
    response = await acompletion(
        model=resolved,
        messages=messages,
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
    max_tokens: int = _OPUS_MAX_TOKENS,
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
            max_tokens=max_tokens,
            **extra,
        ) as stream:
            response = await stream.get_final_message()
    else:
        response = await client.messages.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": content}],
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


# How many times a malformed structured response is handed back to the model
# to correct before the call is given up on.
#
# **Why this exists.** A live pipeline run lost a 2,500-credit outbound
# sequence to one truncated brace: the model emitted JSON that stopped mid
# string, `model_validate_json` raised, and there was no second attempt. One
# unlucky token destroyed a paid artifact, and the founder was told to "try
# building it again", which costs them the same again.
#
# Two retries rather than one because the failure is random rather than
# systematic — a schema the model genuinely cannot satisfy fails all three
# times and should, while a truncation or a stray comma almost never repeats.
# The corrective turn carries the parser's own error, so the model is told
# what was wrong rather than merely asked again.
STRUCTURED_RETRIES = 2


async def llm_structured(
    messages: list[dict[str, str]],
    schema: type[BaseModel],
    model: str | None = None,
) -> BaseModel:
    """Send messages to LLM and return a validated Pydantic model.

    Retries a malformed response up to `STRUCTURED_RETRIES` times, showing the
    model its own output and the parse error. Raises the last
    `ValidationError` if none of the attempts parse — callers distinguish that
    from a deliberate refusal, which is a `ValueError` they raise themselves.
    """
    resolved = _resolve_model(model, fast=True)
    attempt_messages = list(messages)
    last_error: ValidationError | None = None

    for attempt in range(STRUCTURED_RETRIES + 1):
        response = await acompletion(
            model=resolved,
            messages=attempt_messages,
            response_format={"type": "json_object"},
            api_key=_api_key(),
        )
        logger.info(
            "llm_structured",
            model=resolved,
            schema=schema.__name__,
            tokens=response.usage.completion_tokens,
            attempt=attempt + 1,
        )
        # Recorded per attempt, not per call: a retry is real spend, and a
        # ledger that counted only the successful turn would understate COGS
        # exactly when the model is behaving worst.
        _record(resolved, response.usage)

        raw = response.choices[0].message.content
        # Extract clean JSON from LLM response which may include markdown
        # fences, trailing commentary, or other non-JSON text
        cleaned = _extract_json(raw)
        try:
            return schema.model_validate_json(cleaned)
        except ValidationError as exc:
            last_error = exc
            logger.warning(
                "llm_structured_unparseable",
                model=resolved,
                schema=schema.__name__,
                attempt=attempt + 1,
                remaining=STRUCTURED_RETRIES - attempt,
                error=str(exc)[:300],
            )
            if attempt == STRUCTURED_RETRIES:
                break
            attempt_messages = [
                *attempt_messages,
                {"role": "assistant", "content": raw or ""},
                {
                    "role": "user",
                    "content": (
                        "That response did not parse against the required "
                        f"schema:\n\n{str(exc)[:1500]}\n\n"
                        "Return the same content as a single valid JSON "
                        "object matching the schema. No commentary, no code "
                        "fences, and close every string and brace."
                    ),
                },
            ]

    assert last_error is not None
    raise last_error


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
