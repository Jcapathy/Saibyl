"""Tests for credits, report depth scaling, and quote signing.

The recurring failure mode in pricing code is silent under-charging, so these
assert direction — cheaper runs cost less, rounding favours the seller, a
tampered quote fails — rather than pinning exact dollar figures that would have
to be edited every time the token profiles are recalibrated.
"""
from __future__ import annotations

import pytest

from app.services.billing.agent_pricing import (
    CREDITS_PER_USD,
    MIN_MARGIN_PCT,
    STANDARD_RUN,
    credits_for,
    estimate_simulation_cost,
    report_section_count,
    tier_caps,
    tier_grant,
)
from app.services.billing.run_quote import _canonical, _sign

# ── Credits ──────────────────────────────────────────────

def test_one_credit_is_a_tenth_of_a_cent():
    assert credits_for(1.0) == CREDITS_PER_USD


def test_credits_round_up_never_down():
    """A run costing a fraction of a credit more than it charges is a loss."""
    assert credits_for(0.0001) == 1
    assert credits_for(0.00101) == 2


def test_zero_cost_is_zero_credits():
    assert credits_for(0) == 0


# ── Report depth scaling ─────────────────────────────────

def test_small_runs_get_the_minimum_sections():
    """The V1 floor of 4 sections cost a 25-agent free run $1.07 of its $1.27."""
    free_run_events = int(25 * 3 * 2 * 0.8)  # 25 agents, 3 rounds, 2 platforms
    assert report_section_count(free_run_events) == 2


def test_section_count_scales_up_with_run_size():
    standard = report_section_count(int(100 * 5 * 2 * 0.8))
    deep = report_section_count(int(250 * 10 * 4 * 0.8))
    assert 2 < standard < deep


def test_section_count_is_bounded_at_both_ends():
    assert report_section_count(0, "brief") >= 2
    assert report_section_count(10_000_000, "deep") <= 7


def test_depth_preset_shifts_section_count():
    events = int(100 * 5 * 2 * 0.8)
    assert (
        report_section_count(events, "brief")
        < report_section_count(events, "standard")
        < report_section_count(events, "deep")
    )


def test_free_run_is_far_cheaper_than_it_was_under_the_old_floor():
    """Regression guard on the §3.8 cost bug.

    The report must not dominate the cost of a run whose entire purpose is to
    be nearly free.
    """
    free = estimate_simulation_cost(25, 3, platforms=2)
    assert free.report_sections == 2
    assert free.breakdown["report"] < free.actual_cost_usd * 0.6


# ── Cost model ───────────────────────────────────────────

def test_agent_generation_does_not_scale_with_variants():
    """Matched swarms share one generated audience — that reuse is what makes
    the comparison valid, and the cost model has to reflect it."""
    one = estimate_simulation_cost(100, 5, variants=1)
    eight = estimate_simulation_cost(100, 5, variants=8)
    assert one.breakdown["agent_generation"] == eight.breakdown["agent_generation"]
    assert eight.breakdown["agent_actions"] > one.breakdown["agent_actions"]


def test_every_quote_holds_the_margin_floor():
    for shape in [(25, 3, 2, 1), (100, 5, 2, 1), (100, 5, 1, 8), (250, 10, 4, 1)]:
        est = estimate_simulation_cost(*shape)
        assert est.margin_pct >= float(MIN_MARGIN_PCT)


def test_credits_track_measured_cost_not_retail_price():
    """Credits ration compute, so they are denominated in COGS."""
    est = estimate_simulation_cost(100, 5, platforms=2)
    assert est.credits == credits_for(est.actual_cost_usd)


def test_standard_run_equivalents_are_one_for_the_standard_run():
    """The reference run carries a subject brief.

    That is a property of the reference and not of the shape tuple, because
    `STANDARD_RUN` describes what a customer configures — agents, rounds,
    platforms, variants — and whether the project has uploaded material is not
    one of those. Since 2026-08-04 the Founder lens is sold on that material, so
    the run *with* it is the reference and the document-free one is the
    exception. See `_standard_run_credits`.
    """
    est = estimate_simulation_cost(*STANDARD_RUN, subject_brief=True)
    assert est.standard_run_equivalents == pytest.approx(1.0, abs=0.02)


def test_a_document_free_run_is_worth_less_than_a_standard_run():
    """And is quoted for less, rather than being charged for a brief it will
    never send. A run with nothing to distil pays for no distillation."""
    est = estimate_simulation_cost(*STANDARD_RUN)
    assert est.standard_run_equivalents < 1.0
    assert est.breakdown["subject_distillation"] == 0.0


def test_a_bigger_run_is_worth_more_standard_runs():
    big = estimate_simulation_cost(150, 8, platforms=3, variants=4)
    assert big.standard_run_equivalents > 1.0


def test_invalid_depth_is_rejected():
    with pytest.raises(ValueError):
        estimate_simulation_cost(100, 5, depth="exhaustive")


# ── Tiers ────────────────────────────────────────────────

def test_grants_rise_with_tier():
    assert tier_grant("free") < tier_grant("founder") < tier_grant("growth") < tier_grant("agency")


def test_v1_plan_names_still_resolve():
    """The Stripe tier migration is separate work; the code must not break
    for orgs still carrying starter/pro/enterprise."""
    assert tier_grant("starter") == tier_grant("founder")
    assert tier_caps("pro").max_agents == tier_caps("growth").max_agents


def test_unknown_plan_falls_back_to_the_entry_tier():
    assert tier_grant("something-else") == tier_grant("starter")


def test_free_tier_caps_match_the_free_run_definition():
    caps = tier_caps("free")
    assert (caps.max_agents, caps.max_rounds, caps.max_platforms) == (25, 3, 2)


# ── Quote signing ────────────────────────────────────────

def _payload(**overrides):
    fields = {
        "quote_id": "q-1",
        "org_id": "org-1",
        "agent_count": 100,
        "rounds": 5,
        "platforms": 2,
        "variants": 1,
        "depth": "standard",
        "credits": 3230,
        "expires_at": "2026-08-02T12:00:00+00:00",
    }
    fields.update(overrides)
    return _canonical(**fields)


def test_signature_is_stable_for_identical_input():
    assert _sign(_payload()) == _sign(_payload())


def test_raising_the_agent_count_invalidates_the_signature():
    assert _sign(_payload()) != _sign(_payload(agent_count=250))


def test_lowering_the_credit_price_invalidates_the_signature():
    assert _sign(_payload()) != _sign(_payload(credits=1))


def test_extending_the_expiry_invalidates_the_signature():
    assert _sign(_payload()) != _sign(_payload(expires_at="2027-01-01T00:00:00+00:00"))


def test_a_quote_cannot_be_replayed_against_another_org():
    assert _sign(_payload()) != _sign(_payload(org_id="org-2"))


# ── Variants: N-way matched swarms ───────────────────────

def test_the_variant_cap_never_runs_ahead_of_the_engine():
    """Guards a billing gap, not a feature.

    The cost model has always scaled agent-action cost with variants. Until
    Phase 3 nothing executed more than one arena, so a 4-variant quote charged
    4x for one arena's work — which is why this constant exists at all.

    It is now 8, and the engine builds one adapter instance per (platform,
    variant). The pairing is what matters: this asserts the runner actually
    branches on arena, so the constant cannot be raised again ahead of the code
    that earns it.
    """
    import inspect

    from app.services.billing.agent_pricing import MAX_RUNNABLE_VARIANTS
    from app.workers import simulation_tasks

    assert MAX_RUNNABLE_VARIANTS == 8

    source = inspect.getsource(simulation_tasks.run_simulation)
    assert "load_arenas" in source, "the runner must resolve arenas per variant"
    assert "(platform_id, arena.variant_key)" in source, (
        "adapters must be keyed on (platform, variant) — keying on platform "
        "alone puts every variant in one shared conversation"
    )


def test_each_arena_gets_its_own_adapter_instance():
    """Isolation is structural: adapters own their feed and their memory.

    `get_adapter` returning a shared object would put every variant in one
    conversation while still labelling the events differently — a scoreboard
    that looks fine and measures nothing.
    """
    from app.services.platforms.registry import get_adapter, load_all_adapters

    load_all_adapters()
    first, second = get_adapter("reddit"), get_adapter("reddit")
    assert first is not second


def test_no_tier_can_configure_more_variants_than_the_engine_runs():
    from app.services.billing.agent_pricing import MAX_RUNNABLE_VARIANTS

    for plan in ("free", "founder", "starter", "growth", "pro", "agency", "enterprise"):
        assert tier_caps(plan).max_variants <= MAX_RUNNABLE_VARIANTS


def test_tier_caps_still_differ_on_the_dimensions_that_do_work():
    """The clamp must not flatten the tier ladder everywhere."""
    assert tier_caps("free").max_agents < tier_caps("founder").max_agents
    assert tier_caps("founder").max_rounds < tier_caps("growth").max_rounds


def test_a_runnable_variant_count_is_quotable_and_more_is_refused():
    """The quote boundary tracks the engine, in both directions."""
    from app.services.billing.agent_pricing import MAX_RUNNABLE_VARIANTS
    from app.services.billing.run_quote import QuoteError, _validate_shape

    _validate_shape(100, 5, 2, 1)
    _validate_shape(100, 5, 2, MAX_RUNNABLE_VARIANTS)
    with pytest.raises(QuoteError):
        _validate_shape(100, 5, 2, MAX_RUNNABLE_VARIANTS + 1)


def test_cost_model_can_still_price_a_hypothetical_multi_variant_run():
    """The model stays pure — PRICING_GUIDE quotes an 8-variant shape.

    The refusal belongs at the boundaries that charge money, not in the
    estimator that the quoting CLI uses for planning.
    """
    eight = estimate_simulation_cost(100, 5, platforms=1, variants=8)
    assert eight.credits > estimate_simulation_cost(100, 5, platforms=1).credits


def test_quoted_depth_reaches_the_report_writer():
    """Depth is the one setting that changes cost without changing the run.

    `run_generate_report` defaults to evidence_depth="deep", so a run quoted at
    "standard" was written at deep depth — more Opus-written sections than the
    customer was priced for.
    """
    import inspect

    from app.workers import simulation_tasks

    source = inspect.getsource(simulation_tasks.run_simulation)
    assert "evidence_depth=evidence_depth" in source
    assert 'sim.get("depth")' in source


def test_pricing_depth_round_trips_through_react_depth():
    """brief/standard/deep must survive the trip and come back the same."""
    from app.services.intelligence.report_agent import ReACTConfig

    depth_map = {"brief": "shallow", "standard": "standard", "deep": "deep"}
    for pricing_depth, react_depth in depth_map.items():
        back = ReACTConfig(evidence_depth=react_depth).evidence_depth_preset()
        assert back == pricing_depth, f"{pricing_depth} -> {react_depth} -> {back}"
