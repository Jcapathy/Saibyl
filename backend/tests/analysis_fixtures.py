"""A realistic `simulation_analysis` artifact for the export tests.

Built through the pydantic models rather than as a hand-written dict, so a
schema change breaks the fixture instead of letting the export tests keep
passing against a shape the product no longer produces.

Two properties are deliberately baked in and relied on by the tests:

* **An unmeasured slice.** Round 4 and the `linkedin` platform have `n = 0`,
  which is exactly what `analysis_data.mean_interval` returns when nothing was
  measured — mean 0.0 with a zero-width band. Any renderer that draws them puts
  a fabricated "neutral" on the page.
* **A one-agent slice.** The `Skeptical CFO` archetype has `n = 1`, whose band
  spans the whole scale by construction. It is the case where quoting the mean
  alone is most misleading.
"""
from __future__ import annotations

from datetime import UTC, datetime

from app.services.intelligence.analysis_schema import (
    AdversarialDisclosure,
    ArchetypeSlice,
    CohortSlice,
    Flashpoint,
    Headline,
    Interval,
    ObjectionQuote,
    ObjectionSummary,
    PairedComparison,
    PlatformSlice,
    QualityBlock,
    SimulationAnalysis,
    StanceSplit,
    TimelinePoint,
    VariantScore,
    VariantScoreboard,
    ViralityComponents,
)

SIMULATION_ID = "11111111-2222-3333-4444-555555555555"
REPORT_ID = "99999999-8888-7777-6666-555555555555"

UNMEASURED = Interval(mean=0.0, lower=0.0, upper=0.0, n=0)


def _interval(mean: float, half: float, n: int) -> Interval:
    return Interval(
        mean=round(mean, 4),
        lower=round(mean - half, 4),
        upper=round(mean + half, 4),
        n=n,
    )


def _stance(support: float, oppose: float, undecided: float, off_topic: float) -> StanceSplit:
    return StanceSplit(
        support_pct=support,
        oppose_pct=oppose,
        undecided_pct=undecided,
        off_topic_pct=off_topic,
    )


def make_analysis(*, scoreboard: VariantScoreboard | None = None) -> SimulationAnalysis:
    return SimulationAnalysis(
        simulation_id=SIMULATION_ID,
        generated_at=datetime(2026, 8, 3, 14, 30, tzinfo=UTC),
        headline=Headline(
            valence=_interval(-0.34, 0.19, 24),
            stance=_stance(21.0, 46.0, 25.0, 8.0),
            mean_intensity=0.61,
            polarization_pct=38.0,
            novel_claim_pct=12.5,
            trajectory="declining",
            trajectory_delta=-0.27,
            top_objection_key="switching-cost",
        ),
        sentiment_timeline=[
            TimelinePoint(
                round_number=1,
                valence=_interval(-0.08, 0.21, 22),
                stance=_stance(30.0, 31.0, 32.0, 7.0),
                event_count=61,
                agent_count=22,
            ),
            TimelinePoint(
                round_number=2,
                valence=_interval(-0.21, 0.18, 23),
                stance=_stance(26.0, 38.0, 29.0, 7.0),
                event_count=70,
                agent_count=23,
            ),
            TimelinePoint(
                round_number=3,
                valence=_interval(-0.52, 0.16, 24),
                stance=_stance(15.0, 58.0, 21.0, 6.0),
                event_count=74,
                agent_count=24,
            ),
            # Nothing measurable happened here. It must not be drawn at zero.
            TimelinePoint(round_number=4, valence=UNMEASURED, stance=StanceSplit()),
            TimelinePoint(
                round_number=5,
                valence=_interval(-0.44, 0.17, 21),
                stance=_stance(18.0, 52.0, 22.0, 8.0),
                event_count=58,
                agent_count=21,
            ),
        ],
        by_platform=[
            PlatformSlice(
                platform="reddit",
                valence=_interval(-0.58, 0.15, 19),
                stance=_stance(12.0, 61.0, 21.0, 6.0),
                event_count=118,
                agent_count=19,
                top_objection_keys=["switching-cost"],
            ),
            PlatformSlice(
                platform="hacker_news",
                valence=_interval(-0.19, 0.24, 14),
                stance=_stance(29.0, 34.0, 30.0, 7.0),
                event_count=87,
                agent_count=14,
            ),
            # Configured but silent. Absent from every chart.
            PlatformSlice(platform="linkedin", valence=UNMEASURED, stance=StanceSplit()),
        ],
        by_archetype=[
            ArchetypeSlice(
                archetype="Incumbent power user",
                valence=_interval(-0.63, 0.14, 11),
                stance=_stance(9.0, 68.0, 18.0, 5.0),
                agent_count=11,
            ),
            ArchetypeSlice(
                archetype="Growth-stage buyer",
                valence=_interval(-0.12, 0.22, 12),
                stance=_stance(33.0, 30.0, 30.0, 7.0),
                agent_count=12,
            ),
            # One agent is an anecdote; the band spans the whole scale.
            ArchetypeSlice(
                archetype="Skeptical CFO",
                valence=Interval(mean=-0.4, lower=-1.0, upper=1.0, n=1),
                stance=_stance(0.0, 100.0, 0.0, 0.0),
                agent_count=1,
            ),
        ],
        by_cohort=[
            CohortSlice(
                cohort="buyer",
                valence=_interval(-0.18, 0.21, 15),
                stance=_stance(29.0, 33.0, 31.0, 7.0),
                agent_count=15,
                agents_total=16,
                archetypes=["Growth-stage buyer", "Skeptical CFO"],
            ),
            CohortSlice(
                cohort="adversarial",
                valence=_interval(-0.66, 0.13, 9),
                stance=_stance(6.0, 71.0, 18.0, 5.0),
                agent_count=9,
                agents_total=9,
                archetypes=["Incumbent power user"],
            ),
        ],
        objections=[
            ObjectionSummary(
                key="switching-cost",
                label="Migration cost is not worth the gain",
                summary="Agents priced the migration in weeks of engineering time.",
                quotes=[
                    ObjectionQuote(
                        event_id="e-1",
                        agent_username="dana_ops",
                        archetype="Incumbent power user",
                        platform="reddit",
                        round_number=2,
                        text="Three weeks of migration for a 10% gain is not a trade I can defend.",
                    ),
                    ObjectionQuote(
                        event_id="e-2",
                        agent_username="rk_platform",
                        archetype="Growth-stage buyer",
                        platform="hacker_news",
                        round_number=3,
                        text="We'd need the whole quarter. Who is paying for that?",
                    ),
                ],
                event_ids=["e-1", "e-2"],
                agent_count=14,
                event_count=31,
                first_round_seen=1,
                originating_cohort="adversarial",
                cohort_spread={"Incumbent power user": 0.72, "Growth-stage buyer": 0.41},
                originated_adversarial=True,
                adversarial_agent_count=8,
                buyer_agent_count=6,
                mean_intensity=0.71,
                load_bearing_score=8.4,
            ),
            ObjectionSummary(
                key="pricing-opacity",
                label="Pricing is opaque above the published tier",
                summary="Nobody could state what an enterprise seat costs.",
                quotes=[
                    ObjectionQuote(
                        event_id="e-3",
                        agent_username="finops_lin",
                        archetype="Skeptical CFO",
                        platform="reddit",
                        round_number=3,
                        text="The pricing page stops exactly where my question starts.",
                    )
                ],
                event_ids=["e-3"],
                agent_count=9,
                event_count=17,
                first_round_seen=2,
                originating_cohort="buyer",
                mean_intensity=0.58,
                load_bearing_score=5.1,
            ),
            ObjectionSummary(
                key="support-depth",
                label="Support depth is unproven at this size",
                agent_count=5,
                event_count=8,
                first_round_seen=3,
                mean_intensity=0.44,
                load_bearing_score=2.2,
            ),
        ],
        flashpoints=[
            Flashpoint(
                round_number=3,
                valence_before=-0.21,
                valence_after=-0.52,
                delta=-0.31,
                significant=True,
                trigger_event_ids=["e-1"],
                objection_keys=["switching-cost"],
                description="Sentiment fell 0.31 between round 2 and 3.",
            ),
            Flashpoint(
                round_number=5,
                valence_before=-0.52,
                valence_after=-0.44,
                delta=0.08,
                significant=False,
                objection_keys=["pricing-opacity"],
            ),
        ],
        adversarial=AdversarialDisclosure(
            enabled=True,
            share_configured=0.35,
            share_realised=0.36,
            agents_total=9,
            agents_active=9,
            archetypes=["Incumbent power user"],
            roles={"incumbent_power_user": 6, "switching_cost_hawk": 3},
            named_competitors=[],
            # Verbatim from `analysis_builder._adversarial_disclosure` for these
            # counts. It is copied rather than composed because this fixture has
            # no `RunData`, so it is the one string here that can drift silently
            # — `test_report_vocabulary` runs the real composer for that reason.
            disclosure=(
                "9 of 25 people in this run (36%) were built to argue against "
                "you: they are happy with what they already use, and they push "
                "back on switching by construction. They are synthetic, like "
                "everyone else in this run, and what they said is reported "
                "separately from the buyers' so the headline can be read either "
                "way. No rival was named: they argue about the category and the "
                "cost of switching, with no real company involved."
            ),
        ),
        scoreboard=scoreboard,
        quality=QualityBlock(
            events_total=318,
            events_measured=263,
            coverage_pct=82.7,
            agents_total=25,
            agents_active=24,
            rounds=5,
            measurement_model="claude-haiku-4-5",
            mean_ci_width=0.37,
            confidence="moderate",
            caveats=[
                "24 people produced measurable opinions. Intervals are wide at "
                "this size — treat differences smaller than the bands as unresolved.",
                "36% of the room was built to argue against you and pushes back on "
                "switching by construction. The headline includes them; the "
                "breakdown further down separates them out.",
            ],
        ),
    )


def _variant(key: str, label: str, rate: float, half: float, n: int) -> VariantScore:
    return VariantScore(
        variant_key=key,
        label=label,
        content=f"Copy for {label}",
        objective_rate=_interval(rate, half, n),
        valence=_interval(-0.2, 0.2, n),
        stance=_stance(30.0, 34.0, 29.0, 7.0),
        virality=ViralityComponents(
            score=61.0, components_used=4, components_total=6,
            share_intent_rate=_interval(0.22, 0.09, n),
            cross_archetype_reach=0.6, archetypes_reached=3, archetypes_total=4,
        ),
        agent_count=n,
        event_count=n * 3,
    )


def make_scoreboard(*, with_winner: bool) -> VariantScoreboard:
    variants = [
        _variant("v1", "Cost-first framing", 0.41, 0.06 if with_winner else 0.14, 24),
        _variant("v2", "Speed-first framing", 0.24, 0.06 if with_winner else 0.14, 24),
        _variant("v3", "Risk-first framing", 0.19, 0.06 if with_winner else 0.14, 24),
    ]
    if with_winner:
        return VariantScoreboard(
            objective="book a demo",
            objective_intents=["book_demo"],
            variants=variants,
            winner_variant_key="v1",
            verdict=(
                "Cost-first framing leads: people were 17.0% more likely to "
                "convert on it than on Speed-first framing (95% interval 4.0% to "
                "30.0%, 9 of 24 people behaved differently between the two)."
            ),
            paired=PairedComparison(
                top_variant_key="v1",
                against_variant_key="v2",
                shared_agents=24,
                discordant_agents=9,
                mean_difference=0.17,
                lower=0.04,
                upper=0.30,
                separates=True,
            ),
            unpaired_winner_variant_key="v1",
            unpaired_verdict="Same answer under the previous rule.",
        )
    return VariantScoreboard(
        objective="book a demo",
        objective_intents=["book_demo"],
        variants=variants,
        winner_variant_key=None,
        verdict=(
            "No winner: Cost-first framing leads Speed-first framing by 17.0% "
            "per person, but the 95% interval (-6.0% to 40.0%) includes zero."
        ),
        paired=PairedComparison(
            top_variant_key="v1",
            against_variant_key="v2",
            shared_agents=24,
            discordant_agents=5,
            mean_difference=0.17,
            lower=-0.06,
            upper=0.40,
            separates=False,
        ),
        unpaired_winner_variant_key=None,
        unpaired_verdict="No separation under the previous rule either.",
    )


SECTION_MARKDOWN = """\
## What the room actually did

The migration-cost objection is **load-bearing**: it appeared in round 1 and had
crossed into buyers by round 3.

**Reddit carried the decline; Hacker News did not follow.**

| Platform | Mean sentiment | 95% CI | People |
| --- | --- | --- | --- |
| Reddit | -0.58 | -0.73 to -0.43 | 19 |
| Hacker News | -0.19 | -0.43 to 0.05 | 14 |

Three things follow:

- Cost framing has to land before round 2.
- The finance buyer is unresolved at this size.
- Support depth never became load-bearing.

> The pricing page stops exactly where my question starts.
"""
