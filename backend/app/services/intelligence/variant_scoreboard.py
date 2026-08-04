# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# build_scoreboard(run) -> VariantScoreboard | None
# OBJECTIVE_INTENTS, objective_intents(objective)
# ─────────────────────────────────────────────────────────
"""The N-way variant scoreboard, and the Virality Potential Score.

**DECISIONS_V2 §6.** The objective chosen at setup determines the headline
metric; sentiment demotes to a supporting one. An ad meant to drive foot traffic
and an ad meant to sell a service succeed differently, and scoring both on
sentiment measures neither.

**Virality is a separate axis and is never blended into the objective score.** A
variant can spread widely and convert terribly. Blending hides exactly the two
cases a marketer has to act on — *viral but off-message*, which will spread as
something they did not say, and *converts but won't travel*, which is good copy
that needs paid distribution. Both are emitted as explicit flags rather than left
for a reader to infer from two numbers side by side.

Three rules carried from Phase 1, because they are what make a scoreboard a
measurement rather than a leaderboard:

- **Confidence comes from agents, not events.** Intent rates are proportions
  over *agents*, so a variant that made one agent post six times does not
  outrank one that convinced six agents.
- **Overlapping intervals are not a ranking.** `winner` is None whenever the top
  two variants' intervals overlap, and `verdict` says so. A scoreboard that
  always names a winner is a scoreboard that will name one from noise.
- **Gaps stay gaps.** A component that cannot be measured is None, never 0.0.
  Zero means "measured, and nothing happened"; None means "not measured", and
  collapsing the two is how a structural gap starts reading as a finding.
"""
from __future__ import annotations

import math

import structlog

from app.services.intelligence.analysis_data import (
    MeasuredEvent,
    RunData,
    mean_interval,
    stance_split,
)
from app.services.intelligence.analysis_schema import (
    Interval,
    VariantArchetypeSlice,
    VariantScore,
    VariantScoreboard,
    ViralityComponents,
)

logger = structlog.get_logger()

_Z_95 = 1.96

# Which measured `intent` values count as success for each objective.
#
# The classifier's taxonomy is fixed (`purchase`, `trial`, `click`, `visit`,
# `inquire`, `share`, `abandon`, `none`); this maps the PRD §6 objective table
# onto it. An objective counts more than one intent where the weaker one is
# genuinely the same decision at a different commitment level — a "trial" is a
# real signup outcome, and refusing it would understate every signup test.
OBJECTIVE_INTENTS: dict[str, tuple[str, ...]] = {
    "clicks": ("click",),
    "foot_traffic": ("visit",),
    "product_sale": ("purchase",),
    "service_sale": ("inquire",),
    "signup": ("trial", "purchase"),
    # Awareness is the one objective with no single decisive action. It is
    # measured as recall-plus-share: an agent who restated the message or would
    # pass it on has been reached, which is what awareness means.
    "awareness": ("share",),
}

# Weights for the Virality Potential Score, summing to 1.0.
#
# **Cross-archetype reach carries the heaviest weight** — PRD §6 and DECISIONS
# §6 both say so, and the reason is that a naive share-count cannot tell
# virality from an echo chamber. Content that spreads only inside the cohort it
# started in has not travelled.
_VIRALITY_WEIGHTS = {
    "cross_archetype_reach": 0.35,
    "share_intent_rate": 0.20,
    "cross_platform_jump": 0.15,
    "restatement_rate": 0.15,
    "cascade_branching": 0.10,
    "velocity": 0.05,
}


def objective_intents(objective: str | None) -> tuple[str, ...]:
    """Intents that count as success for an objective.

    Falls back to the union of every committing intent when no objective is
    configured — which is what a Founder- or Crisis-lens run gets, and what the
    Marketing lens gets before the objective is chosen.
    """
    if objective and objective in OBJECTIVE_INTENTS:
        return OBJECTIVE_INTENTS[objective]
    return ("purchase", "trial", "click", "visit", "inquire")


def _proportion_interval(hits: int, n: int) -> Interval:
    """A proportion with a 95% interval, over agents.

    Zero observed does not mean zero true rate: with no hits the upper bound is
    the rule-of-three 3/n, so "no agent clicked, in 40 agents" reports a band up
    to 7.5% rather than a confident zero. Same convention as the inoculation
    loop's reach bands, deliberately — the two appear side by side in a report.
    """
    if n <= 0:
        return Interval(mean=0.0, lower=0.0, upper=0.0, n=0)

    p = hits / n
    if hits == 0:
        return Interval(mean=0.0, lower=0.0, upper=round(min(1.0, 3.0 / n), 4), n=n)

    margin = _Z_95 * math.sqrt(max(p * (1.0 - p), 0.0) / n)
    return Interval(
        mean=round(p, 4),
        lower=round(max(0.0, p - margin), 4),
        upper=round(min(1.0, p + margin), 4),
        n=n,
    )


def _agents_in(events: list[MeasuredEvent]) -> set[str]:
    return {e.agent_id or e.agent_username for e in events}


def _normalised_velocity(events: list[MeasuredEvent], max_rounds: int) -> float | None:
    """How fast the arena peaked, on 0..1 where 1 is fastest.

    Rounds-to-peak is reported raw alongside this; the normalised form exists
    only so it can join a weighted score. A fast burn and a slow build are not
    better and worse — they shape channel and budget timing — so this is the
    lowest-weighted component by a wide margin.
    """
    if not events or max_rounds <= 1:
        return None
    per_round: dict[int, int] = {}
    for event in events:
        per_round[event.round_number] = per_round.get(event.round_number, 0) + 1
    if not per_round:
        return None
    peak_round = max(per_round, key=lambda r: per_round[r])
    return round(1.0 - (peak_round - 1) / max(1, max_rounds - 1), 4)


def _restatement_rate(events: list[MeasuredEvent], agents: int) -> float | None:
    """Share of agents who put the message in their own words.

    Measured from `takeaway`, which the classifier writes per event. Returns
    None when nothing carries a takeaway at all — every run measured before
    migration 023, where a 0.0 would read as "nobody restated it" rather than
    "this was not measured".
    """
    with_takeaway = [e for e in events if e.takeaway]
    if not with_takeaway:
        return None
    restating = {e.agent_id or e.agent_username for e in with_takeaway}
    return round(len(restating) / agents, 4) if agents else 0.0


def _cascade_branching(events: list[MeasuredEvent]) -> float | None:
    """Mean replies per post that attracted any.

    **This is branching, not depth.** `BasePlatformAdapter.comment()` takes a
    post id across all twelve adapters, so there is no reply-to-reply and the
    graph is structurally two levels deep — a depth metric would report 2.0 for
    every variant that got a single reply and tell a marketer nothing.

    None when the run carries no graph edges at all, which is every run written
    before migration 022.
    """
    replies = [e for e in events if e.target_event_id]
    if not replies:
        return None
    per_parent: dict[str, int] = {}
    for event in replies:
        key = event.target_event_id or ""
        per_parent[key] = per_parent.get(key, 0) + 1
    if not per_parent:
        return None
    return round(sum(per_parent.values()) / len(per_parent), 4)


def _cross_platform_jump(events: list[MeasuredEvent], run: RunData) -> float | None:
    """Share of this arena's active agents seen on more than one platform.

    None on a single-platform run: there is nowhere to jump to, and 0.0 would
    read as "it failed to travel" when the run never offered the chance.
    """
    if len(run.platforms) < 2:
        return None
    by_agent: dict[str, set[str]] = {}
    for event in events:
        by_agent.setdefault(e_key := (event.agent_id or event.agent_username), set())
        by_agent[e_key].add(event.platform)
    if not by_agent:
        return 0.0
    crossed = sum(1 for platforms in by_agent.values() if len(platforms) > 1)
    return round(crossed / len(by_agent), 4)


def _virality(
    events: list[MeasuredEvent],
    run: RunData,
    active_agents: int,
) -> ViralityComponents:
    """The six components and the 0–100 score built from them.

    Unmeasurable components are None and are **dropped from the weighting**,
    with the remaining weights renormalised — rather than counted as zero, which
    would penalise a variant for a gap in the instrumentation. `components_used`
    records how many contributed, so a score built from three components is not
    read as equivalent to one built from six.
    """
    share_agents = {
        e.agent_id or e.agent_username for e in events if e.intent == "share"
    }
    share_rate = _proportion_interval(len(share_agents), active_agents)

    archetypes_reached = {e.archetype for e in events}
    total_archetypes = len(run.archetypes) or 1
    cross_archetype = round(len(archetypes_reached) / total_archetypes, 4)

    components = ViralityComponents(
        share_intent_rate=share_rate,
        cross_archetype_reach=cross_archetype,
        archetypes_reached=len(archetypes_reached),
        archetypes_total=total_archetypes,
        cross_platform_jump=_cross_platform_jump(events, run),
        restatement_rate=_restatement_rate(events, active_agents),
        cascade_branching=_cascade_branching(events),
        velocity_rounds_to_peak=_rounds_to_peak(events),
        velocity_normalised=_normalised_velocity(events, run.max_rounds),
    )

    measured = {
        "cross_archetype_reach": components.cross_archetype_reach,
        "share_intent_rate": share_rate.mean,
        "cross_platform_jump": components.cross_platform_jump,
        "restatement_rate": components.restatement_rate,
        # Branching is a count, not a share. Normalised against 5 replies per
        # post, above which a post is unambiguously a conversation — the cap
        # matters more than the exact figure, since an uncapped ratio would let
        # one very busy post dominate a 0–100 score.
        "cascade_branching": (
            min(1.0, components.cascade_branching / 5.0)
            if components.cascade_branching is not None
            else None
        ),
        "velocity": components.velocity_normalised,
    }
    contributing = {k: v for k, v in measured.items() if v is not None}
    if contributing:
        total_weight = sum(_VIRALITY_WEIGHTS[k] for k in contributing)
        score = sum(
            _VIRALITY_WEIGHTS[k] * v for k, v in contributing.items()
        ) / total_weight
        components.score = round(score * 100, 2)
    components.components_used = len(contributing)
    components.components_total = len(measured)
    return components


def _rounds_to_peak(events: list[MeasuredEvent]) -> int | None:
    if not events:
        return None
    per_round: dict[int, int] = {}
    for event in events:
        per_round[event.round_number] = per_round.get(event.round_number, 0) + 1
    return max(per_round, key=lambda r: per_round[r]) if per_round else None


def _takeaway_accuracy(events: list[MeasuredEvent], content: str) -> float | None:
    """Share of stated takeaways that overlap the copy they came from.

    A deliberately crude lexical overlap, and labelled as such wherever it is
    rendered. The alternative is a second main-model pass per variant, which
    would price the Marketing lens out of the tier it is sold in; the alternative
    to *that* is asserting takeaway accuracy without measuring it, which is worse
    than a stated approximation.

    What it is good at is the case it exists for: a takeaway sharing almost no
    vocabulary with the copy is a message that travelled as something else, and
    that is the *viral but off-message* flag.
    """
    stated = [e.takeaway for e in events if e.takeaway]
    if not stated or not content.strip():
        return None

    source = {w for w in _words(content) if len(w) > 3}
    if not source:
        return None

    scores = []
    for takeaway in stated:
        words = {w for w in _words(takeaway) if len(w) > 3}
        if not words:
            continue
        scores.append(len(words & source) / len(words))
    return round(sum(scores) / len(scores), 4) if scores else None


_STOPWORDS = {
    "this", "that", "with", "from", "your", "their", "have", "will", "would",
    "about", "which", "there", "they", "than", "then", "into", "more", "most",
    "some", "such", "only", "other", "been", "were", "what", "when", "just",
}


def _words(text: str) -> list[str]:
    cleaned = "".join(c.lower() if c.isalnum() else " " for c in text)
    return [w for w in cleaned.split() if w not in _STOPWORDS]


# How far below the run's best takeaway accuracy a variant must sit before it is
# called off-message.
#
# **Relative, not absolute — and that is a correction, not a preference.** This
# was an absolute 0.25 until the first live multi-variant run measured the metric
# at 0.07, 0.07 and 0.14 across three variants. An absolute cut of 0.25 fired on
# two of three, and a flag that fires on almost everything is noise wearing the
# clothes of a finding.
#
# The mistake was mine and it was a familiar one: 0.25 was a number I picked, not
# a number I measured, sitting in a codebase whose whole discipline is that those
# are different things. Lexical overlap between a twelve-word paraphrase and a
# marketing sentence is *inherently* low; there is no absolute level at which it
# means "off-message".
#
# What a marketer can act on is a variant that is understood **worse than its
# alternatives** — a comparison the matched swarm makes valid, since all three
# faced the same audience. So the flag now needs a real gap between variants, and
# is silent when they sit together, which is the honest reading of "this metric
# did not separate them".
_OFF_MESSAGE_RELATIVE_GAP = 0.40
# Above this, a variant is spreading. Stated in the artifact rather than hidden
# here, so a reader can disagree with it.
_VIRAL_ABOVE = 60.0
# Objective-metric mean above which a variant is "converting" for the two
# derived flags.
_CONVERTING_ABOVE = 0.20


def build_scoreboard(run: RunData) -> VariantScoreboard | None:
    """Score every arena on the run's objective, plus virality.

    Returns None for a single-arena run. One variant is not a comparison, and an
    artifact carrying a one-row scoreboard invites a reader to treat it as one.
    """
    if not run.is_multi_variant:
        return None

    intents = objective_intents(run.objective)
    scores: list[VariantScore] = []

    for arena in run.arenas:
        events = run.events_for(arena.variant_key)
        scored = [e for e in events if e.scored]
        active = _agents_in(events)
        n_active = len(active)

        converting = {
            e.agent_id or e.agent_username for e in events if e.intent in intents
        }
        objective_rate = _proportion_interval(len(converting), n_active)

        by_archetype = []
        for archetype in run.archetypes:
            arch_events = [e for e in events if e.archetype == archetype]
            if not arch_events:
                continue
            arch_agents = _agents_in(arch_events)
            arch_converting = {
                e.agent_id or e.agent_username
                for e in arch_events
                if e.intent in intents
            }
            by_archetype.append(
                VariantArchetypeSlice(
                    archetype=archetype,
                    objective_rate=_proportion_interval(
                        len(arch_converting), len(arch_agents)
                    ),
                    valence=mean_interval([e for e in arch_events if e.scored]),
                    agent_count=len(arch_agents),
                    event_count=len(arch_events),
                )
            )

        virality = _virality(events, run, n_active)
        accuracy = _takeaway_accuracy(events, arena.content)

        scores.append(
            VariantScore(
                variant_key=arena.variant_key,
                label=arena.label,
                content=arena.content,
                objective_rate=objective_rate,
                # Sentiment is kept and demoted, not dropped. It is the
                # supporting metric — a variant that converts while everyone
                # resents it is a finding, and it is invisible without this.
                valence=mean_interval(scored),
                stance=stance_split(scored),
                virality=virality,
                takeaway_accuracy=accuracy,
                agent_count=n_active,
                event_count=len(events),
                event_ids=[e.id for e in events],
                # Set by `_flag_off_message` once every arena is scored — it is
                # a statement about this variant relative to the others.
                viral_but_off_message=False,
                converts_but_wont_travel=bool(
                    objective_rate.mean >= _CONVERTING_ABOVE
                    and virality.score is not None
                    and virality.score < _VIRAL_ABOVE
                ),
                by_archetype=by_archetype,
            )
        )

    # Off-message is decided across the run, not per variant, so it cannot be
    # computed in the loop above. The matched swarm is what makes the comparison
    # legitimate: all variants faced the same audience, so "understood worse than
    # its alternatives" is a real statement where "below 0.25" was not.
    _flag_off_message(scores)

    ranked = sorted(scores, key=lambda s: s.objective_rate.mean, reverse=True)
    winner, verdict = _resolve_winner(ranked)

    board = VariantScoreboard(
        objective=run.objective,
        objective_intents=list(intents),
        variants=ranked,
        winner_variant_key=winner,
        verdict=verdict,
        # Named in the artifact so a reader can disagree with the thresholds
        # rather than reverse-engineer them from the flags.
        viral_score_threshold=_VIRAL_ABOVE,
        off_message_threshold=_OFF_MESSAGE_RELATIVE_GAP,
    )

    logger.info(
        "variant_scoreboard_built",
        simulation_id=run.simulation_id,
        objective=run.objective,
        variants=len(ranked),
        winner=winner,
        verdict=verdict,
        silent_arenas=[s.variant_key for s in ranked if s.event_count == 0],
    )
    return board


def _flag_off_message(scores: list[VariantScore]) -> None:
    """Mark variants that spread while being understood worse than their peers.

    Silent when the variants' takeaway accuracies sit together, which is the
    honest reading of "this metric did not separate them" — and, on the first
    live run, the true one: 0.07, 0.07 and 0.14 are not three different levels
    of comprehension, they are one crude measure with noise on it.

    Requires at least three arenas. With two, "worse than the other" is a
    coin-flip dressed as a finding.
    """
    measured = [s for s in scores if s.takeaway_accuracy is not None]
    if len(measured) < 3:
        return

    best = max(s.takeaway_accuracy or 0.0 for s in measured)
    if best <= 0.0:
        return

    for score in measured:
        gap = (best - (score.takeaway_accuracy or 0.0)) / best
        score.viral_but_off_message = bool(
            score.virality.score is not None
            and score.virality.score >= _VIRAL_ABOVE
            and gap >= _OFF_MESSAGE_RELATIVE_GAP
        )


def _resolve_winner(ranked: list[VariantScore]) -> tuple[str | None, str]:
    """Name a winner only when the top two do not overlap.

    This is the rule the whole scoreboard exists to honour. A marketer will act
    on the top row; if the top two variants' intervals overlap, the ordering is
    an artefact of sampling and naming a winner launders noise into a decision.
    """
    if not ranked:
        return None, "No variant produced a measurable result."
    if len(ranked) == 1:
        return None, "Only one variant produced events; there is nothing to compare."

    best, second = ranked[0], ranked[1]
    if best.objective_rate.n == 0:
        return None, "No agent in the leading variant was measured."

    if best.objective_rate.lower > second.objective_rate.upper:
        return (
            best.variant_key,
            f"{best.label or best.variant_key} leads: its interval "
            f"({best.objective_rate.lower:.1%}–{best.objective_rate.upper:.1%}) "
            f"clears the runner-up's "
            f"({second.objective_rate.lower:.1%}–{second.objective_rate.upper:.1%}).",
        )

    tied = [
        s.label or s.variant_key
        for s in ranked
        if s.objective_rate.upper >= best.objective_rate.lower
    ]
    return (
        None,
        f"No winner: {', '.join(tied)} overlap on the objective metric. "
        f"The ordering above is not a ranking — more agents would be needed to "
        f"separate them.",
    )
