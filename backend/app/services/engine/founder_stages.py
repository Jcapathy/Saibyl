# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# FounderStage            — the five stage ids, as a Literal
# StageSpec               — one stage's intake, defaults, metrics, template
# FOUNDER_STAGES          — dict[FounderStage, StageSpec]
# stage_spec(stage)       -> StageSpec | None
# ─────────────────────────────────────────────────────────
"""The five Founder-lens entry points (PRD §5, DECISIONS §8).

**This is the retention mechanism, not a UX nicety.** A validation tool is a
one-time purchase; a positioning system is a subscription. One general
"validate my product" flow gets used once and churns. Five stages are five
purchase occasions for the same account, and the answer legitimately changes
every time the founder ships a feature, changes pricing, rewrites the landing
page, or hears a new objection in a sales call.

A stage is data, not code. It declares what the founder is asked for, what the
audience defaults to, which questions the report must answer, and what a
run at this stage is *not* entitled to conclude. Everything that consumes a
stage — intake validation, the audience defaults in the Run Configurator, the
report's section plan — reads this registry, so adding a sixth stage is a dict
entry rather than a search for every `if stage ==` in the codebase.

**`cannot_conclude` is the load-bearing field.** A concept-validation run has
no product to react to, so it cannot measure adoption intent; a fundraise run
simulates how investors read a story, not whether they would invest. Stating
those limits in the same object that drives the report is the only way they
reliably reach the reader — a caveat that lives in a doc reaches nobody.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

FounderStage = Literal[
    "concept_validation",
    "pre_launch_positioning",
    "launch_gtm",
    "growth",
    "fundraise",
]

FOUNDER_STAGE_IDS: tuple[str, ...] = (
    "concept_validation",
    "pre_launch_positioning",
    "launch_gtm",
    "growth",
    "fundraise",
)


class StageSpec(BaseModel):
    """What one Founder-lens stage asks for and produces."""

    id: str
    label: str
    # One line, shown on the stage picker. What question this stage answers.
    question: str

    # What the founder is asked to upload or write. Advisory in the API —
    # a founder with only a deck should not be blocked from running — but shown
    # at intake, because a run against the wrong input produces a confidently
    # wrong answer, which is worse than no answer.
    expected_inputs: list[str] = Field(default_factory=list)

    # Audience defaults for the Run Configurator. The adversarial share is the
    # interesting one: it is 0 at concept validation, because there is no
    # product to defend against yet and an incumbent cohort would be arguing
    # with a problem statement, and highest at growth, where the buyer already
    # has something that works.
    default_adversarial_share: float = 0.0
    default_rounds: int = 5

    # The questions the report must answer at this stage, in priority order.
    # The report planner turns these into sections; they are not section titles.
    report_questions: list[str] = Field(default_factory=list)

    # What a run at this stage cannot support, stated in the report. See the
    # module docstring — this is the field that keeps the output honest.
    cannot_conclude: list[str] = Field(default_factory=list)


FOUNDER_STAGES: dict[str, StageSpec] = {
    "concept_validation": StageSpec(
        id="concept_validation",
        label="Concept validation",
        question="Does this pain exist, who feels it most, and would they pay?",
        expected_inputs=[
            "Problem statement",
            "Target segment description",
            "Any early customer conversations",
        ],
        # No product exists to switch away from. An incumbent cohort here would
        # be arguing against a problem statement, which is not the objection a
        # founder needs at this stage — they need to know whether the pain is
        # real, and a swarm of defenders drowns that signal.
        default_adversarial_share=0.0,
        default_rounds=4,
        report_questions=[
            "Do agents recognise this pain unprompted, or only when named?",
            "Which cohort feels it most acutely, and how does that split?",
            "What do they do about it today, and what does that cost them?",
            "What would disqualify a solution before they tried it?",
            "Is there stated willingness to pay, and at what shape of price?",
        ],
        cannot_conclude=[
            "Adoption intent — there is no product for an agent to adopt.",
            "Pricing level. Stated willingness to pay from a synthetic audience "
            "with no product in front of it indicates direction, not a number.",
        ],
    ),
    "pre_launch_positioning": StageSpec(
        id="pre_launch_positioning",
        label="Pre-launch positioning",
        question="What will they object to, and where does the pitch lose them?",
        expected_inputs=["PRD or product spec", "Landing page copy", "Pitch deck"],
        # The stage the inoculation loop was designed for: real positioning,
        # real switching cost, and time to fix it before launch.
        default_adversarial_share=0.3,
        default_rounds=5,
        report_questions=[
            "What are the load-bearing objections, ranked by reach x intensity x cohort spread?",
            "Which claims in the material are believed, and which are read as marketing?",
            "Where does the pitch lose each cohort, and at which sentence?",
            "What credibility does the material assert but not evidence?",
            "Which objections originate with incumbent-aligned agents and then spread?",
        ],
        cannot_conclude=[
            "Conversion rate. The run measures reception and objection, not funnel behaviour.",
        ],
    ),
    "launch_gtm": StageSpec(
        id="launch_gtm",
        label="Launch / GTM",
        question="Which message lands on which channel, and what pre-positioning is needed?",
        expected_inputs=["Launch copy", "Channel plan", "Any launch assets"],
        default_adversarial_share=0.35,
        default_rounds=5,
        report_questions=[
            "How does reception differ by platform, and is the difference larger than the bands?",
            "Which message-channel pairings work, and which are mismatched?",
            "Which objections arrive in round 1 and set the tone for later rounds?",
            "What should be pre-positioned before launch rather than answered after it?",
        ],
        cannot_conclude=[
            "Reach or impressions. The swarm models reaction, not distribution.",
            "Which channel to spend on. Message-channel fit is not channel economics.",
        ],
    ),
    "growth": StageSpec(
        id="growth",
        label="Growth",
        question="How do existing and prospective users react to this change?",
        expected_inputs=[
            "Pricing page or the change to it",
            "Feature announcement",
            "Churn signals or support themes",
        ],
        # The highest default. At growth the buyer already has something that
        # works — often the product itself — so the sunk-cost and
        # already-solved-it arguments are the real ones.
        default_adversarial_share=0.4,
        default_rounds=6,
        report_questions=[
            "How does the change land with users who already have a working setup?",
            "What is the pricing reaction, and which cohort carries it?",
            "What expansion resistance appears, and on what grounds?",
            "What churn narratives form, and do they spread beyond their originating cohort?",
        ],
        cannot_conclude=[
            "Actual churn or expansion rates. The run measures the narrative, "
            "not the behaviour that follows it.",
        ],
    ),
    "fundraise": StageSpec(
        id="fundraise",
        label="Fundraise",
        question="How do investors and press read this story, and what will they ask?",
        expected_inputs=["Pitch deck", "Narrative memo", "Any market sizing"],
        # Investors and journalists are professionally skeptical, but they are
        # not incumbent-aligned — the skepticism is about the story, not about
        # defending a tool they already sell.
        default_adversarial_share=0.2,
        default_rounds=5,
        report_questions=[
            "What does this audience believe the company does, in their own words?",
            "Which parts of the story are read as evidence and which as assertion?",
            "What questions recur, and which cohort asks them first?",
            "Where does the narrative lose credibility, and against what comparison?",
        ],
        cannot_conclude=[
            "Whether the round will be raised, or at what valuation.",
            "Any individual firm's view. The audience is synthetic and generic "
            "by construction; it models how the story reads, not who reads it.",
        ],
    ),
}


def stage_spec(stage: str | None) -> StageSpec | None:
    """The spec for a stage id, or None for an unstaged run."""
    if not stage:
        return None
    return FOUNDER_STAGES.get(stage)
