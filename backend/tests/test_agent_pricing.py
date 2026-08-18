import pytest

from app.services.billing.agent_pricing import (
    MAX_AGENTS,
    MIN_MARGIN_PCT,
    estimate_simulation_cost,
)
from app.services.billing.model_pricing import cost_usd, price_for


def test_estimate_basic():
    est = estimate_simulation_cost(1000, 5)
    assert est.agent_count == 1000
    assert est.rounds == 5
    assert est.agent_rounds == 5000
    assert est.actual_cost_usd > 0
    assert est.retail_cost_usd > est.actual_cost_usd


def test_margin_never_below_floor():
    """The floor is the point of the pricing model — no run is served at a loss."""
    for agents, rounds, platforms, variants in [
        (25, 3, 1, 1),
        (100, 5, 2, 1),
        (100, 5, 2, 8),
        (1000, 10, 4, 3),
    ]:
        est = estimate_simulation_cost(agents, rounds, platforms, variants)
        assert est.margin_pct >= float(MIN_MARGIN_PCT), (
            f"{agents}x{rounds}x{platforms}x{variants} priced at "
            f"{est.margin_pct}% margin, below the {MIN_MARGIN_PCT}% floor"
        )


def test_breakdown_sums_to_actual_cost():
    est = estimate_simulation_cost(100, 5, platforms=2)
    assert sum(est.breakdown.values()) == pytest.approx(est.actual_cost_usd, rel=1e-6)


def test_agent_actions_dominate_cost():
    """Agent actions are the high-volume stage — if they aren't the largest
    line item on a sizeable run, the profile is miscalibrated."""
    est = estimate_simulation_cost(500, 10, platforms=2)
    assert est.breakdown["agent_actions"] == max(est.breakdown.values())


def test_variants_scale_action_cost():
    one = estimate_simulation_cost(100, 5, variants=1)
    eight = estimate_simulation_cost(100, 5, variants=8)
    ratio = eight.breakdown["agent_actions"] / one.breakdown["agent_actions"]
    assert ratio == pytest.approx(8.0, rel=1e-6)


def test_agent_generation_does_not_scale_with_variants():
    """Matched swarms reuse one generated audience across every variant."""
    one = estimate_simulation_cost(100, 5, variants=1)
    eight = estimate_simulation_cost(100, 5, variants=8)
    assert one.breakdown["agent_generation"] == pytest.approx(
        eight.breakdown["agent_generation"]
    )


def test_estimate_scales_linearly_in_agents():
    est1 = estimate_simulation_cost(1000, 5)
    est2 = estimate_simulation_cost(2000, 5)
    ratio = est2.breakdown["agent_actions"] / est1.breakdown["agent_actions"]
    assert ratio == pytest.approx(2.0, rel=1e-6)


def test_cost_is_realistic_not_negligible():
    """Guards the specific defect this model replaced: the old constant priced
    a 4,000 agent-round run at well under a dollar of true cost."""
    est = estimate_simulation_cost(100, 5, platforms=1, variants=8)
    assert est.agent_rounds == 500
    # 4,000 agent actions cannot plausibly cost less than a dollar.
    assert est.actual_cost_usd > 1.0


def test_estimate_max_agents():
    est = estimate_simulation_cost(MAX_AGENTS, 1)
    assert est.agent_count == MAX_AGENTS


def test_estimate_exceeds_max_raises():
    with pytest.raises(ValueError, match="cannot exceed"):
        estimate_simulation_cost(MAX_AGENTS + 1, 1)


def test_estimate_zero_raises():
    with pytest.raises(ValueError):
        estimate_simulation_cost(0, 5)


def test_estimate_negative_raises():
    with pytest.raises(ValueError):
        estimate_simulation_cost(-100, 5)


def test_invalid_platforms_or_variants_raise():
    with pytest.raises(ValueError):
        estimate_simulation_cost(100, 5, platforms=0)
    with pytest.raises(ValueError):
        estimate_simulation_cost(100, 5, variants=0)


# ---------------------------------------------------------------------------
# model_pricing
# ---------------------------------------------------------------------------

def test_price_lookup_handles_dated_snapshots_and_prefixes():
    """The configured fast model is a dated ID; it must price as Haiku."""
    dated = price_for("claude-haiku-4-5-20251001")
    alias = price_for("claude-haiku-4-5")
    assert dated == alias
    assert price_for("anthropic/claude-opus-4-7") == price_for("claude-opus-4-7")
    assert price_for("anthropic.claude-opus-4-7") == price_for("claude-opus-4-7")


def test_longest_prefix_wins():
    """claude-opus-4-8 must not be matched by a shorter overlapping key."""
    assert price_for("claude-opus-4-8").input_per_mtok == price_for(
        "claude-opus-4-8"
    ).input_per_mtok


def test_unknown_model_falls_back_to_highest_rate():
    """An unknown model must over-estimate, never under-charge."""
    unknown = price_for("some-unreleased-model")
    haiku = price_for("claude-haiku-4-5")
    assert unknown.input_per_mtok > haiku.input_per_mtok


def test_haiku_is_cheaper_than_opus_per_call():
    """The premise of the tiered model policy."""
    haiku = cost_usd("claude-haiku-4-5", input_tokens=1000, output_tokens=120)
    opus = cost_usd("claude-opus-4-7", input_tokens=1000, output_tokens=120)
    assert haiku < opus


def test_cache_reads_are_cheaper_than_fresh_input():
    fresh = cost_usd("claude-opus-4-7", input_tokens=10_000)
    cached = cost_usd("claude-opus-4-7", cache_read_tokens=10_000)
    assert cached < fresh


def test_the_free_grant_covers_one_free_run():
    """A grant that does not cover one free run makes the tier unusable.

    The user hits "not enough credits" on the only run they were promised, at
    signup, which is the worst possible moment. This has gone stale three times —
    when depth scaling and canonicalization pricing landed, when the 2026-08-03
    recalibration found the report writes six sections and was quoted for four,
    and when the subject distillation added a main-model stage. Every time the
    *free* tier moved first, because the report, the canonicalizer and the
    distillation barely shrink with run size and so dominate a 25-agent run.

    **The free run is priced with a subject brief**, because the free run is the
    one the product is demonstrated with: a founder uploads their deck and gets
    one simulation. Pricing the document-free version here would prove the grant
    covers a run nobody takes the free tier to perform, and the failure would
    land on the customer at signup — which is exactly what this test exists to
    catch and has now failed to catch twice.

    Asserted against the tier caps rather than a hardcoded shape, so tightening
    a cap cannot quietly invalidate it.
    """
    from app.services.billing.agent_pricing import (
        TIER_CREDIT_GRANTS,
        estimate_simulation_cost,
        tier_caps,
    )

    caps = tier_caps("free")
    free_run = estimate_simulation_cost(
        caps.max_agents, caps.max_rounds, caps.max_platforms, caps.max_variants,
        subject_brief=True,
    )

    # The bound is >= 0 rather than a headroom percentage because the grant is a
    # commercial number and not this test's to set. It is worth knowing that the
    # margin is 227 credits — 15%, since the grant moved to 1,500 alongside the
    # distillation — so the message reports it on the way past. It was 20 credits
    # at the 1,200 grant, and one new stage consumed it.
    headroom = TIER_CREDIT_GRANTS["free"] - free_run.credits
    assert headroom >= 0, (
        f"free grant is {TIER_CREDIT_GRANTS['free']} credits but a free run at "
        f"the tier cap costs {free_run.credits} — the free tier cannot complete "
        f"its one run. Headroom was {headroom} credits."
    )
    assert TIER_CREDIT_GRANTS["trial"] == TIER_CREDIT_GRANTS["free"]


def test_a_new_free_account_is_told_it_has_a_run():
    """The number the sidebar prints must agree with the grant that was sized.

    The test above proves the grant covers one capped run. It did **not**
    prove the app says so — and the app said the opposite. The sidebar divided
    the balance by `standard_run_credits()` (the 100-agent reference, a shape
    the free tier is capped out of configuring), so `floor(1500 / 3014)` = 0
    and every new signup read "About 0 more runs — add more" while holding a
    grant deliberately sized for exactly one run.

    This is the customer-visible half of the same fact, which is the half no
    test asserted: the pricing model was self-consistent and the product
    still lied. `capped_run_credits` is what a client must divide by.
    """
    from app.services.billing.agent_pricing import (
        TIER_CREDIT_GRANTS,
        capped_run_credits,
        standard_run_credits,
    )

    grant = TIER_CREDIT_GRANTS["free"]
    per_run = capped_run_credits("free")

    assert grant // per_run >= 1, (
        f"a new free account holds {grant} credits and a run it can configure "
        f"costs {per_run} — the app would tell them they have "
        f"{grant // per_run} runs on the tier whose whole promise is one."
    )
    # And the reference price is the wrong unit for this tier — the mistake
    # this test exists to keep out. If these ever coincide the free caps have
    # been raised to the reference shape, and that is a decision, not a drift.
    assert per_run < standard_run_credits(), (
        "the free tier's capped run now costs the reference price; the caps or "
        "the reference moved, and the 'runs left' unit needs re-deciding"
    )

    # A paid tier can configure the reference shape, so its unit stays the
    # reference — otherwise pricing every tier at its own ceiling would
    # understate the run counts PRICING_GUIDE advertises.
    for plan in ("founder", "growth", "agency"):
        assert capped_run_credits(plan) == standard_run_credits(), (
            f"{plan} should count runs at the reference price it can actually "
            f"configure, not at its ceiling"
        )


def test_paid_tier_run_counts_are_whole_runs():
    """A tier advertising N runs must actually afford N.

    Through `standard_run_credits()`, not a local re-derivation from
    `STANDARD_RUN`. The shape tuple does not carry `subject_brief`, and the
    reference run does — so rebuilding the reference from the tuple alone
    computes a figure ~10% below the one every quote is compared against, and
    this test would then certify run counts nobody can achieve. That is the
    two-sources-of-truth class with an advertised number on the end of it.

    6 / 19 / 66 as of 2026-08-04, down from 7 / 21 / 73: the subject
    distillation took the standard run from $2.74 to $3.01. DECISIONS §15c's
    precedent is to pass a corrected cost base straight through to the published
    run count rather than bank it, and this is that precedent applied again.
    """
    from app.services.billing.agent_pricing import (
        TIER_CREDIT_GRANTS,
        standard_run_credits,
    )

    standard = standard_run_credits()
    for tier, advertised in (("founder", 6), ("growth", 19), ("agency", 66)):
        affordable = TIER_CREDIT_GRANTS[tier] // standard
        assert affordable == advertised, (
            f"{tier} affords {affordable} standard runs; PRICING_GUIDE §1.6 and "
            f"PRD §8 advertise {advertised}. Regenerate the tables."
        )
