"""ICP synthesis, pack compilation, and the adversarial grounding guardrail.

The guardrail tests are the point of this file. PRD §4 permits an
incumbent-aligned agent only when a competitor name came out of material the
user uploaded and marked as competitor material, and DECISIONS §7 says that
guardrail does not get relaxed to improve output quality. A rule stated only in
a document is a rule that erodes, so it is tested at the two layers that can
enforce it: the schema, and the builder that reads model output.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.services.engine.founder_stages import FOUNDER_STAGE_IDS, FOUNDER_STAGES, stage_spec
from app.services.engine.personas.icp_schema import (
    ADVERSARIAL_ROLES,
    AdversarialArchetype,
    Competitor,
    ICPArchetype,
    ICPProfile,
)
from app.services.engine.personas.icp_synthesizer import (
    ProjectMaterial,
    _build_profile,
    compile_pack,
    rebalance_adversarial,
)
from app.services.engine.personas.pack_loader import ICP_PACK_PREFIX, PersonaPack

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

COMPETITOR_DOC = "11111111-1111-1111-1111-111111111111"
OWN_DOC = "22222222-2222-2222-2222-222222222222"


def _material(competitor: bool = True) -> ProjectMaterial:
    return ProjectMaterial(
        own="Our product does X.",
        competitor="Datadog is an observability platform." if competitor else "",
        own_ids=[OWN_DOC],
        competitor_ids=[COMPETITOR_DOC] if competitor else [],
    )


def _model_output(**overrides) -> dict:
    data = {
        "name": "Observability buyers",
        "product_summary": "Tracing for teams already paying for something else.",
        "category": "observability",
        "competitors": [
            {
                "name": "Datadog",
                "positioning": "full-stack observability",
                "mentioned_in": [COMPETITOR_DOC],
            }
        ],
        "archetypes": [
            {
                "id": "platform-lead",
                "label": "Platform Lead",
                "weight": 0.6,
                "role": "Platform engineering lead",
                "seniority": "director",
                "budget_authority": "recommender",
                "incumbent_tooling": ["Datadog", "Grafana"],
                "switching_cost": "high",
                "evaluation_criteria": ["ingest cost", "query latency"],
                "skepticism_triggers": ["unpriced usage tiers"],
                "goals": ["cut observability spend"],
                "pains": ["cardinality bills"],
                "platforms": ["hacker_news"],
                "prior_pack_id": "enterprise-it-buyer",
                "prior_archetype_id": None,
                "disposition": -0.1,
            },
            {
                "id": "sre",
                "label": "SRE",
                "weight": 0.4,
                "role": "Site reliability engineer",
                "seniority": "ic",
                "budget_authority": "influencer",
                "incumbent_tooling": ["Grafana"],
                "switching_cost": "moderate",
                "evaluation_criteria": ["alert quality"],
                "skepticism_triggers": ["vendor benchmarks"],
                "goals": ["fewer pages"],
                "pains": ["noisy alerts"],
                "platforms": ["reddit"],
                "disposition": 0.1,
            },
        ],
        "adversarial": [
            {
                "id": "datadog-power-user",
                "label": "Datadog power user",
                "weight": 1.0,
                "role": "incumbent_power_user",
                "competitor_name": "Datadog",
                "grounded_in": [COMPETITOR_DOC],
                "core_argument": "We already have dashboards built on this.",
                "talking_points": ["migration cost", "team retraining"],
                "platforms": ["hacker_news"],
                "disposition": -0.5,
            }
        ],
        "gaps": ["The material never says who approves the spend."],
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# The grounding guardrail
# ---------------------------------------------------------------------------

def test_named_competitor_without_grounding_is_rejected_by_schema():
    with pytest.raises(ValidationError):
        AdversarialArchetype(
            id="x",
            label="Incumbent employee",
            role="incumbent_employee",
            competitor_name="Datadog",
            grounded_in=[],
        )


def test_named_competitor_with_grounding_is_accepted():
    archetype = AdversarialArchetype(
        id="x",
        label="Incumbent employee",
        role="incumbent_employee",
        competitor_name="Datadog",
        grounded_in=[COMPETITOR_DOC],
    )
    assert archetype.competitor_name == "Datadog"


def test_model_naming_competitor_with_no_uploaded_material_is_stripped_not_dropped():
    """No competitor material: the name goes, the cohort stays.

    Dropping the whole archetype would quietly remove the adversarial cohort
    from exactly the runs that have no competitor material — which is most
    early runs, and the ones where "we already have a process for this" is the
    objection that matters.
    """
    profile = _build_profile(_model_output(), _material(competitor=False), adversarial=True)

    assert len(profile.adversarial) == 1
    assert profile.adversarial[0].competitor_name is None
    assert profile.adversarial[0].grounded_in == []
    # The talking points survive; only the name was unlicensed.
    assert profile.adversarial[0].talking_points


def test_grounding_citation_must_be_a_competitor_document():
    """Citing the founder's own document does not license a competitor's name."""
    output = _model_output()
    output["adversarial"][0]["grounded_in"] = [OWN_DOC]

    profile = _build_profile(output, _material(competitor=True), adversarial=True)

    assert profile.adversarial[0].competitor_name is None


def test_competitor_named_without_source_document_is_not_grounded():
    output = _model_output()
    output["competitors"][0]["mentioned_in"] = []

    profile = _build_profile(output, _material(competitor=True), adversarial=True)

    assert profile.competitors[0].name == "Datadog"
    assert profile.competitors[0].is_grounded is False
    assert profile.named_competitors == []


def test_adversarial_disabled_produces_no_adversarial_archetypes():
    profile = _build_profile(_model_output(), _material(), adversarial=False)
    assert profile.adversarial == []


def test_unknown_adversarial_role_falls_back_to_category_skeptic():
    output = _model_output()
    output["adversarial"][0]["role"] = "disgruntled_person"

    profile = _build_profile(output, _material(), adversarial=True)

    assert profile.adversarial[0].role == "category_skeptic"
    assert profile.adversarial[0].role in ADVERSARIAL_ROLES


# ---------------------------------------------------------------------------
# Profile construction
# ---------------------------------------------------------------------------

def test_profile_requires_at_least_one_archetype():
    with pytest.raises(ValidationError):
        ICPProfile(name="empty", archetypes=[])


def test_build_profile_carries_gaps_rather_than_inventing_answers():
    profile = _build_profile(_model_output(), _material(), adversarial=True)
    assert profile.gaps == ["The material never says who approves the spend."]


def test_build_profile_slugs_ids_and_clamps_disposition():
    output = _model_output()
    output["archetypes"][0]["id"] = "Platform Lead!! "
    output["archetypes"][0]["disposition"] = 4.2

    profile = _build_profile(output, _material(), adversarial=True)

    assert profile.archetypes[0].id == "platform-lead"
    assert profile.archetypes[0].disposition == 1.0


def test_archetype_without_a_label_is_skipped():
    output = _model_output()
    output["archetypes"].append({"id": "ghost", "weight": 0.1})

    profile = _build_profile(output, _material(), adversarial=True)

    assert [a.id for a in profile.archetypes] == ["platform-lead", "sre"]


# ---------------------------------------------------------------------------
# Compilation to a PersonaPack
# ---------------------------------------------------------------------------

def _profile() -> ICPProfile:
    return _build_profile(_model_output(), _material(), adversarial=True)


def test_compiled_pack_validates_as_a_persona_pack():
    pack = compile_pack(_profile(), f"{ICP_PACK_PREFIX}abc", ["hacker_news"], 0.3)
    # Round-trips through the engine's own model — this is what get_pack returns.
    assert PersonaPack.model_validate(pack.model_dump()) == pack


def test_compiled_pack_carries_icp_context_into_the_archetype():
    """The ICP's value is in the context fields, so they must reach the engine.

    Without this, a synthesized ICP is a relabelled generic pack: agent
    generation would see a job title and no switching cost, which is the exact
    failure DECISIONS §3 rejected the pack library to avoid.
    """
    pack = compile_pack(_profile(), f"{ICP_PACK_PREFIX}abc", ["hacker_news"], 0.3)
    lead = next(a for a in pack.archetypes if a.id == "platform-lead")

    assert lead.context is not None
    assert lead.context.incumbent_tooling == ["Datadog", "Grafana"]
    assert lead.context.switching_cost == "high"
    assert lead.context.skepticism_triggers == ["unpriced usage tiers"]


def test_compiled_pack_takes_psychometrics_from_the_named_prior():
    """Priors, not invention. The Big Five come from a built-in pack."""
    from app.services.engine.personas.pack_loader import get_pack

    prior = get_pack("enterprise-it-buyer")
    heaviest = max(prior.archetypes, key=lambda a: a.weight)

    pack = compile_pack(_profile(), f"{ICP_PACK_PREFIX}abc", ["hacker_news"], 0.3)
    lead = next(a for a in pack.archetypes if a.id == "platform-lead")

    assert lead.personality.big5 == heaviest.personality.big5


def test_archetype_with_no_prior_gets_the_visible_fallback():
    pack = compile_pack(_profile(), f"{ICP_PACK_PREFIX}abc", ["reddit"], 0.0)
    sre = next(a for a in pack.archetypes if a.id == "sre")

    assert sre.demographics.age_range == [28, 52]


def test_adversarial_archetype_is_flagged_on_the_compiled_archetype():
    pack = compile_pack(_profile(), f"{ICP_PACK_PREFIX}abc", ["hacker_news"], 0.3)
    attacker = next(a for a in pack.archetypes if a.is_adversarial)

    assert attacker.adversarial_role == "incumbent_power_user"
    assert attacker.context is not None
    assert attacker.context.competitor_name == "Datadog"


# ---------------------------------------------------------------------------
# The adversarial share
# ---------------------------------------------------------------------------

def test_adversarial_share_is_expressed_as_weight():
    pack = compile_pack(_profile(), f"{ICP_PACK_PREFIX}abc", ["hacker_news"], 0.3)

    attacker_weight = sum(a.weight for a in pack.archetypes if a.is_adversarial)
    buyer_weight = sum(a.weight for a in pack.archetypes if not a.is_adversarial)

    assert attacker_weight == pytest.approx(0.3)
    assert buyer_weight == pytest.approx(0.7)


def test_buyer_weight_ratios_survive_rebalancing():
    """0.6/0.4 between buyers stays 0.6/0.4 of the buyer share."""
    pack = compile_pack(_profile(), f"{ICP_PACK_PREFIX}abc", ["hacker_news"], 0.4)

    lead = next(a for a in pack.archetypes if a.id == "platform-lead")
    sre = next(a for a in pack.archetypes if a.id == "sre")

    assert lead.weight / (lead.weight + sre.weight) == pytest.approx(0.6)


def test_zero_share_keeps_the_cohort_in_the_pack_at_negligible_weight():
    """The pack must not depend on the share of whichever run compiled it."""
    pack = compile_pack(_profile(), f"{ICP_PACK_PREFIX}abc", ["hacker_news"], 0.0)

    attackers = [a for a in pack.archetypes if a.is_adversarial]
    assert len(attackers) == 1
    assert attackers[0].weight < 0.001


def test_rebalance_at_prepare_time_overrides_the_compiled_share():
    """The run's configured share wins over the one synthesis was given."""
    pack = compile_pack(_profile(), f"{ICP_PACK_PREFIX}abc", ["hacker_news"], 0.1)
    rebalance_adversarial(pack.archetypes, 0.5)

    attacker_weight = sum(a.weight for a in pack.archetypes if a.is_adversarial)
    assert attacker_weight == pytest.approx(0.5)


def test_rebalance_is_a_noop_on_a_built_in_pack():
    from app.services.engine.personas.pack_loader import get_pack

    pack = get_pack("saas-buyer-smb")
    before = [a.weight for a in pack.archetypes]
    rebalance_adversarial(pack.archetypes, 0.4)

    assert [a.weight for a in pack.archetypes] == before


# ---------------------------------------------------------------------------
# Material bucketing
# ---------------------------------------------------------------------------

def test_material_reports_whether_competitor_material_exists():
    assert _material(competitor=True).has_competitor_material is True
    assert _material(competitor=False).has_competitor_material is False


def test_material_all_ids_covers_every_bucket():
    material = ProjectMaterial(
        own="a", competitor="b", market="c",
        own_ids=["1"], competitor_ids=["2"], market_ids=["3"],
    )
    assert material.all_ids == ["1", "2", "3"]
    assert material.is_empty is False


def test_empty_material_is_detected():
    assert ProjectMaterial().is_empty is True


# ---------------------------------------------------------------------------
# Stage registry
# ---------------------------------------------------------------------------

def test_every_stage_id_has_a_spec():
    assert set(FOUNDER_STAGES) == set(FOUNDER_STAGE_IDS)
    for stage_id, spec in FOUNDER_STAGES.items():
        assert spec.id == stage_id


def test_every_stage_states_what_it_cannot_conclude():
    """The honesty field. A stage with no stated limits is a stage that
    over-claims, and the report reads this list."""
    for spec in FOUNDER_STAGES.values():
        assert spec.cannot_conclude, f"{spec.id} states no limits"
        assert spec.report_questions, f"{spec.id} asks nothing"


def test_concept_validation_defaults_to_no_adversarial_cohort():
    """There is no product to switch away from yet."""
    assert FOUNDER_STAGES["concept_validation"].default_adversarial_share == 0.0


def test_growth_carries_the_highest_adversarial_default():
    """At growth the buyer already has something that works."""
    shares = {s.id: s.default_adversarial_share for s in FOUNDER_STAGES.values()}
    assert shares["growth"] == max(shares.values())


def test_stage_defaults_are_within_the_enforced_ceiling():
    for spec in FOUNDER_STAGES.values():
        assert 0.0 <= spec.default_adversarial_share <= 0.5


def test_stage_spec_returns_none_for_unstaged_runs():
    assert stage_spec(None) is None
    assert stage_spec("not_a_stage") is None
    assert stage_spec("fundraise") is FOUNDER_STAGES["fundraise"]


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------

def test_icp_synthesis_is_priced_as_its_own_stage():
    """Phase 1's bug #6 was a measured stage that was never priced."""
    from app.services.billing.agent_pricing import estimate_icp_synthesis_cost

    estimate = estimate_icp_synthesis_cost()

    assert estimate.stage == "icp_synthesis"
    assert estimate.actual_cost_usd > 0
    assert estimate.credits > 0
    assert estimate.margin_pct >= 70.0


def test_synthesis_credits_round_up():
    from app.services.billing.agent_pricing import (
        CREDITS_PER_USD,
        estimate_icp_synthesis_cost,
    )

    estimate = estimate_icp_synthesis_cost()
    assert estimate.credits >= estimate.actual_cost_usd * CREDITS_PER_USD


def test_synthesis_costs_a_fraction_of_a_standard_run():
    """One main-model call should not approach the cost of a whole run."""
    from app.services.billing.agent_pricing import estimate_icp_synthesis_cost

    assert estimate_icp_synthesis_cost().standard_run_equivalents < 0.25


# ---------------------------------------------------------------------------
# Competitor helper
# ---------------------------------------------------------------------------

def test_competitor_is_grounded_only_with_a_source_document():
    assert Competitor(name="X", mentioned_in=[COMPETITOR_DOC]).is_grounded is True
    assert Competitor(name="X").is_grounded is False


def test_icp_archetype_rejects_non_positive_weight():
    with pytest.raises(ValidationError):
        ICPArchetype(id="a", label="A", role="r", weight=0)
