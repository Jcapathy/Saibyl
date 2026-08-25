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


def test_the_free_grant_buys_any_one_entry_service():
    """The founder's rule, 2026-08-22: the grant buys ONE service of the
    founder's choosing — not one idea evaluation.

    The old 1,500 was sized against the capped idea evaluation alone (1,273)
    and could not buy a website check at 1,750. A founder who wanted to spend
    their one free thing on the flagship module was told they had insufficient
    credits, which is the opposite of a loss leader.

    Each of these must be affordable on the grant with nothing else bought.
    A new entry service priced above the grant fails here rather than at a
    stranger's signup.
    """
    from app.services.billing.agent_pricing import (
        TIER_CREDIT_GRANTS,
        answer_pack_credits,
        clearance_credits,
        free_run_credits,
        messaging_doc_credits,
        website_check_credits,
    )

    grant = TIER_CREDIT_GRANTS["free"]
    entry_services = {
        "idea evaluation": free_run_credits(),
        "answer pack": answer_pack_credits(),
        "messaging doc": messaging_doc_credits(),
        "website check": website_check_credits(),
        "USPTO QUICK": clearance_credits("QUICK"),
        "USPTO STANDARD": clearance_credits("STANDARD"),
    }

    unaffordable = {
        name: price for name, price in entry_services.items() if price > grant
    }
    assert not unaffordable, (
        f"the free grant is {grant:,} credits and cannot buy {unaffordable} — "
        f"a founder choosing that service is refused at signup"
    )


def test_the_leftover_is_too_small_to_buy_a_second_service():
    """The remainder is designed, not incidental.

    A balance that can do nothing is a better argument for topping up than a
    balance of zero, which reads as the trial simply being over. But it must
    genuinely buy nothing — a grant that stretched to two services would give
    away the second one and remove the reason to pay.
    """
    from app.services.billing.agent_pricing import (
        TIER_CREDIT_GRANTS,
        answer_pack_credits,
        free_run_credits,
        website_check_credits,
    )

    grant = TIER_CREDIT_GRANTS["free"]
    cheapest_paid = min(
        free_run_credits(), answer_pack_credits(), website_check_credits()
    )

    for name, price in (
        ("idea evaluation", free_run_credits()),
        ("website check", website_check_credits()),
        ("answer pack", answer_pack_credits()),
    ):
        leftover = grant - price
        assert leftover >= 0, f"{name} is not affordable on the grant"
        assert leftover < cheapest_paid, (
            f"after {name} the founder has {leftover:,} credits left, which "
            f"still buys something at {cheapest_paid:,} — the grant is giving "
            f"away a second service"
        )


def test_the_grant_stops_short_of_the_downstream_services():
    """The funnel, stated as a rule. The grant buys the diagnosis; the founder
    pays for the cure. A free website check leading to a paid revision is the
    path the pricing is built around, and it only exists while the revision
    stays out of reach of the grant."""
    from app.services.billing.agent_pricing import (
        TIER_CREDIT_GRANTS,
        capital_shortlist_credits,
        outbound_sequence_credits,
        website_revision_credits,
    )

    grant = TIER_CREDIT_GRANTS["free"]
    for name, price in (
        ("website revision", website_revision_credits()),
        ("capital shortlist", capital_shortlist_credits()),
        ("outbound sequence", outbound_sequence_credits()),
    ):
        assert price > grant, (
            f"{name} costs {price:,}, which the {grant:,} grant now covers — "
            f"the loss leader is giving away a downstream service"
        )


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
        FREE_RUN_SHAPE,
        TIER_CREDIT_GRANTS,
        estimate_simulation_cost,
    )

    # Priced from `FREE_RUN_SHAPE`, **not** from `tier_caps()`.
    #
    # It used to read the free tier's caps, which were the same object as the
    # free run's shape. Removing tiers separated them — the free run is a
    # product, the caps are an accident-stopper — and the first attempt at that
    # change left this test reading the ceiling, which priced the "free run" at
    # 65,107 credits against a 2,000 grant. The two concepts must never be read
    # through one name again.
    caps = FREE_RUN_SHAPE
    free_run = estimate_simulation_cost(
        caps.max_agents, caps.max_rounds, caps.max_platforms, caps.max_variants,
        subject_brief=True,
    )

    # The bound is >= 0 rather than a headroom percentage because the grant is a
    # commercial number and not this test's to set. The margin was 20 credits at
    # the 1,200 grant and one new stage consumed it; 227 at 1,500; and it is
    # wider again since the grant moved to 2,000 on 2026-08-22 to cover a
    # website check. The message reports it on the way past either way.
    headroom = TIER_CREDIT_GRANTS["free"] - free_run.credits
    assert headroom >= 0, (
        f"free grant is {TIER_CREDIT_GRANTS['free']} credits but a free run at "
        f"the tier cap costs {free_run.credits} — the free tier cannot complete "
        f"its one run. Headroom was {headroom} credits."
    )

def test_a_new_account_is_shown_the_free_run_as_affordable():
    """The customer-visible half of the grant being sized.

    The test above proves the grant covers the free run. It does not prove the
    *app says so*, and the app used to say the opposite: the sidebar divided
    the balance by the 100-agent reference price, so every new signup read
    "About 0 more runs — add more" while holding a grant sized for exactly one.

    That sentence no longer exists. The founder removed runs-remaining entirely
    on 2026-08-25 in favour of showing what a *specific* run costs, so the
    customer-visible fact to pin moved with it: `/billing/prices` must publish
    the free run at a price the grant covers, and must say it is covered.
    """
    from app.services.billing.agent_pricing import FREE_RUN_GRANT, free_run_credits

    per_run = free_run_credits()

    assert per_run <= FREE_RUN_GRANT, (
        f"the free run costs {per_run:,} against a {FREE_RUN_GRANT:,} grant, so "
        f"the prices screen would show a founder a shortfall on the one thing "
        f"they were promised for nothing"
    )


def test_no_runs_remaining_number_is_served_anywhere():
    """The sentence, and the two-branch function that fed it, are both gone.

    `capped_run_credits` existed for exactly one reader — "about N more runs" —
    and could only be honest by knowing the reader's tier. Tiers went, the
    sentence went, and this keeps them from coming back together: a divisor
    like it can only be reintroduced alongside an assumption about the run
    shape, which is the thing that was wrong every previous time.
    """
    import inspect

    from app.api import billing
    from app.services.billing import agent_pricing

    assert not hasattr(agent_pricing, "capped_run_credits"), (
        "capped_run_credits is back; it prices an assumed shape, and a quote "
        "against the founder's real configuration is what replaced it"
    )

    # The *served key*, not any mention of it. `/billing/credits` carries a
    # comment explaining why the field was removed, and that comment is worth
    # more than a grep that trips over it.
    served = inspect.getsource(billing.credit_balance)
    assert '"capped_run_credits"' not in served, (
        "the runs-remaining divisor is being served again"
    )
