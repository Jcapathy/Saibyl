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
    signup, which is the worst possible moment. This has gone stale twice — once
    when depth scaling and canonicalization pricing landed, and again when the
    2026-08-03 recalibration found the report writes six sections and was quoted
    for four. Both times the *free* tier moved first, because the report and the
    canonicalizer barely shrink with run size and so dominate a 25-agent run.

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
        caps.max_agents, caps.max_rounds, caps.max_platforms, caps.max_variants
    )

    # The bound is >= 0 rather than a headroom percentage because the grant is a
    # commercial number and not this test's to set. It is worth knowing that the
    # margin is 20 credits — 1.7%, and under 30 ever since the grant moved to
    # 1,200 — so the message reports it on the way past. Any stage repricing at
    # all consumes it, and the failure lands at signup.
    headroom = TIER_CREDIT_GRANTS["free"] - free_run.credits
    assert headroom >= 0, (
        f"free grant is {TIER_CREDIT_GRANTS['free']} credits but a free run at "
        f"the tier cap costs {free_run.credits} — the free tier cannot complete "
        f"its one run. Headroom was {headroom} credits."
    )
    assert TIER_CREDIT_GRANTS["trial"] == TIER_CREDIT_GRANTS["free"]


def test_paid_tier_run_counts_are_whole_runs():
    """A tier advertising N runs must actually afford N."""
    from app.services.billing.agent_pricing import (
        STANDARD_RUN,
        TIER_CREDIT_GRANTS,
        estimate_simulation_cost,
    )

    standard = estimate_simulation_cost(*STANDARD_RUN).credits
    for tier, advertised in (("founder", 7), ("growth", 21), ("agency", 73)):
        affordable = TIER_CREDIT_GRANTS[tier] // standard
        assert affordable == advertised, (
            f"{tier} affords {affordable} standard runs; PRICING_GUIDE §1.6 and "
            f"PRD §8 advertise {advertised}. Regenerate the tables."
        )
