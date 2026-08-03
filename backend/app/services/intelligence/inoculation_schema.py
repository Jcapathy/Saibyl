# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# InoculationAsset      — one drafted counter-asset
# ObjectionMeasurement  — an objection's reach in one run
# ObjectionDelta        — the same objection across two runs, with a verdict
# InoculationResult     — the whole before/after comparison
# ASSET_TYPES, Verdict
# ─────────────────────────────────────────────────────────
"""The before/after object the inoculation loop produces.

DECISIONS_V2 §4 is unambiguous about why this exists: without the re-simulation,
"here's what to pre-position" is an LLM opinion. With it, Saibyl can say *this
disclosure moved this objection from 34% of the swarm to 9%*. The difference
between those two products is entirely in this file's `ObjectionDelta.verdict`.

**The verdict is allowed to be `ineffective`, and that is the feature.** An
asset that does not move its objection is the most valuable thing the loop can
tell a founder, because it is the one thing they cannot learn from an LLM
opinion — an LLM asked whether its own suggestion would work says yes. The
verdict is computed from the confidence intervals, not from the point estimate,
so "it went from 34% to 31%" reports as unresolved rather than as progress.

**Reach is share of agents, never share of events.** An objection voiced ten
times by one agent is one agent's objection. This is the same clustering rule as
`mean_interval`, applied to a proportion, and it is why the two runs are
comparable even when one produced more events than the other.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.services.intelligence.analysis_schema import Interval

INOCULATION_SCHEMA_VERSION = 1

# What a counter-asset can be. Fixed rather than free-form: each is a real
# artefact a founder can publish, and the list is the menu the drafting pass
# chooses from. A free-form type drifts into "messaging", which is not something
# anyone can go and write.
ASSET_TYPES: tuple[str, ...] = (
    # A plain statement of a limitation, published before someone finds it.
    "disclosure",
    # What is coming and when. Answers "this is missing" without claiming it
    # exists.
    "roadmap",
    # Why the price is the price. The most common request behind a price
    # objection is a reason, not a discount.
    "pricing_rationale",
    "security_page",
    # How to get off the incumbent. The direct answer to switching cost, which
    # is the objection the adversarial cohort exists to surface.
    "migration_guide",
    "faq_entry",
    # "Why not just use X." Only permitted when a competitor was grounded in
    # uploaded material — see the drafting pass.
    "comparison_page",
)

AssetType = Literal[
    "disclosure",
    "roadmap",
    "pricing_rationale",
    "security_page",
    "migration_guide",
    "faq_entry",
    "comparison_page",
]

# died       — nobody voiced it in the re-simulation.
# shrank     — measurably fewer agents, intervals separated.
# unresolved — moved, but inside the bands. NOT progress.
# unchanged  — did not move.
# grew       — measurably more agents. The asset drew attention to it.
# emerged    — absent before, present after. A new objection the asset created.
Verdict = Literal["died", "shrank", "unresolved", "unchanged", "grew", "emerged"]


class InoculationAsset(BaseModel):
    """One counter-asset, as drafted and as it will be published."""

    objection_key: str
    objection_label: str = ""
    asset_type: AssetType
    title: str
    body: str
    # Stated before the re-simulation. An unstated hypothesis is always
    # retroactively correct.
    hypothesis: str = ""


class ObjectionMeasurement(BaseModel):
    """How far one objection reached in one run."""

    # Agents that voiced it.
    agent_count: int = 0
    # Agents that produced any measured event — the denominator. Held per run
    # because the two runs can differ: an agent that was silent in one run and
    # spoke in the other changes the base, and hiding that would let a quieter
    # re-simulation read as a successful inoculation.
    agents_active: int = 0
    event_count: int = 0
    mean_intensity: float = 0.0
    load_bearing_score: float = 0.0
    # Share of active agents voicing it, with a 95% interval on the proportion.
    reach: Interval

    @property
    def present(self) -> bool:
        return self.agent_count > 0


class ObjectionDelta(BaseModel):
    """One objection, measured before and after the asset was pre-positioned."""

    objection_key: str
    label: str
    before: ObjectionMeasurement
    after: ObjectionMeasurement

    # after.reach.mean - before.reach.mean, in percentage points.
    reach_delta_pct: float = 0.0
    # True only when the two proportions' intervals do not overlap. Everything
    # the UI is allowed to call a result depends on this being conservative.
    significant: bool = False
    verdict: Verdict = "unchanged"

    # Which assets were written against this objection. An objection can be
    # targeted by more than one, and then the loop measures the pair, not
    # either one — stated here rather than implied.
    asset_ids: list[str] = Field(default_factory=list)
    asset_titles: list[str] = Field(default_factory=list)

    # Agents that voiced this objection before and did not after. The
    # "here are the agents who changed their mind" claim, as data. Empty when
    # the two runs' agents cannot be matched.
    converted_agent_usernames: list[str] = Field(default_factory=list)

    @property
    def effective(self) -> bool:
        """Did a pre-positioned asset actually move this objection?

        `unresolved` is deliberately excluded. A move inside the confidence
        bands is not a result, and counting it would turn the one number this
        product is sold on into noise.
        """
        return self.significant and self.verdict in ("died", "shrank")


class InoculationResult(BaseModel):
    """The whole before/after comparison for one re-simulation."""

    schema_version: int = INOCULATION_SCHEMA_VERSION
    parent_simulation_id: str
    child_simulation_id: str

    deltas: list[ObjectionDelta] = Field(default_factory=list)

    headline_before: Interval
    headline_after: Interval
    headline_delta: float = 0.0
    headline_significant: bool = False

    assets_tested: int = 0
    assets_effective: int = 0

    # Objections that appeared only in the re-simulation. Surfaced rather than
    # filtered: an asset that answers one objection and raises two is a result a
    # founder needs before they publish it.
    emerged_objection_keys: list[str] = Field(default_factory=list)

    # What this comparison cannot support, in the reader's words. Same purpose
    # as `StageSpec.cannot_conclude` — a limit that lives in a doc reaches
    # nobody, so it travels with the object it limits.
    caveats: list[str] = Field(default_factory=list)
