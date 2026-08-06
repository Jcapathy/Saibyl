"""One-off credit top-ups: the rate, the refusals, and the arithmetic.

The load-bearing test here is
`test_a_topup_credit_is_never_cheaper_than_a_subscription_credit`. The whole
commercial design rests on pay-as-you-go being worse value than committing, and
that is a relationship between two constants which somebody will eventually edit
one of. If it ever inverts, the product is quietly paying people not to
subscribe.

What is *not* tested here is the Stripe call itself. `create_topup_checkout`
talks to Stripe and writes a row; mocking both would mostly assert that the
function was written the way it was written. The parts worth pinning are the
pricing, which is pure, and the idempotency, which lives in Postgres and is
pinned by migration 031's `WHERE credited_at IS NULL`.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.billing.agent_pricing import (
    CREDITS_PER_USD,
    TARGET_MARGIN_PCT,
    standard_run_credits,
)
from app.services.billing.topups import (
    MAX_TOPUP_CENTS,
    MIN_TOPUP_CENTS,
    SUGGESTED_TOPUP_USD,
    TOPUP_MARGIN_PCT,
    TopupRefusedError,
    credits_for_topup,
    quote_topup,
)

# ---------------------------------------------------------------------------
# The rate
# ---------------------------------------------------------------------------

def test_a_topup_credit_is_never_cheaper_than_a_subscription_credit():
    """Pay-as-you-go must cost more per credit than committing.

    If this inverts, the product is paying people not to subscribe: a founder
    who does the division finds the monthly plan is the worse deal, and the
    recurring revenue the tiers exist to produce stops being the rational
    choice. It is one comparison between two constants and either can be edited
    alone, which is exactly why it is asserted rather than assumed.
    """
    assert TOPUP_MARGIN_PCT > TARGET_MARGIN_PCT

    dollars = 100
    topup = credits_for_topup(dollars * 100)
    subscription = int(
        Decimal(dollars)
        * Decimal(CREDITS_PER_USD)
        * (Decimal("100") - TARGET_MARGIN_PCT)
        / Decimal("100")
    )
    assert topup < subscription


def test_the_advertised_subscription_advantage_matches_the_rates():
    """The percentage on screen is derived, so it cannot drift from the rates."""
    quote = quote_topup(10_000)
    topup = credits_for_topup(10_000)
    subscription = int(
        Decimal(100)
        * Decimal(CREDITS_PER_USD)
        * (Decimal("100") - TARGET_MARGIN_PCT)
        / Decimal("100")
    )
    actual_pct = round((subscription / topup - 1) * 100)
    assert quote.subscription_is_cheaper_by_pct == actual_pct


@pytest.mark.parametrize(
    ("usd", "expected_credits"),
    [(10, 1_500), (20, 3_000), (50, 7_500), (100, 15_000)],
)
def test_the_suggested_amounts_buy_what_the_design_said(usd, expected_credits):
    """At 85% margin a dollar buys 150 credits. Pinned as published numbers."""
    assert credits_for_topup(usd * 100) == expected_credits


def test_credits_round_down_so_a_fraction_is_never_given_away():
    """The opposite direction to `credits_for`, and for the same reason.

    `credits_for` converts our cost into what we must charge, so it rounds up to
    protect the floor. This converts a payment into what we owe, so it rounds
    down. Both round in the direction that cannot serve a run at a loss.
    """
    # $10.001 would be 1500.15 credits at the current rate.
    assert credits_for_topup(1_001) == 1_501
    assert credits_for_topup(1_000) == 1_500


def test_a_nonsense_amount_buys_nothing_rather_than_raising():
    assert credits_for_topup(0) == 0
    assert credits_for_topup(-500) == 0


# ---------------------------------------------------------------------------
# The refusals
# ---------------------------------------------------------------------------

def test_below_the_floor_is_refused_with_a_reason_a_founder_can_act_on():
    with pytest.raises(TopupRefusedError) as exc:
        quote_topup(MIN_TOPUP_CENTS - 1)
    message = str(exc.value)
    assert "$10" in message
    # Not a validation code. A sentence saying why, in the register the rest of
    # the product is written in.
    assert "card fee" in message


def test_above_the_ceiling_points_at_the_thing_that_is_better_value():
    with pytest.raises(TopupRefusedError) as exc:
        quote_topup(MAX_TOPUP_CENTS + 1)
    message = str(exc.value)
    assert "monthly plan" in message
    assert "more credits for the same money" in message


def test_the_bounds_are_the_right_way_round():
    assert MIN_TOPUP_CENTS < MAX_TOPUP_CENTS


def test_every_suggested_amount_is_actually_accepted():
    """A button that leads to a refusal is a grey button with extra steps."""
    for usd in SUGGESTED_TOPUP_USD:
        quote = quote_topup(usd * 100)
        assert quote.credits > 0


# ---------------------------------------------------------------------------
# What the founder is told
# ---------------------------------------------------------------------------

def test_ten_dollars_is_reported_as_a_fraction_of_a_run_not_rounded_to_one():
    """0.5 of a run is the honest answer, and rounding it either way is a lie.

    Rounding down to "0 runs" reads as buying nothing; rounding up to "1 run"
    is an overpromise a founder discovers by running out mid-run. Neither is
    acceptable on a screen that is asking for money.
    """
    quote = quote_topup(1_000)
    assert 0 < quote.standard_runs < 1
    # Floored to one decimal, not rounded to nearest. This assertion originally
    # read `round(..., 1)` and passed — it encoded the very rounding that let
    # $20 display as "1.0 runs" against a run it could not afford.
    exact = quote.credits / standard_run_credits()
    assert quote.standard_runs <= exact
    assert exact - quote.standard_runs < 0.1


def test_the_quoted_dollar_amount_matches_the_cents_charged():
    quote = quote_topup(2_500)
    assert quote.amount_cents == 2_500
    assert quote.amount_usd == 25.0


def test_a_larger_payment_always_buys_more_credits():
    """Monotonic. A rate table with a dip in it is a bug somebody will find."""
    amounts = list(range(MIN_TOPUP_CENTS, MAX_TOPUP_CENTS, 3_137))
    credits = [credits_for_topup(a) for a in amounts]
    assert credits == sorted(credits)
    assert len(set(credits)) > 1


def test_a_near_miss_is_never_rounded_up_into_a_whole_run():
    """$20 buys 3,000 credits against a 3,014-credit run. That is not 1 run.

    Rounded to nearest it displays as 1.0, and the page then tells a founder
    that $20 buys a full-size run. It does not, and they find out when the run
    will not start. Caught by reading the deployed endpoint's own output, not
    by this file - the original test only covered the $10 case.
    """
    per_run = standard_run_credits()
    quote = quote_topup(2_000)
    assert quote.credits < per_run
    assert quote.standard_runs < 1.0


def test_the_runs_figure_never_overstates_what_was_bought():
    """Rounding down can only understate. That is the safe direction here."""
    per_run = standard_run_credits()
    for cents in range(MIN_TOPUP_CENTS, MAX_TOPUP_CENTS, 1_013):
        quote = quote_topup(cents)
        assert quote.standard_runs <= quote.credits / per_run
