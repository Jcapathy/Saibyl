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

def test_a_topup_credit_is_never_priced_below_the_margin_floor():
    """**Restated 2026-08-25. The old premise no longer exists.**

    This used to assert `TOPUP_MARGIN_PCT > TARGET_MARGIN_PCT`, because a
    top-up was deliberately worse value per credit than a subscription so that
    subscribing was the rational choice. Subscriptions were removed on
    2026-08-24, and with nothing to steer anyone toward, the surcharge was a
    third off the value of every credit for no stated reason. The founder
    levelled it.

    What survives is the half that was always about solvency rather than about
    steering: a credit may never be sold below the margin the cost model is
    built on. Equal is the floor. Below it, every run bought with those credits
    is served at a loss.
    """
    assert TOPUP_MARGIN_PCT >= TARGET_MARGIN_PCT

    # And in credits rather than only in percentages, since that is the number
    # a founder actually receives: a dollar may never buy more than the margin
    # floor allows.
    dollars = 100
    at_the_floor = int(
        Decimal(dollars)
        * Decimal(CREDITS_PER_USD)
        * (Decimal("100") - TARGET_MARGIN_PCT)
        / Decimal("100")
    )
    assert credits_for_topup(dollars * 100) <= at_the_floor


@pytest.mark.parametrize(
    ("usd", "expected_credits"),
    [(10, 2_000), (20, 4_000), (50, 10_000), (100, 20_000)],
)
def test_the_suggested_amounts_buy_what_the_design_said(usd, expected_credits):
    """At 80% margin a dollar buys 200 credits. Pinned as published numbers.

    Was 150 a dollar at the old 85%. Every figure here rose by a third when the
    subscription surcharge was removed."""
    assert credits_for_topup(usd * 100) == expected_credits


def test_credits_round_down_so_a_fraction_is_never_given_away():
    """The opposite direction to `credits_for`, and for the same reason.

    `credits_for` converts our cost into what we must charge, so it rounds up to
    protect the floor. This converts a payment into what we owe, so it rounds
    down. Both round in the direction that cannot serve a run at a loss.

    **At the current rate no fraction actually arises**: an 80% margin makes
    credits exactly `cents * 2`, so there is nothing to round. The direction is
    asserted against the exact quotient anyway, because the rate is a constant
    and the next person to move it should not have to rediscover which way this
    is supposed to fall.
    """
    for cents in (1_000, 1_001, 2_345, 49_999):
        exact = (
            Decimal(cents)
            / Decimal(100)
            * Decimal(CREDITS_PER_USD)
            * (Decimal("100") - TOPUP_MARGIN_PCT)
            / Decimal("100")
        )
        assert credits_for_topup(cents) <= exact, cents


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


def test_above_the_ceiling_says_what_to_do_instead():
    with pytest.raises(TopupRefusedError) as exc:
        quote_topup(MAX_TOPUP_CENTS + 1)
    message = str(exc.value)
    # It used to point at a monthly plan. That plan was removed the day before
    # this assertion was, so the refusal was sending a founder to look for
    # something that no longer existed. A ceiling has to say what to do next.
    assert "add more" in message
    assert "never expire" in message
    assert "plan" not in message.lower()


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
    """The defect: a balance that nearly buys a run displaying as one.

    $20 used to buy 3,000 credits against a 3,014-credit run. Rounded to
    nearest that displays as 1.0, and the page then tells a founder $20 buys a
    full-size run. It does not, and they find out when the run will not start.

    **$20 now genuinely buys more than a run** (4,000 credits at the levelled
    margin), so the old example stopped being an example. The property is what
    matters and it is asserted directly: whatever amount lands just short of a
    run must never display as a whole one.
    """
    per_run = standard_run_credits()

    # The largest whole-dollar amount that still buys less than one run.
    cents = 100
    while credits_for_topup(cents + 100) < per_run:
        cents += 100
    just_short = quote_topup(cents)

    assert just_short.credits < per_run
    assert just_short.standard_runs < 1.0


def test_the_runs_figure_never_overstates_what_was_bought():
    """Rounding down can only understate. That is the safe direction here."""
    per_run = standard_run_credits()
    for cents in range(MIN_TOPUP_CENTS, MAX_TOPUP_CENTS, 1_013):
        quote = quote_topup(cents)
        assert quote.standard_runs <= quote.credits / per_run


# ---------------------------------------------------------------------------
# The refusal a founder actually receives
# ---------------------------------------------------------------------------

def test_the_api_returns_the_sentence_not_a_validation_code():
    """The refusals above must survive the trip through FastAPI.

    They did not. `TopupRequest.amount_cents` carried `ge`/`le`, so Pydantic
    rejected out-of-range amounts *before* the handler ran and a founder who
    typed $5 got back `Input should be greater than or equal to 1000` — a
    validation code, in cents, naming a field they never see. Every test above
    passed throughout, because they call `quote_topup` directly.

    Found by reading the deployed endpoint's response. This one asserts on the
    schema that produced the defect rather than on a live call, so it holds
    without a server.
    """
    from app.api.billing import TopupRequest

    field = TopupRequest.model_fields["amount_cents"]
    constraints = {
        type(m).__name__: getattr(m, "ge", getattr(m, "le", None))
        for m in field.metadata
    }
    # A `Ge` of exactly the business floor means the business rule is back on
    # the field, and the sentence is unreachable again.
    assert constraints.get("Ge") != MIN_TOPUP_CENTS
    assert constraints.get("Le") != MAX_TOPUP_CENTS

    # And the handler still refuses it, with words.
    with pytest.raises(TopupRefusedError):
        quote_topup(500)


def test_the_credits_endpoint_sends_every_field_its_readers_ask_for():
    """Two clients read `balance`/`grant`; the endpoint sent `credits_*`.

    Neither would have thrown. Both would have rendered a balance of zero —
    which is the single number most likely to stop a founder clicking, and it
    would have been wrong for every account with credits on it. Caught by
    reading the route against the component rather than by either side's tests,
    because each was internally consistent.

    Asserted on the handler's returned keys so it holds without a server.
    """
    import inspect

    from app.api import billing

    source = inspect.getsource(billing.credit_balance)
    for key in ('"balance"', '"grant"', '"standard_run_credits"',
                '"credits_balance"', '"credits_granted"'):
        assert key in source, f"{key} is no longer returned by /billing/credits"
