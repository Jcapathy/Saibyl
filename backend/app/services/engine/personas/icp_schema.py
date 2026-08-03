# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# ICPProfile          — the editable object synthesis produces
# ICPArchetype        — one buyer/user archetype
# AdversarialArchetype — one incumbent-aligned archetype
# Competitor          — a competitor named in uploaded material
# ADVERSARIAL_ROLES, ICP_SCHEMA_VERSION
# ─────────────────────────────────────────────────────────
"""The shape of a synthesized ICP.

Two audiences read this object and they want different things, which is why it
is not simply a `PersonaPack`.

**The founder** reads role, budget authority, incumbent tooling, switching cost,
evaluation criteria and skepticism triggers, and corrects what is wrong.
DECISIONS_V2 §3 kept the structured form as the editing surface precisely so
that synthesis proposes and a human disposes — an ICP the founder cannot argue
with is an ICP they cannot trust.

**The engine** reads a `PersonaPack`: demographics, psychometrics, platform
preferences, behaviour traits. It has consumed packs since V1 and there is no
reason for it to learn a second audience format.

So the profile below is the founder's object, and `icp_synthesizer.compile_pack`
turns it into the engine's. The compile step is where the 16 built-in packs earn
their keep as *priors*: a synthesized archetype states what a B2B buyer cares
about, and the nearest built-in pack supplies the Big Five and posting cadence
that nobody should be asking a language model to invent per project.

**On the adversarial cohort.** `AdversarialArchetype.grounded_in` is not
documentation. A model asked about a named competitor will confabulate, so an
adversarial archetype may name a company only when that name came out of a
document the user uploaded and marked as competitor material — the guardrail in
PRD §4 that DECISIONS §7 explicitly forbids relaxing to improve output quality.
`grounded_in` carries the document ids that licensed the name, and an archetype
that names a competitor with an empty `grounded_in` is rejected at validation
rather than being caught in review.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

# Bumped when the profile's shape changes in a way a reader must know about.
ICP_SCHEMA_VERSION = 1

Seniority = Literal["ic", "manager", "director", "vp", "c_level", "founder"]
BudgetAuthority = Literal["none", "influencer", "recommender", "approver", "owner"]
SwitchingCost = Literal["low", "moderate", "high", "prohibitive"]

# PRD §4. Five roles, fixed rather than free-form: each maps to a distinct
# failure mode a founder has to answer, and a free-form list would drift into
# "person who dislikes the product", which is not a cohort.
ADVERSARIAL_ROLES: tuple[str, ...] = (
    # Works for the incumbent. Defends the category as it is sold today.
    "incumbent_employee",
    # Uses the incumbent daily and is good at it. Their skill is the switching
    # cost, and this is the objection buyers never say out loud.
    "incumbent_power_user",
    # Sells services around the incumbent. Their revenue is the switching cost.
    "sunk_cost_consultant",
    # Doubts the category, not the product. Survives any competitive win.
    "category_skeptic",
    # "You can do this with an open-source tool and a weekend." The most common
    # objection in developer-adjacent markets and the one pure-buyer swarms miss.
    "free_alternative_advocate",
)

AdversarialRole = Literal[
    "incumbent_employee",
    "incumbent_power_user",
    "sunk_cost_consultant",
    "category_skeptic",
    "free_alternative_advocate",
]


class Competitor(BaseModel):
    """A competitor named in material the user uploaded.

    `mentioned_in` is the licence to use the name. An entry with no source
    documents is not a competitor Saibyl knows about; it is one the model
    remembered, and the two are indistinguishable downstream unless the
    distinction is carried in the data.
    """

    name: str
    # What the uploaded material says they do. Never what the model knows.
    positioning: str = ""
    mentioned_in: list[str] = Field(default_factory=list)

    @property
    def is_grounded(self) -> bool:
        return bool(self.mentioned_in)


class ICPArchetype(BaseModel):
    """One buyer or user archetype, in the founder's vocabulary."""

    id: str
    label: str
    # Share of the buying audience. Normalised across the profile at compile.
    weight: float = Field(default=1.0, gt=0)

    role: str
    seniority: Seniority = "manager"
    budget_authority: BudgetAuthority = "influencer"

    # What they use today. The single most load-bearing field in the profile:
    # a B2B buyer evaluates net of what they would have to rip out.
    incumbent_tooling: list[str] = Field(default_factory=list)
    switching_cost: SwitchingCost = "moderate"

    # What they judge on, in their order of priority.
    evaluation_criteria: list[str] = Field(default_factory=list)
    # What makes them distrust a pitch. Feeds the agent's disposition directly,
    # and is where a good synthesis separates itself from a generic one.
    skepticism_triggers: list[str] = Field(default_factory=list)

    goals: list[str] = Field(default_factory=list)
    pains: list[str] = Field(default_factory=list)

    # Where this archetype actually argues about tools. Platform ids, matched
    # against the run's selected platforms at compile.
    platforms: list[str] = Field(default_factory=list)

    # Prior only. The compiler takes psychometrics from the named built-in pack
    # archetype rather than asking the model to invent a Big Five vector.
    prior_pack_id: str | None = None
    prior_archetype_id: str | None = None

    # -1..1. How this archetype is disposed toward the subject *before* seeing
    # it — from switching cost and skepticism triggers, not from optimism.
    disposition: float = Field(default=0.0, ge=-1.0, le=1.0)


class AdversarialArchetype(BaseModel):
    """One incumbent-aligned archetype (PRD §4, DECISIONS §7).

    Held separately from `ICPArchetype` rather than being flagged inside it,
    because everything downstream treats the two differently: they are labelled
    synthetic in every report and export, their share of the swarm is configured
    independently, and an objection's cohort spread means something different
    when it crosses from this side of the room.
    """

    id: str
    label: str
    weight: float = Field(default=1.0, gt=0)
    role: AdversarialRole

    # The incumbent this archetype is aligned to, or None for an unnamed
    # category skeptic. Naming one requires `grounded_in`.
    competitor_name: str | None = None
    # Document ids that named the competitor. The guardrail, in data.
    grounded_in: list[str] = Field(default_factory=list)

    # The argument they make. Must be about the *category or the switch*, not a
    # factual claim about a named company's product — the model does not know
    # those and will invent them.
    core_argument: str = ""
    talking_points: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)

    prior_pack_id: str | None = None
    prior_archetype_id: str | None = None
    disposition: float = Field(default=-0.4, ge=-1.0, le=1.0)

    @model_validator(mode="after")
    def _name_requires_grounding(self) -> AdversarialArchetype:
        """A named competitor with no source document is model memory.

        Rejected here rather than filtered later: by the time this object
        reaches a report, the name has already been through agent generation
        and into verbatim quotes, and there is no honest way to redact it.
        """
        if self.competitor_name and not self.grounded_in:
            raise ValueError(
                f"Adversarial archetype '{self.id}' names competitor "
                f"'{self.competitor_name}' with no grounding document. A "
                f"competitor may only be named from material the user "
                f"uploaded and marked as competitor material."
            )
        return self


class ICPProfile(BaseModel):
    """The synthesized ICP: what synthesis proposes and the founder corrects."""

    schema_version: int = ICP_SCHEMA_VERSION

    name: str
    product_summary: str = ""
    # The market as the uploaded material describes it — used to keep generic
    # skeptics on-category when there is no competitor material to ground them.
    category: str = ""

    archetypes: list[ICPArchetype] = Field(default_factory=list)
    adversarial: list[AdversarialArchetype] = Field(default_factory=list)
    competitors: list[Competitor] = Field(default_factory=list)

    # What synthesis could not determine from the material. Surfaced to the
    # founder rather than filled with a plausible guess: "your deck never says
    # who signs the cheque" is useful, and an invented answer is not.
    gaps: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _at_least_one_archetype(self) -> ICPProfile:
        if not self.archetypes:
            raise ValueError("An ICP profile needs at least one buyer archetype")
        return self

    @property
    def named_competitors(self) -> list[Competitor]:
        return [c for c in self.competitors if c.is_grounded]
