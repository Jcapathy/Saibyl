# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# TOPUP_MARGIN_PCT     — the margin a one-off top-up is priced at
# MIN_TOPUP_CENTS      — the smallest top-up we will take
# MAX_TOPUP_CENTS      — the largest single top-up we will take
# SUGGESTED_TOPUP_USD  — the amounts shown as buttons
# TopupQuote           — what a given amount buys, and how it compares
# TopupRefusedError    — the amount is outside what we will take
# quote_topup(cents)   — price one top-up
# ─────────────────────────────────────────────────────────
"""One-off credit top-ups. The only way anyone pays for Saibyl.

**This module used to describe a different business.** It opened "priced above
the subscription rate", explained that a top-up deliberately cost more per
credit so that committing to $99 a month was "visibly and arithmetically the
better deal", and published the 33% gap to the founder. Subscription tiers were
removed on 2026-08-24 (PRD_V3 §6) and the surcharge with them on 2026-08-25, so
none of that is true any more and all of it has gone.

**What a top-up is now.** A founder buys credits when they want them, at the
same margin the cost model is built on. Nothing renews, nothing expires, and
the first run is free. `TOPUP_MARGIN_PCT` below is the whole of the pricing.

**No Stripe Price ID is involved.** A top-up is an ad-hoc `unit_amount` on a
`mode="payment"` Checkout session, which is why it could ship when the tier
migration never did.

The rate lives in this module and nowhere else. Two places that both convert
dollars to credits is the "two sources of truth" class, and the symptom is a
founder charged at one rate and credited at another.
"""
from __future__ import annotations

from decimal import ROUND_FLOOR, Decimal

from pydantic import BaseModel

from app.services.billing.agent_pricing import (
    CREDITS_PER_USD,
    TARGET_MARGIN_PCT,
    standard_run_credits,
)

# **Equal to `TARGET_MARGIN_PCT` since 2026-08-25. Founder decision.**
#
# This was 85% against a target of 80%, and the five-point gap was deliberate:
# it made a top-up worse value per credit than a subscription, so that
# subscribing was "visibly and arithmetically the better deal". The page even
# published the difference, as `subscription_is_cheaper_by_pct`, which came out
# at 33%.
#
# There is no subscription. It was removed on 2026-08-24, and the moment it went
# the surcharge stopped steering anyone anywhere and became a third off the
# value of every credit for no reason anybody could state. Levelling it is the
# whole of the "make it affordable" instruction: it takes about 25% off every
# price published on the landing page.
#
# It must still never go BELOW `TARGET_MARGIN_PCT`, which is the margin floor
# the cost model is built on, and the test suite asserts that. Equal is the
# floor, not a step past it.
TOPUP_MARGIN_PCT = TARGET_MARGIN_PCT

# $10 is the floor because it is the smallest amount that buys a run a founder
# would recognise as a result. Below it, Stripe's own per-transaction fee is a
# double-digit percentage of the payment, and the founder gets a fraction of a
# run — an experience that argues against the product.
MIN_TOPUP_CENTS = 1_000

# $500 is the ceiling on a SINGLE top-up, not on what anyone may hold. It is a
# guard against a mistyped amount rather than a commercial limit: nothing stops
# a founder adding more immediately afterwards, and the refusal says so.
MAX_TOPUP_CENTS = 50_000

# What the buttons offer. Any amount in range is accepted — these are shortcuts,
# not a price list, and the field beside them takes anything.
SUGGESTED_TOPUP_USD: tuple[int, ...] = (10, 20, 50, 100)


class TopupQuote(BaseModel):
    """What an amount buys, said in the units a founder actually thinks in."""

    amount_cents: int
    amount_usd: float
    credits: int

    # Runs of the reference shape. A float because 0.7 of a run is the honest
    # answer at $10 and rounding it to "0 runs" or "1 run" would both be lies.
    standard_runs: float



def credits_for_topup(amount_cents: int) -> int:
    """Credits bought by a payment, rounding **down**.

    Down, not up — the opposite of `credits_for`, and for the same reason. That
    function converts our cost into credits we must charge, so rounding up
    protects the margin floor. This one converts a customer's payment into
    credits we owe, so rounding up would give away a fraction of a credit on
    every top-up. Both round in the direction that cannot serve a run at a loss.
    """
    if amount_cents <= 0:
        return 0
    dollars = Decimal(amount_cents) / Decimal(100)
    cogs_share = (Decimal("100") - TOPUP_MARGIN_PCT) / Decimal("100")
    credits = dollars * Decimal(CREDITS_PER_USD) * cogs_share
    return int(credits.to_integral_value(rounding=ROUND_FLOOR))


# `_subscription_advantage_pct()` stood here. It derived how much further a
# dollar went on a subscription, 33% from the 80%/85% margins, so the top-up
# screen could tell a founder checkably that subscribing was the better deal.
# Subscriptions went on 2026-08-24 and the surcharge it measured went on
# 2026-08-25. Nothing replaced it, because there is nothing left to compare.


class TopupRefusedError(ValueError):
    """The amount is outside what we will take, with the reason in words."""


def _runs_display(credits: int, per_run: int) -> float:
    """How many runs this buys, rounded **down** to one decimal place.

    Down, not to nearest, and this is not fussiness. At the old rate $20 bought
    3,000 credits against a 3,014-credit run, 0.995 of one. Rounded to nearest
    that displays as **1.0**, so the page told a founder $20 buys a full-size
    run when it did not, and they found out when the run would not start. The
    levelled margin moved that particular example past the line, which is
    exactly why the rounding rule is asserted as a property rather than pinned
    to $20.

    Rounding down can only ever understate what they get, which is the safe
    direction for a number on a screen that is asking for money.
    """
    if per_run <= 0:
        return 0.0
    exact = Decimal(credits) / Decimal(per_run)
    return float(exact.quantize(Decimal("0.1"), rounding=ROUND_FLOOR))


def quote_topup(amount_cents: int) -> TopupQuote:
    """Price one top-up, or refuse it with a sentence a founder can act on."""
    if amount_cents < MIN_TOPUP_CENTS:
        raise TopupRefusedError(
            f"The smallest top-up is ${MIN_TOPUP_CENTS // 100}. Below that, the "
            f"card fee takes a large share of it and you would not get enough "
            f"credits to finish a run."
        )
    if amount_cents > MAX_TOPUP_CENTS:
        raise TopupRefusedError(
            # Said "a monthly plan gives you more credits for the same money"
            # until 2026-08-25, which sent a founder looking for a plan that had
            # been removed the day before. A refusal that points at nothing is
            # worse than a bare limit.
            f"The largest single top-up is ${MAX_TOPUP_CENTS // 100:,}. You can "
            f"add more straight after, as many times as you like, and credits "
            f"never expire. If you want to put on a lot at once, email us."
        )

    credits = credits_for_topup(amount_cents)
    per_run = standard_run_credits()
    return TopupQuote(
        amount_cents=amount_cents,
        amount_usd=amount_cents / 100,
        credits=credits,
        standard_runs=_runs_display(credits, per_run),
    )
