"""A category brief changes the page, or it is decoration.

The defect this closes: the revision generator had no idea what kind of
company it was designing for. It inherited the founder's existing design DNA
and polished it, so a generic page came back as a better-executed generic
page — and a clinical product and a payments product were designed by the same
instincts.

Two failure modes are guarded here, and the second is the one that would
actually ship:

1. The brief never reaches the prompt.
2. The brief is a stereotype. "Medical means blue and a stethoscope" is
   confidently wrong guidance, which is worse than none — it produces the
   generated look it was meant to prevent. So the briefs are asserted to be
   written as buyer arguments (who signs off, what they must believe, what
   the page must prove) rather than as house styles.
"""
from __future__ import annotations

import pytest

from app.services.website.verticals import (
    DEFAULT_VERTICAL,
    VERTICALS,
    brief_for,
    brief_section,
    classify_vertical,
)


@pytest.mark.parametrize(
    ("material", "expected"),
    [
        (
            "We help clinics manage prior authorization for patient care across "
            "health systems and EHR integrations",
            "health",
        ),
        (
            "Route payments and reconcile your ledger with automated KYC and "
            "settlement for treasury teams",
            "fintech",
        ),
        (
            "A CLI and SDK to deploy your API with observability and low latency "
            "on kubernetes",
            "devtools",
        ),
        (
            "Track your daily habit and wellness routine, a personal app for "
            "everyday fitness",
            "consumer",
        ),
        (
            "Connect buyers and sellers, browse listings from vendors, we take a "
            "commission per booking",
            "marketplace",
        ),
    ],
)
def test_the_founders_own_words_pick_the_category(material, expected):
    assert classify_vertical(material) == expected


@pytest.mark.parametrize(
    "material",
    [
        "",
        "We make software.",
        # One stray signal is not a category. "capital" appears in plenty of
        # copy that has nothing to do with finance.
        "A capital-efficient tool for teams",
    ],
)
def test_thin_evidence_refuses_rather_than_guessing(material):
    """A confidently wrong brief pushes a page toward conventions its buyer
    does not hold. Refusing costs a paragraph of generic advice; guessing
    costs the page."""
    assert classify_vertical(material) == DEFAULT_VERTICAL


def test_material_spanning_two_categories_refuses():
    """A health-payments product genuinely sits between two sets of
    conventions, and picking one by tiebreak would be arbitrary."""
    both = "patient clinical care for hospital billing with payments, ledger and settlement KYC"
    assert classify_vertical(both) == DEFAULT_VERTICAL


def test_a_category_brief_reaches_the_generation_prompt():
    """The wiring, not just the module."""
    from app.services.website import revise

    prompt = revise._generation_prompt(
        round_no=1,
        page_text="We help clinics manage patient care across health systems and EHR.",
        critique={"dimensions": [], "findings": []},
        dna=None,
        reference=None,
        previous_html=None,
    )

    assert "WHAT THIS CATEGORY DEMANDS" in prompt
    assert "Health and clinical software" in prompt
    # And the category's specific argument, not just its name.
    assert "compliance" in prompt.lower() or "audit" in prompt.lower()


def test_an_unclear_page_still_gets_a_prompt_without_a_category_claim():
    from app.services.website import revise

    prompt = revise._generation_prompt(
        round_no=1,
        page_text="We make software.",
        critique={"dimensions": [], "findings": []},
        dna=None,
        reference=None,
        previous_html=None,
    )

    assert "WHAT THIS CATEGORY DEMANDS" in prompt
    # Named as general rather than asserting a category nobody established.
    assert "General" in prompt
    for label in ("Health and clinical", "Financial products", "Developer tools"):
        assert label not in prompt


def test_briefs_are_buyer_arguments_and_not_house_styles():
    """The stereotype guard.

    Every brief must say who decides and what they must believe, and none may
    prescribe a literal colour or font — the moment this file starts naming
    hex values per industry it has become the lookup table it exists to avoid.
    """
    import re

    for vid, brief in VERTICALS.items():
        assert brief.buyer.strip(), f"{vid}: no buyer named"
        assert brief.must_believe.strip(), f"{vid}: nothing the buyer must believe"
        assert brief.evidence, f"{vid}: no evidence the page must carry"
        assert brief.red_flags, f"{vid}: nothing named as a warning sign"

        blob = " ".join(
            [brief.direction, brief.must_believe, *brief.evidence, *brief.red_flags]
        )
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", blob), (
            f"{vid}: a literal colour is prescribed; briefs describe pressures, "
            "not values"
        )
        assert not re.search(r"\b\d+\s*(px|pt|rem)\b", blob), (
            f"{vid}: a literal size is prescribed; briefs describe pressures, "
            "not values"
        )


def test_every_brief_forbids_inventing_the_evidence_it_asks_for():
    """The category asks for certifications and numbers. A page that claims a
    certification it does not hold is worse than one that omits it, so the
    prompt block must say so every time — including for `general`."""
    for vid in [*VERTICALS, DEFAULT_VERTICAL]:
        section = brief_section(vid)
        assert "placeholder" in section.lower()
        assert "invent" in section.lower()


def test_an_unknown_category_falls_back_rather_than_raising():
    brief = brief_for("no-such-category")
    assert brief.id == DEFAULT_VERTICAL
