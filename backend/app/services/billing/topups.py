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
"""One-off credit top-ups, priced above the subscription rate.

**Why a top-up exists.** A founder deciding whether this is worth $99 a month
should be able to spend $10 and find out. The alternative — a free tier that
runs out and a monthly commitment as the only next step — asks for the big
decision at the exact moment they have the least evidence.

**Why it costs more per credit than a subscription.** Pay-as-you-go is priced
at a higher margin so that subscribing is visibly and arithmetically the better
deal, and the page says so in those words rather than hoping nobody divides.
Concretely: a subscription buys credits at 80% margin, a top-up at 85%, so a
subscribed credit is **33% cheaper**. That number is derived here rather than
written down anywhere, so it cannot drift from the rates it describes.

**No Stripe Price ID is involved.** A top-up is an ad-hoc `unit_amount` on a
`mode="payment"` Checkout session, which is why this could ship while the tier
migration is still blocked on Stripe Products.

The rate lives in this module and nowhere else. Two places that both convert
dollars to credits is the "two sources of truth" class, and the symptom is a
founder charged at one rate and credited at another.
"""
from __future__ import annotations

from decimal import ROUND_FLOOR, Decimal

from pydantic import BaseModel

from app.services.billing.agent_pricing import (
    CREDITS_PER_USD,
    standard_run_credits,
)

# A top-up is priced at a higher margin than a subscription, deliberately.
# Raising this makes top-ups worse value and pushes harder toward subscribing;
# lowering it toward TARGET_MARGIN_PCT makes them equivalent. It must never go
# below TARGET_MARGIN_PCT — that would make the pay-as-you-go option cheaper
# than the commitment, which is backwards, and the test suite asserts it.
TOPUP_MARGIN_PCT = Decimal("85")

# $10 is the floor because it is the smallest amount that buys a run a founder
# would recognise as a result. Below it, Stripe's own per-transaction fee is a
# double-digit percentage of the payment, and the founder gets a fraction of a
# run — an experience that argues against the product.
MIN_TOPUP_CENTS = 1_000

# $500 is the ceiling. Past it a subscription is cheaper on the same credits and
# refusing is the honest answer; the message says so and points at the plans.
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
# dollar went on a subscription — 33%, from the 80%/85% margins — so the top-up
# screen could tell a founder, checkably, that subscribing was the better deal.
#
# Subscriptions were removed on 2026-08-25 (PRD_V3 §6), so there is nothing left
# to be better than and the field it fed is gone from `TopupQuote`.
#
# **`TOPUP_MARGIN_PCT` is still 85% and that is now a live question rather than
# a settled one.** The five points above `TARGET_MARGIN_PCT` existed only to
# make subscribing look good; with no subscription they make credits 33% dearer
# than they need to be, for no remaining reason. Lowering it to
# `TARGET_MARGIN_PCT` is a pricing decision for the founder, not a cleanup, so
# it is flagged here rather than taken.


class TopupRefusedError(ValueError):
    """The amount is outside what we will take, with the reason in words."""


def _runs_display(credits: int, per_run: int) -> float:
    """How many runs this buys, rounded **down** to one decimal place.

    Down, not to nearest, and this is not fussiness. At the current rate $20
    buys 3,000 credits against a 3,014-credit run — 0.995 of one. Rounded to
    nearest that displays as **1.0**, so the page tells a founder $20 buys a
    full-size run and it does not. They find out when the run they paid for
    will not start.

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
            f"The largest top-up is ${MAX_TOPUP_CENTS // 100:,}. Above that a "
            f"monthly plan gives you more credits for the same money — have a "
            f"look at those instead."
        )

    credits = credits_for_topup(amount_cents)
    per_run = standard_run_credits()
    return TopupQuote(
        amount_cents=amount_cents,
        amount_usd=amount_cents / 100,
        credits=credits,
        standard_runs=_runs_display(credits, per_run),
    )
