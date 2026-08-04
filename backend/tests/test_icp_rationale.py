"""An archetype must be able to say why it is one of your buyers.

The audience-review surface shows a founder each synthesized buyer and asks
whether it looks right. **The target user has not heard the term ICP** — they
cannot judge an archetype from a job title and a switching-cost enum, and
`AudienceReview.tsx` correctly left the space for a reason empty rather than
invent filler for it.

`ICPArchetype.rationale` fills that space, and the test that matters is not that
it is populated but that it is *dropped when it says nothing*. A sentence that
paraphrases the role back at the founder looks exactly like the evidence they
were asked to judge and contains none — Phase 1's bug #5 and Phase 2's
fabricated statistic, one notch quieter: not an invented number, an invented
reason. An empty space is honest; a plausible sentence is not.

The field is optional with an empty default, so every profile stored before it
existed validates unchanged and `ICP_SCHEMA_VERSION` did **not** move. A bump
blanks the whole review surface until `frontend/src/lib/founder.ts`'s
`SUPPORTED_ICP_SCHEMA_VERSION` moves in the same commit.
"""
from __future__ import annotations

import pytest
import structlog

from app.services.engine.personas import icp_synthesizer
from app.services.engine.personas.icp_schema import (
    ICP_SCHEMA_VERSION,
    AdversarialArchetype,
    ICPArchetype,
    ICPProfile,
)
from app.services.engine.personas.icp_synthesizer import ProjectMaterial, _build_profile

COMPETITOR_DOC = "11111111-1111-1111-1111-111111111111"
OWN_DOC = "22222222-2222-2222-2222-222222222222"

_OWN_MATERIAL = (
    "Saibyl runs synthetic audience simulations. Pricing starts at $99 a month "
    "for a founder plan with 1,200 credits. Teams currently answer these "
    "questions by commissioning panel research, which takes six weeks and costs "
    "twelve thousand dollars per study. Our onboarding imports an existing "
    "positioning deck."
)
_COMPETITOR_MATERIAL = (
    "Remesh is a live-conversation research platform sold to enterprise insights "
    "teams on annual contracts."
)


def _material(competitor: bool = True) -> ProjectMaterial:
    return ProjectMaterial(
        own=_OWN_MATERIAL,
        competitor=_COMPETITOR_MATERIAL if competitor else "",
        own_ids=[OWN_DOC],
        competitor_ids=[COMPETITOR_DOC] if competitor else [],
    )


def _output(archetype_rationale: str = "", adversarial_rationale: str = "") -> dict:
    return {
        "name": "Research buyers",
        "product_summary": "Synthetic audiences for teams who cannot wait six weeks.",
        "category": "audience research",
        "competitors": [
            {
                "name": "Remesh",
                "positioning": "live-conversation research",
                "mentioned_in": [COMPETITOR_DOC],
            }
        ],
        "archetypes": [
            {
                "id": "insights-lead",
                "label": "Insights Lead",
                "weight": 1.0,
                "rationale": archetype_rationale,
                "role": "Consumer insights lead",
                "seniority": "director",
                "budget_authority": "approver",
                "incumbent_tooling": ["panel research"],
                "switching_cost": "moderate",
                "evaluation_criteria": ["speed"],
                "skepticism_triggers": ["synthetic respondents"],
                "goals": ["ship faster"],
                "pains": ["slow studies"],
                "platforms": ["hacker_news"],
            }
        ],
        "adversarial": [
            {
                "id": "remesh-advocate",
                "label": "Remesh advocate",
                "weight": 1.0,
                "rationale": adversarial_rationale,
                "role": "incumbent_power_user",
                "competitor_name": "Remesh",
                "grounded_in": [COMPETITOR_DOC],
                "core_argument": "Real respondents are the whole point.",
                "talking_points": ["panel quality"],
                "platforms": ["hacker_news"],
            }
        ],
        "gaps": [],
    }


def _events(logs) -> set[str]:
    return {entry["event"] for entry in logs}


@pytest.fixture(autouse=True)
def capturable_logger(monkeypatch):
    """Make `capture_logs` able to see this module's logger, in any test order.

    `setup_logging()` configures a **new** processors list and `create_app()`
    calls it every time; `capture_logs` mutates whichever list is current *in
    place*. With `cache_logger_on_first_use=True`, a module logger first used
    before the last `create_app()` stays bound to the previous list — it still
    logs, and `capture_logs` still returns `[]`, which is a log assertion that
    passes for the wrong reason.
    """
    monkeypatch.setattr(
        icp_synthesizer, "logger", structlog.get_logger(icp_synthesizer.__name__)
    )


# ---------------------------------------------------------------------------
# Old profiles must keep validating — this is why the version did not move
# ---------------------------------------------------------------------------

def test_a_profile_stored_before_the_field_existed_still_validates():
    stored = {
        "schema_version": 1,
        "name": "Legacy ICP",
        "archetypes": [{"id": "a", "label": "A", "role": "buyer"}],
    }
    profile = ICPProfile.model_validate(stored)

    assert profile.archetypes[0].rationale == ""


def test_the_icp_schema_version_did_not_move():
    """If this ever has to change, `frontend/src/lib/founder.ts`'s
    `SUPPORTED_ICP_SCHEMA_VERSION` must move in the same commit — the review
    surface renders nothing at all for an unrecognised version."""
    assert ICP_SCHEMA_VERSION == 1


def test_an_absent_rationale_is_empty_not_null():
    assert ICPArchetype(id="a", label="A", role="buyer").rationale == ""
    assert AdversarialArchetype(id="a", label="A", role="category_skeptic").rationale == ""


# ---------------------------------------------------------------------------
# Kept when it cites the material
# ---------------------------------------------------------------------------

def test_a_rationale_citing_the_material_is_kept_verbatim():
    text = (
        "Your material says teams answer this today with panel studies that take "
        "six weeks and cost twelve thousand dollars, so the person feeling that "
        "bill is the one who buys."
    )
    profile = _build_profile(_output(archetype_rationale=text), _material(), adversarial=True)

    assert profile.archetypes[0].rationale == text


def test_an_adversarial_rationale_can_cite_competitor_material():
    text = (
        "Your competitor upload describes Remesh as sold on annual contracts to "
        "enterprise insights teams, so someone mid-contract will argue against "
        "switching."
    )
    profile = _build_profile(
        _output(adversarial_rationale=text), _material(), adversarial=True
    )

    assert profile.adversarial[0].rationale == text


def test_whitespace_is_normalised_and_the_length_is_capped():
    text = "Your\n  pricing   page mentions onboarding an existing positioning deck. " + "x" * 500
    profile = _build_profile(_output(archetype_rationale=text), _material(), adversarial=True)

    kept = profile.archetypes[0].rationale
    assert len(kept) <= 320
    assert "\n" not in kept
    assert "  " not in kept


# ---------------------------------------------------------------------------
# Dropped when it restates the archetype
# ---------------------------------------------------------------------------

def test_a_rationale_that_paraphrases_the_role_is_dropped_and_reported():
    """The failure the empty space existed to avoid."""
    with structlog.testing.capture_logs() as logs:
        profile = _build_profile(
            _output(
                archetype_rationale=(
                    "A consumer insights lead who approves budget, uses panel "
                    "research today, and wants to ship faster."
                )
            ),
            _material(),
            adversarial=True,
        )

    assert profile.archetypes[0].rationale == ""
    assert "icp_rationale_dropped" in _events(logs)


def test_a_rationale_that_cites_nothing_at_all_is_dropped():
    with structlog.testing.capture_logs() as logs:
        profile = _build_profile(
            _output(archetype_rationale="This is clearly one of your most important buyers."),
            _material(),
            adversarial=True,
        )

    assert profile.archetypes[0].rationale == ""
    assert "icp_rationale_dropped" in _events(logs)


def test_a_rationale_about_material_that_was_not_uploaded_is_dropped():
    """No competitor material means no competitor-grounded reason.

    Same shape as the naming guardrail one field over: the model knows things
    about Remesh, and knowing is not grounding.
    """
    text = (
        "Remesh sells annual enterprise contracts, so their power users will "
        "resist."
    )
    with structlog.testing.capture_logs() as logs:
        profile = _build_profile(
            _output(adversarial_rationale=text), _material(competitor=False), adversarial=True
        )

    assert profile.adversarial[0].rationale == ""
    assert "icp_rationale_dropped" in _events(logs)


def test_an_empty_rationale_is_not_reported_as_a_drop():
    """"The model returned nothing" and "the model returned filler" are
    different observations and must not share one log line."""
    with structlog.testing.capture_logs() as logs:
        profile = _build_profile(_output(), _material(), adversarial=True)

    assert profile.archetypes[0].rationale == ""
    assert "icp_rationale_dropped" not in _events(logs)


def test_dropping_a_rationale_never_drops_the_archetype():
    """The archetype is the audience; the rationale is the explanation of it."""
    profile = _build_profile(
        _output(archetype_rationale="They are an important buyer for you."),
        _material(),
        adversarial=True,
    )

    assert [a.id for a in profile.archetypes] == ["insights-lead"]
    assert [a.id for a in profile.adversarial] == ["remesh-advocate"]


def test_a_founder_edited_rationale_round_trips_through_the_schema():
    """`PATCH /api/icp/{id}` replaces the profile whole and re-validates it."""
    profile = _build_profile(
        _output(archetype_rationale="Your pricing page starts at $99 a month."),
        _material(),
        adversarial=True,
    )
    profile.archetypes[0].rationale = "I wrote this myself."

    reloaded = ICPProfile.model_validate(profile.model_dump(mode="json"))
    assert reloaded.archetypes[0].rationale == "I wrote this myself."
