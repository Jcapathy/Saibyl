# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# SimulationAnalysis            — the whole artifact
# TimelinePoint, PlatformSlice, ArchetypeSlice, CohortSlice, ObjectionSummary,
# Flashpoint, PropagationEdge, AdversarialDisclosure, QualityBlock, Interval
# VariantScoreboard, VariantScore, VariantArchetypeSlice, ViralityComponents
# SCHEMA_VERSION
# ─────────────────────────────────────────────────────────
"""The typed shape of `simulation_analysis.artifact`.

Every number rendered in the UI or written into a report comes from an instance
of this model. That is the rule Phase 1 exists to establish, and it is only
enforceable because the shape is declared in one place: a field that does not
exist here cannot be displayed, so there is nowhere for a `Math.random()` to
hide.

Two conventions run through the whole artifact:

**Confidence comes from agents, not events.** A 25-agent run that produced 400
events has 25 independent observations, not 400 — one agent posting ten times is
one opinion repeated. Every interval here is computed across per-agent means, so
a small swarm honestly reports a wide band instead of manufacturing precision
from its own verbosity.

**Every finding carries `event_ids`.** A claim that cannot be drilled down to the
agent quotes that produced it does not belong in the artifact.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# Bumped when the artifact's shape changes in a way a reader must know about.
# The frontend refuses to render an unknown version rather than silently
# dropping fields it cannot find.
#
# 2 — Phase 2 adds `by_cohort` and `adversarial`. Both are additive, but the
#     version still moves: a client that renders a Founder-lens run without the
#     adversarial disclosure block would present incumbent-aligned synthetic
#     agents as ordinary market voices, which is the one thing PRD §4 forbids.
#     Refusing to render is the correct failure there.
#
# 3 — Phase 3 adds `scoreboard`. Additive again, and again the version moves for
#     a reason beyond the new field: on a multi-variant run the *headline* stops
#     being the thing to read. It aggregates every arena into one number, which
#     is the average of six competing headlines and describes none of them. A
#     client rendering v3 without the scoreboard would show a marketer a single
#     confident sentiment figure for a test whose entire purpose was to separate
#     six alternatives.
#
# **`SUPPORTED_SCHEMA_VERSION` in `frontend/src/lib/analysis.ts` must move in the
# same commit.** The frontend refuses to render an unknown version, so a bump
# without the mirror blanks every report in the product.
SCHEMA_VERSION = 3

Stance = Literal["support", "oppose", "undecided", "off_topic"]

# Which side of the room an agent is on. Not an archetype: a run can have six
# archetypes and only ever two cohorts, and the split that matters to a founder
# is buyers versus the people arguing against the switch.
Cohort = Literal["buyer", "adversarial"]


class Interval(BaseModel):
    """A mean with its 95% confidence interval and the n it was computed from."""

    mean: float
    lower: float
    upper: float
    # Independent observations — agents, not events.
    n: int

    @property
    def width(self) -> float:
        return self.upper - self.lower


class StanceSplit(BaseModel):
    support_pct: float = 0.0
    oppose_pct: float = 0.0
    undecided_pct: float = 0.0
    off_topic_pct: float = 0.0


class TimelinePoint(BaseModel):
    """One round of the sentiment arc."""

    round_number: int
    valence: Interval
    stance: StanceSplit
    mean_intensity: float = 0.0
    event_count: int = 0
    agent_count: int = 0
    novel_claim_count: int = 0


class PlatformSlice(BaseModel):
    platform: str
    valence: Interval
    stance: StanceSplit
    mean_intensity: float = 0.0
    event_count: int = 0
    agent_count: int = 0
    top_objection_keys: list[str] = Field(default_factory=list)


class ArchetypeSlice(BaseModel):
    archetype: str
    valence: Interval
    stance: StanceSplit
    mean_intensity: float = 0.0
    event_count: int = 0
    agent_count: int = 0
    top_objection_keys: list[str] = Field(default_factory=list)


class CohortSlice(BaseModel):
    """One side of the room: buyers, or incumbent-aligned agents.

    Reported separately from `by_archetype` because the question it answers is
    different. An archetype breakdown says which *kind of person* reacted how; a
    cohort split says how much of the negativity came from agents constructed to
    argue against the switch. A founder reading a −0.4 headline needs to know
    whether that is the market or the 40% of the swarm they configured to be
    hostile, and no archetype table makes that legible.
    """

    cohort: Cohort
    valence: Interval
    stance: StanceSplit
    mean_intensity: float = 0.0
    event_count: int = 0
    # Agents in this cohort that produced at least one measured event.
    agent_count: int = 0
    # Agents allocated to this cohort, whether or not they spoke. The pair makes
    # a silent cohort visible instead of shrinking its denominator.
    agents_total: int = 0
    archetypes: list[str] = Field(default_factory=list)
    top_objection_keys: list[str] = Field(default_factory=list)


class AdversarialDisclosure(BaseModel):
    """What the adversarial cohort was, stated wherever the run is presented.

    PRD §4: adversarial agents are labelled synthetic in every report and
    export. That obligation is carried in the artifact rather than left to each
    renderer, because a rule re-implemented in the viewer, the print page, the
    PDF exporter and the PPTX exporter is a rule that will be missing from one
    of them.

    `disclosure` is the sentence itself, composed once here, so all four render
    the same words.
    """

    enabled: bool = False
    # What the run was configured with, 0..0.5.
    share_configured: float = 0.0
    # What it actually came out as — allocation is by archetype weight and
    # rounds to whole agents, so the two differ on small swarms.
    share_realised: float = 0.0
    agents_total: int = 0
    agents_active: int = 0
    archetypes: list[str] = Field(default_factory=list)
    # adversarial_role -> agent count.
    roles: dict[str, int] = Field(default_factory=dict)
    # Competitors named in the run, and only ever those grounded in material the
    # user uploaded. An empty list on an enabled cohort is the normal case: the
    # cohort is generated with no named entity when there is nothing to ground
    # it in.
    named_competitors: list[str] = Field(default_factory=list)
    disclosure: str = ""


class ObjectionQuote(BaseModel):
    event_id: str
    agent_username: str
    archetype: str | None = None
    platform: str | None = None
    round_number: int | None = None
    text: str


class PropagationPoint(BaseModel):
    round_number: int
    event_count: int
    agent_count: int


class ObjectionSummary(BaseModel):
    """A canonical objection, clustered from raw per-event objection strings."""

    key: str
    label: str
    summary: str = ""

    quotes: list[ObjectionQuote] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)

    agent_count: int = 0
    event_count: int = 0
    first_round_seen: int | None = None
    originating_cohort: str | None = None
    # archetype -> share of that archetype's agents voicing this objection
    cohort_spread: dict[str, float] = Field(default_factory=dict)
    propagation: list[PropagationPoint] = Field(default_factory=list)

    # Did this objection start on the incumbent's side of the room, and did it
    # get out? "Competitor advocates start the narrative decline" is argument 2
    # for the cohort existing at all (PRD §4), and it is only checkable if the
    # artifact records where an objection originated and who repeated it.
    #
    # An objection that starts adversarial and stays adversarial is a competitor
    # talking to themselves. One that starts adversarial and crosses into buyers
    # is the thing the inoculation loop exists to answer.
    originated_adversarial: bool = False
    adversarial_agent_count: int = 0
    buyer_agent_count: int = 0

    @property
    def crossed_into_buyers(self) -> bool:
        return self.originated_adversarial and self.buyer_agent_count > 0

    mean_intensity: float = 0.0
    # reach x intensity x cohort spread. Ranking on this rather than frequency
    # is the difference between "most mentioned" and "most likely to kill the
    # deal" — the two are usually different objections.
    load_bearing_score: float = 0.0


class Flashpoint(BaseModel):
    """A round where sentiment moved sharply, with the events that moved it."""

    round_number: int
    platform: str | None = None
    valence_before: float
    valence_after: float
    delta: float
    # Whether the shift is larger than the confidence bands on either side.
    # A move inside the noise is reported as such rather than narrated.
    significant: bool
    trigger_event_ids: list[str] = Field(default_factory=list)
    objection_keys: list[str] = Field(default_factory=list)
    description: str = ""


class PropagationEdge(BaseModel):
    """An objection crossing from one cohort or platform into another."""

    objection_key: str
    from_group: str
    to_group: str
    group_kind: Literal["archetype", "platform"]
    first_round: int
    event_ids: list[str] = Field(default_factory=list)


class ViralityComponents(BaseModel):
    """The Virality Potential Score and the six components behind it.

    **A separate axis from the objective metric, never blended into it**
    (DECISIONS §6). A variant can spread widely and convert terribly; one score
    hides the two cases a marketer must act on.

    **None is not zero anywhere in here.** A component that could not be
    measured is None and is dropped from the weighting, with the remaining
    weights renormalised — counting it as zero would penalise a variant for a
    gap in the instrumentation. `components_used` says how many actually
    contributed, so a score built from three is not read as one built from six.
    """

    # 0–100, or None when nothing at all could be measured.
    score: float | None = None
    components_used: int = 0
    components_total: int = 6

    # Share of this arena's active agents whose measured intent was to share.
    share_intent_rate: Interval = Field(
        default_factory=lambda: Interval(mean=0.0, lower=0.0, upper=0.0, n=0)
    )
    # **The heaviest-weighted component.** Content that spreads only within the
    # cohort it started in is an echo chamber, and a share count cannot tell the
    # difference.
    cross_archetype_reach: float = 0.0
    archetypes_reached: int = 0
    archetypes_total: int = 0

    # None on a single-platform run — there is nowhere to jump to, and 0.0 would
    # read as a failure to travel.
    cross_platform_jump: float | None = None
    # Share of agents who restated the message in their own words. None before
    # migration 023, when nothing carried a takeaway.
    restatement_rate: float | None = None

    # Mean replies per post that attracted any. **Branching, not depth**:
    # `BasePlatformAdapter.comment()` takes a post id across all twelve
    # adapters, so there is no reply-to-reply and the graph is structurally two
    # levels deep. A depth figure would read 2.0 for every variant that got one
    # reply. None before migration 022, when no edges were stored.
    cascade_branching: float | None = None

    # Fast-burn versus slow-build. Reported raw because it shapes channel and
    # budget timing rather than being better or worse — which is also why it is
    # the lowest-weighted component.
    velocity_rounds_to_peak: int | None = None
    velocity_normalised: float | None = None


class VariantArchetypeSlice(BaseModel):
    """How one archetype responded to one variant.

    The per-archetype breakdown is the reason matched swarms are worth the cost:
    "who does this variant win, and who does it lose" is a different and more
    actionable question than "which variant won overall".
    """

    archetype: str
    objective_rate: Interval
    valence: Interval
    agent_count: int = 0
    event_count: int = 0


class VariantScore(BaseModel):
    """One arena's result."""

    variant_key: str
    label: str = ""
    content: str = ""

    # The headline for this run's objective — a proportion over *agents*, so a
    # variant that made one agent post six times does not outrank one that
    # convinced six agents.
    objective_rate: Interval
    # Supporting, not headline (DECISIONS §6). A variant that converts while
    # everyone resents it is a finding, and it is invisible without this.
    valence: Interval
    stance: StanceSplit = Field(default_factory=StanceSplit)

    virality: ViralityComponents = Field(default_factory=ViralityComponents)
    # Lexical overlap between what agents said the message was and what it
    # actually said. Deliberately crude and labelled as such wherever rendered —
    # a per-variant main-model pass would price the lens out of its tier, and
    # asserting accuracy without measuring it is worse than an approximation
    # that says what it is. None when nothing carried a takeaway.
    takeaway_accuracy: float | None = None

    # The two cases DECISIONS §6 exists to keep visible.
    viral_but_off_message: bool = False
    converts_but_wont_travel: bool = False

    agent_count: int = 0
    event_count: int = 0
    event_ids: list[str] = Field(default_factory=list)
    by_archetype: list[VariantArchetypeSlice] = Field(default_factory=list)


class VariantScoreboard(BaseModel):
    """The N-way comparison. Absent entirely on a single-arena run.

    `winner_variant_key` is None whenever the top two variants' intervals
    overlap, and `verdict` says so in words. **Do not "improve" that into always
    naming a winner** — a marketer acts on the top row, and an ordering drawn
    from overlapping bands launders sampling noise into a decision. This is the
    same rule the inoculation loop's `unresolved` verdict encodes, for the same
    reason.
    """

    # None when the run has no configured objective, in which case the intents
    # below are the union of every committing action.
    objective: str | None = None
    objective_intents: list[str] = Field(default_factory=list)

    # Ranked by the objective metric. The ordering is display order and is not
    # itself a claim — `verdict` carries the claim.
    variants: list[VariantScore] = Field(default_factory=list)
    winner_variant_key: str | None = None
    verdict: str = ""

    # Stated so a reader can disagree with them rather than reverse-engineer
    # them from the flags.
    viral_score_threshold: float = 60.0
    off_message_threshold: float = 0.25


class QualityBlock(BaseModel):
    """What the artifact is and is not entitled to claim.

    Shown to the user rather than kept internal: a 25-agent free run genuinely
    has wide bands, and saying so is both honest and the most credible argument
    for buying more agents.
    """

    events_total: int = 0
    events_measured: int = 0
    coverage_pct: float = 0.0
    agents_total: int = 0
    agents_active: int = 0
    rounds: int = 0
    measurement_model: str = ""
    mean_ci_width: float = 0.0
    confidence: Literal["low", "moderate", "high"] = "low"
    caveats: list[str] = Field(default_factory=list)


class Headline(BaseModel):
    """The numbers a reader sees first. Each has a drill-down behind it."""

    valence: Interval
    stance: StanceSplit
    mean_intensity: float = 0.0
    # Share of measured events whose valence sign differs from the run mean —
    # a direct read of how split the audience is, replacing V1's scraped
    # "controversy score".
    polarization_pct: float = 0.0
    novel_claim_pct: float = 0.0
    trajectory: Literal["improving", "declining", "flat"] = "flat"
    # First round to last, with the CI of the difference respected.
    trajectory_delta: float = 0.0
    top_objection_key: str | None = None


class SimulationAnalysis(BaseModel):
    """The artifact. Nothing renders that is not in here."""

    schema_version: int = SCHEMA_VERSION
    simulation_id: str
    generated_at: datetime

    headline: Headline
    sentiment_timeline: list[TimelinePoint] = Field(default_factory=list)
    by_platform: list[PlatformSlice] = Field(default_factory=list)
    by_archetype: list[ArchetypeSlice] = Field(default_factory=list)
    # Empty on a run with no adversarial cohort. A one-sided split is not a
    # split, and rendering "buyers: 100%" is noise.
    by_cohort: list[CohortSlice] = Field(default_factory=list)
    objections: list[ObjectionSummary] = Field(default_factory=list)
    flashpoints: list[Flashpoint] = Field(default_factory=list)
    propagation: list[PropagationEdge] = Field(default_factory=list)
    adversarial: AdversarialDisclosure = Field(default_factory=AdversarialDisclosure)
    # Absent on every single-arena run, which is every Founder- and Crisis-lens
    # run and every run created before Phase 3. One variant is not a comparison,
    # and a one-row scoreboard invites a reader to treat it as one.
    #
    # **When this is present, it is the headline.** `headline` above aggregates
    # every arena into one number, which is the average of six competing
    # messages and describes none of them — see SCHEMA_VERSION 3.
    scoreboard: VariantScoreboard | None = None
    quality: QualityBlock
