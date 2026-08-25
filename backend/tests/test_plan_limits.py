"""Limits under pay-as-you-go: credits ration, and nothing else may.

**This file used to pin a tier ladder.** It asserted that `founder` allowed
strictly more runs than `free`, that the ladder was monotonic, and that the V2
and V3 names for one tier agreed — all of which existed to catch P0-9, where
`PLAN_LIMITS` held only the V2 names and an Agency customer at $999/mo was
silently enforced at fifteen runs a month.

The founder removed subscription tiers on 2026-08-24 and moved Saibyl to
top-ups, so there is no ladder left to be monotonic. The bug those tests caught
cannot recur, because the thing that had rungs is gone.

One rule survives the change, and it is the one that made the others safe:

    **The cap never bites before the credit balance does.**

Under tiers that mattered because a limit level with the grant meant a founder
who topped up had bought credits the cap forbade them to spend. Under
pay-as-you-go it matters *more*, because topping up is now the only way anyone
pays — a monthly run cap derived from the grant would resolve to roughly ten
runs and bind on the first real customer. So the backstop is flat, plan-free
and set far above any honest month's use: it exists to catch automation gone
wrong, never to price anything.
"""
from __future__ import annotations

import pytest

from app.services.billing.agent_pricing import FREE_RUN_GRANT, free_run_credits
from app.services.billing.stripe_service import PLAN_LIMITS

# Every plan string that still exists in `organizations.plan` on real rows.
# Production held `free`, `starter`, `founder` and `enterprise` on the day
# tiers were removed; the column is dead but the values are not, and a lookup
# that raised on them would turn stale data into an outage.
LEGACY_PLAN_STRINGS = (
    "free",
    "trial",
    "founder",
    "starter",
    "growth",
    "pro",
    "agency",
    "enterprise",
)


@pytest.mark.parametrize("plan", LEGACY_PLAN_STRINGS)
def test_every_legacy_plan_string_still_resolves(plan):
    """A dead column must not be able to raise."""
    limits = PLAN_LIMITS[plan]

    assert limits["max_simulations_per_month"] > 0
    assert limits["max_team_members"] > 0


@pytest.mark.parametrize("plan", LEGACY_PLAN_STRINGS)
def test_the_cap_never_bites_before_the_credit_balance_does(plan):
    """The rule that outlived the tiers.

    A founder who buys credits must be able to spend them. The backstop has to
    sit far enough above what any balance realistically buys that it is only
    ever reached by a loop that has gone wrong.
    """
    buys_on_the_grant = FREE_RUN_GRANT // max(free_run_credits(), 1)

    assert PLAN_LIMITS[plan]["max_simulations_per_month"] > buys_on_the_grant * 100, (
        "the monthly backstop is close enough to what a balance buys that it "
        "could become the binding constraint — which makes it a pricing "
        "mechanism, and pricing is credits' job"
    )


def test_no_plan_string_buys_anything_another_one_does_not():
    """There is no ladder. Two accounts differ by what they have paid into
    their balance, never by a string in a column nobody sells any more."""
    answers = {plan: PLAN_LIMITS[plan] for plan in LEGACY_PLAN_STRINGS}

    assert len({tuple(sorted(limits.items())) for limits in answers.values()}) == 1, (
        f"plan strings still resolve differently, so a tier survives: {answers}"
    )


def test_an_unknown_plan_string_resolves_rather_than_raising():
    """Rows written by a future migration, a seed script or a typo."""
    assert PLAN_LIMITS["something-nobody-has-heard-of"] == PLAN_LIMITS["free"]
