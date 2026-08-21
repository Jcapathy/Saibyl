"""A paying customer gets what they paid for (P0-9).

The defect: `PLAN_LIMITS` held only the V2 tier names — `starter`, `pro`,
`enterprise` — while V3 sells `founder`, `growth` and `agency`. Every lookup
falls back to `PLAN_LIMITS["starter"]`, so an Agency customer at $999/mo was
enforced at 15 runs a month against the 66 their grant buys. Nothing failed:
the fallback made a stale table look like a deliberate policy.

Two rules are pinned here, and the second is the one that makes the first
safe:

1. Every tier that can be sold has its own limits. Deriving them from
   `TIER_CREDIT_GRANTS` — the single place a tier is defined — is what makes
   a missing tier impossible rather than merely fixed once.
2. The cap sits strictly above what the grant buys. Level with it, this table
   silently becomes the binding constraint the moment somebody buys top-up
   credits, and they have paid for credits they are forbidden to spend.
"""
from __future__ import annotations

import pytest

from app.services.billing.agent_pricing import TIER_CREDIT_GRANTS, capped_run_credits
from app.services.billing.stripe_service import PLAN_LIMITS

PAID_TIERS = ("founder", "starter", "growth", "pro", "agency", "enterprise")


@pytest.mark.parametrize("plan", sorted(TIER_CREDIT_GRANTS))
def test_every_sellable_tier_has_its_own_limits(plan):
    assert plan in PLAN_LIMITS, (
        f"'{plan}' can be sold but has no limits, so it falls back to the "
        f"cheapest tier's — which is how Agency customers were capped at 15."
    )


@pytest.mark.parametrize("plan", sorted(TIER_CREDIT_GRANTS))
def test_the_cap_never_bites_before_the_credit_balance_does(plan):
    """Credits ration; this is a runaway backstop. If the cap is level with
    what the grant buys, a founder who tops up has bought credits the cap
    forbids them to spend."""
    buys = TIER_CREDIT_GRANTS[plan] // max(capped_run_credits(plan), 1)

    assert PLAN_LIMITS[plan]["max_simulations_per_month"] > max(buys, 1), (
        f"'{plan}' caps at its own grant, so topped-up credits are unspendable"
    )


def test_the_paid_tiers_are_not_all_pinned_to_the_free_allowance():
    """The shape of the original bug, stated directly: every V3 tier resolving
    to the same number as the cheapest one."""
    free = PLAN_LIMITS["free"]["max_simulations_per_month"]

    for plan in PAID_TIERS:
        assert PLAN_LIMITS[plan]["max_simulations_per_month"] > free, (
            f"'{plan}' is a paid tier allowed no more runs than free"
        )


def test_more_expensive_tiers_allow_strictly_more():
    ladder = ["free", "founder", "growth", "agency"]
    allowances = [PLAN_LIMITS[p]["max_simulations_per_month"] for p in ladder]

    assert allowances == sorted(allowances), f"ladder is not monotonic: {allowances}"
    assert len(set(allowances)) == len(allowances), (
        f"two rungs of the ladder allow the same: {dict(zip(ladder, allowances))}"
    )


def test_the_v2_and_v3_names_for_one_tier_agree():
    """`founder` and `starter` are the same tier under two names. If they ever
    disagree, which one a customer gets depends on which string their row
    happens to carry."""
    for old, new in (("starter", "founder"), ("pro", "growth"), ("enterprise", "agency")):
        assert PLAN_LIMITS[old] == PLAN_LIMITS[new], (
            f"'{old}' and '{new}' are one tier but resolve differently"
        )
