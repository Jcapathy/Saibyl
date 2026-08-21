"""Every artifact a founder can be charged for must carry a published price.

This exists because the same defect shipped three times. `capital_shortlist`,
`messaging_doc` and `outbound_sequence` were each priced in `agent_pricing`
and each charged by their own route, and none of the three appeared in
`GET /billing/prices` — the one surface whose entire purpose is that a founder
learns the cost *before* doing the work. All three would have met their price
as a 402 at submit.

It shipped three times for one reason: **nothing failed when an artifact was
left out.** Adding a price function and a charging route are two deliberate
acts; publishing the price is a third that nobody is reminded to perform. So
the reminder is this test. It reads the pricing module itself rather than a
hand-kept list, which means a fourth artifact added tomorrow fails here on the
day it is priced rather than on the day a founder hits the wall.

The `_`-prefixed helpers and the run-level functions are excluded by name and
each exclusion is argued below; anything else that ends in `_credits` is an
artifact and must be published.
"""
from __future__ import annotations

import inspect

import pytest

from app.services.billing import agent_pricing

# Not artifacts, and each for its own reason:
#
#   standard_run_credits / capped_run_credits — a *run* is priced per agent,
#     round and arena, so its cost is quoted by `/billing/estimate-cost`
#     against the founder's actual configuration rather than by a flat number.
#   deduct_credits — a mutation that happens to end in the same word.
#
# Everything else that prices something a founder buys belongs on the prices
# screen, and a new name lands in this test's scope automatically.
_NOT_ARTIFACTS = {
    "standard_run_credits",
    "capped_run_credits",
    "deduct_credits",
}

# `clearance` is published as a nested object keyed by tier rather than as a
# flat entry, because one USPTO search has three prices. Its key in the
# response is the artifact name without the `_credits` suffix, same as the
# others; only its *shape* differs.
_NESTED = {"clearance"}


def _priced_artifacts() -> set[str]:
    """Every artifact the pricing module knows how to charge for."""
    found = set()
    for name, obj in vars(agent_pricing).items():
        if name.startswith("_") or not name.endswith("_credits"):
            continue
        if name in _NOT_ARTIFACTS or not inspect.isfunction(obj):
            continue
        found.add(name.removesuffix("_credits"))
    return found


def test_the_pricing_module_actually_has_artifacts_to_check():
    """A guard on the guard. If the naming convention changes, this test would
    otherwise pass by finding nothing and assert about an empty set."""
    artifacts = _priced_artifacts()

    assert len(artifacts) >= 5, f"only found {artifacts}; has the convention moved?"
    assert "website_check" in artifacts
    assert "capital_shortlist" in artifacts


def test_every_priced_artifact_is_published_on_the_prices_screen():
    """The assertion the three shipped defects would each have failed."""
    from app.api import billing

    source = inspect.getsource(billing.paid_feature_prices)
    missing = sorted(
        artifact for artifact in _priced_artifacts()
        if f'"{artifact}"' not in source
    )

    assert not missing, (
        f"priced but never published: {missing}. A founder meets these as a "
        f"402 at submit instead of a price before the click. Add an entry to "
        f"GET /billing/prices."
    )


@pytest.mark.parametrize("artifact", sorted(_priced_artifacts() - _NESTED))
def test_each_published_price_is_a_real_number_with_a_label(artifact):
    """Published is not the same as usable. An entry carrying a null price or
    an empty label renders as a blank tag, which is the same experience as no
    entry at all."""
    price_fn = getattr(agent_pricing, f"{artifact}_credits")
    credits = price_fn()

    assert isinstance(credits, int), f"{artifact} priced as {type(credits)}"
    assert credits > 0, f"{artifact} priced at {credits}"
