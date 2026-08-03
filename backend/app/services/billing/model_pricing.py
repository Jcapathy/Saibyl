# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# price_for(model) -> ModelPrice
# cost_usd(model, input_tokens, output_tokens, cache_read, cache_write) -> Decimal
# ─────────────────────────────────────────────────────────
"""Per-model token prices, in USD per million tokens.

This is the single source of truth for what a Claude call costs. Everything
that quotes a price to a customer derives from here, so that a price change
is one edit rather than a hunt through hardcoded constants.

Prices are Anthropic first-party API rates. Bedrock and Vertex are billed by
those providers at their own rates; if Saibyl ever runs there, add a separate
table rather than editing these.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import structlog

logger = structlog.get_logger()

_MILLION = Decimal(1_000_000)

# Cache reads bill at ~0.1x the input rate; 5-minute-TTL writes at ~1.25x.
CACHE_READ_MULTIPLIER = Decimal("0.1")
CACHE_WRITE_MULTIPLIER = Decimal("1.25")


@dataclass(frozen=True)
class ModelPrice:
    input_per_mtok: Decimal
    output_per_mtok: Decimal


# Keyed by the model ID prefix. Lookup matches on prefix so dated snapshots
# (e.g. claude-haiku-4-5-20251001) resolve to the same price as the alias.
_PRICES: dict[str, ModelPrice] = {
    "claude-fable-5": ModelPrice(Decimal("10.00"), Decimal("50.00")),
    "claude-mythos-5": ModelPrice(Decimal("10.00"), Decimal("50.00")),
    "claude-opus-5": ModelPrice(Decimal("5.00"), Decimal("25.00")),
    "claude-opus-4-8": ModelPrice(Decimal("5.00"), Decimal("25.00")),
    "claude-opus-4-7": ModelPrice(Decimal("5.00"), Decimal("25.00")),
    "claude-opus-4-6": ModelPrice(Decimal("5.00"), Decimal("25.00")),
    "claude-opus-4-5": ModelPrice(Decimal("5.00"), Decimal("25.00")),
    "claude-sonnet-5": ModelPrice(Decimal("3.00"), Decimal("15.00")),
    "claude-sonnet-4-6": ModelPrice(Decimal("3.00"), Decimal("15.00")),
    "claude-sonnet-4-5": ModelPrice(Decimal("3.00"), Decimal("15.00")),
    "claude-haiku-4-5": ModelPrice(Decimal("1.00"), Decimal("5.00")),
}

# Used when a model ID matches nothing above. Deliberately the most expensive
# entry: an unknown model should over-estimate cost, never under-charge.
_FALLBACK_PRICE = ModelPrice(Decimal("10.00"), Decimal("50.00"))


def _normalize(model: str) -> str:
    """Strip a provider prefix (litellm 'anthropic/…', Bedrock 'anthropic.…')."""
    if "/" in model:
        model = model.rsplit("/", 1)[-1]
    if model.startswith("anthropic."):
        model = model[len("anthropic.") :]
    return model


def price_for(model: str) -> ModelPrice:
    """Resolve a model ID to its price, matching on the longest known prefix."""
    normalized = _normalize(model)

    if normalized in _PRICES:
        return _PRICES[normalized]

    # Longest prefix wins so claude-opus-4-8 isn't matched by a shorter key.
    matches = [key for key in _PRICES if normalized.startswith(key)]
    if matches:
        return _PRICES[max(matches, key=len)]

    logger.warning(
        "unknown_model_price",
        model=model,
        note="falling back to highest known rate; add it to _PRICES",
    )
    return _FALLBACK_PRICE


def cost_usd(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> Decimal:
    """Cost of a single call in USD.

    `input_tokens` should be the uncached remainder — the Anthropic API reports
    cached tokens separately, and double-counting them inflates the figure.
    """
    price = price_for(model)

    billable_input = (
        Decimal(input_tokens)
        + Decimal(cache_read_tokens) * CACHE_READ_MULTIPLIER
        + Decimal(cache_write_tokens) * CACHE_WRITE_MULTIPLIER
    )

    return (
        billable_input * price.input_per_mtok
        + Decimal(output_tokens) * price.output_per_mtok
    ) / _MILLION
