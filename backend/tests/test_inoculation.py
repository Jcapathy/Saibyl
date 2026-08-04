"""The inoculation loop's verdict logic and its refusals.

The loop's whole value is that it can say "this asset did not work". A verdict
engine that only ever reports progress is worth less than nothing, because it
launders an LLM opinion through a measurement pipeline. So these tests are
mostly about the cases where the honest answer is *we cannot tell*.
"""
from __future__ import annotations

import pytest

from app.services.billing.agent_pricing import (
    estimate_inoculation_draft_cost,
    estimate_simulation_cost,
)
from app.services.engine.personas.icp_synthesizer import ProjectMaterial
from app.services.intelligence.inoculation import (
    _evidence_claims,
    _proportion_interval,
    _sourced_numbers,
    _verdict,
    asset_prompt_block,
)
from app.services.intelligence.inoculation_schema import ObjectionDelta, ObjectionMeasurement
from app.services.platforms.base_adapter import BasePlatformAdapter


def _measurement(agent_count: int, agents_active: int) -> ObjectionMeasurement:
    return ObjectionMeasurement(
        agent_count=agent_count,
        agents_active=agents_active,
        reach=_proportion_interval(agent_count, agents_active),
    )


# ---------------------------------------------------------------------------
# Proportion intervals
# ---------------------------------------------------------------------------

def test_zero_observed_is_not_certainty():
    """"No agent raised it in 40" does not exclude a 7% true rate.

    Claiming an objection is dead on zero observations is the most tempting
    overstatement in the whole loop, so the interval carries the rule-of-three
    bound instead of collapsing to zero.
    """
    interval = _proportion_interval(0, 40)

    assert interval.mean == 0.0
    assert interval.upper == pytest.approx(0.075)
    assert interval.n == 40


def test_zero_of_a_tiny_swarm_has_a_very_wide_upper_bound():
    assert _proportion_interval(0, 8).upper == pytest.approx(0.375)


def test_no_active_agents_yields_an_empty_interval():
    interval = _proportion_interval(0, 0)
    assert interval.n == 0
    assert interval.upper == 0.0


def test_proportion_interval_is_centred_on_the_share():
    interval = _proportion_interval(20, 100)
    assert interval.mean == pytest.approx(0.2)
    assert interval.lower < 0.2 < interval.upper


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------

def test_an_objection_that_vanished_is_only_dead_when_the_interval_supports_it():
    before = _measurement(12, 40)
    after = _measurement(0, 40)

    assert _verdict(before, after, significant=True) == "died"
    # Same disappearance, unresolvable swarm: not a result.
    assert _verdict(before, after, significant=False) == "unresolved"


def test_a_measurable_drop_is_shrank():
    assert _verdict(_measurement(20, 40), _measurement(4, 40), True) == "shrank"


def test_a_measurable_rise_is_grew():
    """An asset can draw attention to the objection it answers."""
    assert _verdict(_measurement(4, 40), _measurement(20, 40), True) == "grew"


def test_a_move_inside_the_bands_is_unresolved_not_progress():
    """34% to 31% is not evidence of anything, and must never read as if it is."""
    verdict = _verdict(_measurement(14, 40), _measurement(12, 40), significant=False)
    assert verdict == "unresolved"


def test_no_movement_at_all_is_unchanged():
    assert _verdict(_measurement(10, 40), _measurement(10, 40), False) == "unchanged"


def test_an_objection_absent_before_and_present_after_emerged():
    """An asset that answers one objection and raises two is a result the
    founder needs before they publish it."""
    assert _verdict(_measurement(0, 40), _measurement(9, 40), True) == "emerged"


# ---------------------------------------------------------------------------
# Effectiveness
# ---------------------------------------------------------------------------

def _delta(verdict: str, significant: bool) -> ObjectionDelta:
    return ObjectionDelta(
        objection_key="k",
        label="Objection",
        before=_measurement(20, 40),
        after=_measurement(4, 40),
        significant=significant,
        verdict=verdict,  # type: ignore[arg-type]
        asset_ids=["asset-1"],
    )


def test_only_a_significant_shrink_or_death_counts_as_effective():
    assert _delta("died", True).effective is True
    assert _delta("shrank", True).effective is True


def test_unresolved_never_counts_as_effective():
    """The number the product is sold on has to be one a sceptic accepts."""
    assert _delta("unresolved", False).effective is False
    assert _delta("unchanged", False).effective is False


def test_a_significant_rise_is_not_effective():
    assert _delta("grew", True).effective is False


def test_a_shrink_without_separated_intervals_is_not_effective():
    assert _delta("shrank", False).effective is False


# ---------------------------------------------------------------------------
# Fabricated evidence
#
# Found on the first live run: asked to answer "there is no proof synthetic
# feedback predicts real behavior", the drafter invented the proof and put it in
# three assets. This is Phase 1's bug #5 one level over — the report was stopped
# from writing its own numbers, and the asset drafter never was.
# ---------------------------------------------------------------------------

# Verbatim from the live run. Kept as the fixture because a paraphrase would
# drift away from the thing that actually happened.
_FABRICATED = (
    "In our 14-case internal dataset, the rank-order of objections matched "
    "real-user feedback in 11 cases (Spearman's ρ = 0.74)."
)

_MATERIAL = ProjectMaterial(
    own="Founder $99/mo, Growth $299/mo. A standard run is 100 agents, 5 rounds, "
        "2 platforms and costs 2,265 credits."
)


def test_a_fabricated_correlation_is_caught():
    claims = _evidence_claims(_FABRICATED, _sourced_numbers(_MATERIAL))
    assert claims, "the invented Spearman's rho was not flagged"


def test_prices_the_material_states_are_not_flagged():
    """$99/mo is a price the team sets, not a research finding."""
    body = "Our pricing is $99/mo because a standard run costs us real compute."
    assert _evidence_claims(body, _sourced_numbers(_MATERIAL)) == []


def test_a_number_in_the_material_survives_evidence_language():
    """A figure the material states is sourced, even in an evidential sentence.

    Both halves have to be true for this to test anything: "benchmark" is in
    `_EVIDENCE_WORDS`, and 100 is in the uploaded material. A sentence missing
    either would pass without exercising the exemption at all.
    """
    body = "Our benchmark is the standard run of 100 agents."
    assert "benchmark" in body.lower()
    assert "100" in _sourced_numbers(_MATERIAL)
    assert _evidence_claims(body, _sourced_numbers(_MATERIAL)) == []


def test_an_invented_customer_count_is_caught():
    body = "Across 412 customers, retention held at 94%."
    assert _evidence_claims(body, _sourced_numbers(_MATERIAL))


def test_copy_with_no_numbers_passes():
    body = (
        "We have not yet run a controlled study comparing our output to real "
        "outcomes. Here is the study we intend to run, and when."
    )
    assert _evidence_claims(body, _sourced_numbers(_MATERIAL)) == []


def test_a_number_without_evidence_language_passes():
    """Narrow by design — only figures wearing the clothes of a finding."""
    body = "Setup takes about 15 minutes and the first run completes in 20."
    assert _evidence_claims(body, _sourced_numbers(_MATERIAL)) == []


def test_sourced_numbers_reads_every_material_bucket():
    material = ProjectMaterial(own="a 12", competitor="b 34", market="c 56")
    assert {"12", "34", "56"} <= _sourced_numbers(material)


# ---------------------------------------------------------------------------
# Pre-positioning
# ---------------------------------------------------------------------------

class _Adapter(BasePlatformAdapter):
    """Minimal concrete adapter — the base class is abstract."""

    platform_id = "test"

    async def initialize(self, config: dict, agents: list) -> None:  # pragma: no cover
        self.set_topic(config)

    async def run_round(self, round_number: int):  # pragma: no cover
        yield  # type: ignore[misc]

    async def get_feed(self, agent_username: str):  # pragma: no cover
        return []

    async def post(self, agent_username: str, content: str, metadata=None):  # pragma: no cover
        raise NotImplementedError

    async def comment(self, agent_username: str, post_id: str, content: str):  # pragma: no cover
        raise NotImplementedError

    async def react(self, agent_username: str, post_id: str, reaction):  # pragma: no cover
        raise NotImplementedError

    def get_state_snapshot(self) -> dict:  # pragma: no cover
        return {}


def test_asset_block_is_empty_for_an_ordinary_run():
    assert asset_prompt_block([]) == ""


def test_asset_block_presents_material_as_published_not_posted():
    block = asset_prompt_block([
        {
            "title": "Why we price per seat",
            "asset_type": "pricing_rationale",
            "body": "Our pricing follows the value a team gets, not its headcount.",
            "objection_key": "price-too-high",
        }
    ])

    assert "published this material alongside the subject" in block
    assert "Why we price per seat" in block
    assert "pricing rationale" in block


def test_asset_body_is_truncated_in_the_prompt():
    """A 4,000-character page in every action prompt multiplies the run's
    largest cost line, and an agent reacts to the first paragraph anyway."""
    block = asset_prompt_block([
        {
            "title": "Security",
            "asset_type": "security_page",
            "body": "x" * 5000,
            "objection_key": "security",
        }
    ])

    assert len(block) < 1200


def test_assets_reach_agents_through_the_topic_block():
    """One hook on the base class, inherited by all twelve adapters.

    Adding it to twelve `initialize` implementations would be twelve chances to
    miss one, and a missed adapter means a re-simulation whose agents never saw
    the asset — which would report as "the asset did not work".
    """
    adapter = _Adapter()
    adapter.set_topic({
        "prediction_goal": "Our new pricing",
        "pre_positioned": "The team has published this material...\n\n",
    })

    block = adapter.topic_block()

    assert "Our new pricing" in block
    assert "The team has published this material" in block


def test_an_ordinary_run_topic_block_is_unchanged():
    adapter = _Adapter()
    adapter.set_topic({"prediction_goal": "Our new pricing"})

    assert adapter.topic_block() == "The conversation is about: Our new pricing\n\n"


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------

def test_a_resimulation_is_not_charged_for_agents_it_never_generates():
    normal = estimate_simulation_cost(100, 5, 2, 1, "standard")
    reused = estimate_simulation_cost(100, 5, 2, 1, "standard", reuse_agents=True)

    assert reused.breakdown["agent_generation"] == 0.0
    assert normal.breakdown["agent_generation"] > 0.0
    assert reused.actual_cost_usd < normal.actual_cost_usd


def test_reuse_changes_generation_and_canonicalization_and_nothing_else():
    """Two stages differ for a re-simulation, and the ledger says which two.

    This test previously asserted that *only* generation moved. That was wrong
    in the expensive direction: a re-simulation's clustering call carries the
    parent's objections as priors, and the same run measured 3,162 output tokens
    without them against 13,955 with them.
    """
    normal = estimate_simulation_cost(100, 5, 2, 1, "standard")
    reused = estimate_simulation_cost(100, 5, 2, 1, "standard", reuse_agents=True)

    for stage in ("agent_actions", "event_measurement", "report"):
        assert reused.breakdown[stage] == normal.breakdown[stage]
    assert reused.breakdown["agent_generation"] == 0.0
    assert (
        reused.breakdown["objection_canonicalization"]
        > normal.breakdown["objection_canonicalization"]
    )


def test_pre_positioned_assets_are_charged_on_every_action():
    """An asset rides in `topic_block()`, so it is re-sent with every prompt.

    Measured on the parent/child pair `f980fe0d` / `fa28d899` — same agents,
    same platforms, six assets apart — at 312 against 1,654 input tokens per
    action. Charging assets as a one-off would under-quote the largest stage of
    the run by more than a factor of two.
    """
    without = estimate_simulation_cost(96, 5, 2, 1, "standard", reuse_agents=True)
    with_six = estimate_simulation_cost(
        96, 5, 2, 1, "standard", reuse_agents=True, inoculation_assets=6
    )

    assert with_six.breakdown["agent_actions"] > without.breakdown["agent_actions"] * 1.5
    # Only the action stage moves — assets are not sent to the classifier or
    # the report writer.
    for stage in ("agent_generation", "event_measurement", "objection_canonicalization", "report"):
        assert with_six.breakdown[stage] == without.breakdown[stage]


def test_the_asset_surcharge_scales_with_the_number_of_assets():
    def actions(n: int) -> float:
        return estimate_simulation_cost(
            96, 5, 2, 1, "standard", reuse_agents=True, inoculation_assets=n
        ).breakdown["agent_actions"]

    assert actions(0) < actions(1) < actions(6) < actions(12)


def test_a_negative_asset_count_is_rejected():
    with pytest.raises(ValueError):
        estimate_simulation_cost(96, 5, 2, 1, "standard", inoculation_assets=-1)


def test_the_measured_loop_is_quoted_above_what_it_cost():
    """The margin floor, checked against the one live loop we have bills for.

    From `llm_usage`, excluding the separately-quoted drafting pass and counting
    one clustering call per run: `f980fe0d` cost **$2.307** and `fa28d899`
    **$2.553**. A quote below either figure is a run served under the margin the
    whole model exists to hold — and the child was the one that slipped, because
    it was quoted as a cheaper version of its parent when it is a more expensive
    one.

    (The child's ledger total reads $2.660 because it was re-clustered after the
    key-carryover fix. That second call is a repair, not what the run costs.)
    """
    parent = estimate_simulation_cost(96, 5, 2, 1, "standard")
    child = estimate_simulation_cost(
        96, 5, 2, 1, "standard", reuse_agents=True, inoculation_assets=6
    )

    assert parent.actual_cost_usd >= 2.307
    # Above the as-billed total too, not just the clean one.
    assert child.actual_cost_usd >= 2.660
    # And the direction is the measured one: an asset-carrying re-simulation
    # costs *more* than its parent, not less. The saving on agent generation is
    # real and smaller than the surcharge on actions.
    assert child.actual_cost_usd > parent.actual_cost_usd


def test_asset_drafting_is_priced_as_its_own_stage():
    estimate = estimate_inoculation_draft_cost()

    assert estimate.stage == "inoculation_draft"
    assert estimate.credits > 0
    assert estimate.margin_pct >= 70.0


def test_drafting_costs_a_fraction_of_a_standard_run():
    assert estimate_inoculation_draft_cost().standard_run_equivalents < 0.25
