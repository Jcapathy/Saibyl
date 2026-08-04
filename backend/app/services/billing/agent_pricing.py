# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# estimate_simulation_cost(agent_count, rounds, platforms=1, variants=1,
#                          depth="standard", action_model=None)
#                                              -> SimulationCostEstimate
# report_section_count(measured_events, depth="standard") -> int
# credits_for(cost_usd) -> int
# tier_caps(plan) -> RunCaps
# check_credit_budget(org_id, agent_count, rounds, ...) -> BudgetCheck
# estimate_icp_synthesis_cost() -> SynthesisCostEstimate
# check_synthesis_budget(org_id) -> BudgetCheck
# deduct_credits(org_id, credits) -> None
# CREDITS_PER_USD, TIER_CREDIT_GRANTS, STANDARD_RUN
# ─────────────────────────────────────────────────────────
"""Run cost estimation, credit accounting, and budget enforcement.

Cost is derived from a per-stage token profile priced against the real model
rates in model_pricing, not from a single flat per-agent-round constant. The
previous constant (0.000017 USD) understated the true cost of an Opus-backed
agent action by roughly 440x, which meant every run was quoted far below what
it cost to serve.

**Credits, not agent-rounds, are the metered unit** (DECISIONS_V2 §15b). An
agent-round allowance rations nothing: a run varies by 56x in cost across the
tier caps, so "30 runs" is anywhere from $65 to $5,445 of COGS. One credit is
$0.001 of measured COGS, which makes the balance an integer and makes a grant
mean the same thing at every run shape.

The token profiles below are conservative starting estimates. Once llm_usage
has real data, recalibrate them from measured medians — that is the whole
point of the ledger.
"""
from __future__ import annotations

from decimal import ROUND_CEILING, Decimal
from functools import lru_cache
from uuid import UUID

import structlog
from pydantic import BaseModel

from app.core.config import settings
from app.core.database import get_supabase_admin
from app.services.billing.model_pricing import cost_usd

logger = structlog.get_logger()

MAX_AGENTS = 1_000_000

# Minimum gross margin. A quote that would fall below this is raised to meet
# it, so a pricing mistake can never result in serving a run at a loss.
MIN_MARGIN_PCT = Decimal("70")
TARGET_MARGIN_PCT = Decimal("80")

# Retained for backwards compatibility with existing callers/tests. Derived
# from the real profile rather than hardcoded.
MARKUP_MULTIPLIER = Decimal("100") / (Decimal("100") - TARGET_MARGIN_PCT)  # 5.0x at 80%

# One credit is $0.001 of COGS. Milli-dollars rather than dollars so a balance
# is an integer: a float balance that drifts by a cent per deduction produces
# support tickets nobody can reproduce.
CREDITS_PER_USD = 1_000

# The reference run every advertised run count is quoted against. Never print a
# run count without this definition attached — PRICING_GUIDE.md §1.5.
STANDARD_RUN = (100, 5, 2, 1)  # agents, rounds, platforms, variants

# Monthly grants, in credits. These are the PRD §8 COGS grants converted at
# CREDITS_PER_USD: Founder $19.80, Growth $59.80, Agency $199.80. Both the V1
# plan names still in the database and the V2 tier names are mapped, because
# the Stripe tier migration is separate work — see ARCHITECTURE_V2.md.
#
# The free grant follows the cost of one free run, because a grant that does not
# cover one makes the tier unusable — the user hits "not enough credits" on the
# only run they were promised.
#
# It has moved twice for that reason. The PRD projected $0.35; with depth
# scaling and objection canonicalization priced it came out at $0.75, so the
# grant went to 800. The 2026-08-03 recalibration — the report writes six
# sections and was quoted for four — took a 25-agent run to **$1.18**, which
# 800 credits does not cover. Now 1,200, which leaves headroom rather than
# tracking the cost exactly, because this number failing is a broken signup and
# the saving from cutting it fine is $0.02 a trial.
#
# The report and the canonicalizer are both main-model stages that barely shrink
# with run size, so they dominate a very small run. That is why the free tier is
# the most sensitive of all of them to a report-stage repricing.
TIER_CREDIT_GRANTS = {
    "free": 1_200,
    "trial": 1_200,
    "founder": 19_800,
    "starter": 19_800,
    "growth": 59_800,
    "pro": 59_800,
    "agency": 199_800,
    "enterprise": 199_800,
}


class RunCaps(BaseModel):
    """Maximum run shape a tier may configure.

    Caps exist to stop accidents, not to ration — the credit balance rations.
    Rationing by caps would punish the user for the system's inability to price,
    and the Run Configurator prices every shape before commit.
    """

    max_agents: int
    max_rounds: int
    max_platforms: int
    max_variants: int


# Intended caps once N-way matched swarms exist. Not what a customer can
# configure today — see MAX_RUNNABLE_VARIANTS.
TIER_CAPS = {
    "free": RunCaps(max_agents=25, max_rounds=3, max_platforms=2, max_variants=1),
    "trial": RunCaps(max_agents=25, max_rounds=3, max_platforms=2, max_variants=1),
    "founder": RunCaps(max_agents=100, max_rounds=8, max_platforms=3, max_variants=3),
    "starter": RunCaps(max_agents=100, max_rounds=8, max_platforms=3, max_variants=3),
    "growth": RunCaps(max_agents=150, max_rounds=10, max_platforms=4, max_variants=5),
    "pro": RunCaps(max_agents=150, max_rounds=10, max_platforms=4, max_variants=5),
    "agency": RunCaps(max_agents=250, max_rounds=12, max_platforms=6, max_variants=8),
    "enterprise": RunCaps(max_agents=1_000, max_rounds=20, max_platforms=12, max_variants=8),
}

# How many variant arenas the engine can actually run. **One.**
#
# The cost model prices variants correctly — action cost scales with them,
# generation cost does not — but nothing executes more than one arena:
# `run_prepare_agents` assigns every agent variant "a", the runner never
# branches on variant, and `run_simulation_ab` calls `run_simulation` once.
#
# Quoting a 4-variant run therefore charges four times the agent-action cost
# for one arena's worth of work. That is billing for compute that is never
# performed, so the cap is enforced here rather than left to the caller.
#
# **Phase 3 raises this to 8** when N-way matched swarms ship. That is the only
# change needed — TIER_CAPS above already holds the intended per-tier values.
MAX_RUNNABLE_VARIANTS = 1

_DEFAULT_PLAN = "starter"


def tier_caps(plan: str | None) -> RunCaps:
    """The run shape a tier may configure, clamped to what the engine can run."""
    caps = TIER_CAPS.get((plan or _DEFAULT_PLAN).lower(), TIER_CAPS[_DEFAULT_PLAN])
    if caps.max_variants <= MAX_RUNNABLE_VARIANTS:
        return caps
    return caps.model_copy(update={"max_variants": MAX_RUNNABLE_VARIANTS})


def tier_grant(plan: str | None) -> int:
    return TIER_CREDIT_GRANTS.get(
        (plan or _DEFAULT_PLAN).lower(), TIER_CREDIT_GRANTS[_DEFAULT_PLAN]
    )


def credits_for(cost_usd: Decimal | float) -> int:
    """Convert COGS dollars to credits, always rounding up.

    Rounding up rather than to nearest: a run that costs a fraction of a credit
    more than it charges is a run served at a loss, and at volume the rounding
    direction is the difference between the margin floor holding and not.
    """
    amount = Decimal(str(cost_usd)) * CREDITS_PER_USD
    return int(amount.to_integral_value(rounding=ROUND_CEILING))


# ---------------------------------------------------------------------------
# Per-stage token profiles
# ---------------------------------------------------------------------------

class _StageProfile(BaseModel):
    """Expected tokens for one unit of work in a pipeline stage."""

    input_tokens: int
    output_tokens: int


# ---------------------------------------------------------------------------
# MEASURED from the `llm_usage` ledger, 2026-08-02, across two live runs:
# 25 agents / 3 rounds / 2 platforms, and the reference standard run
# (100 / 5 / 2 / 1). Figures are per unit of work, calibrated at the standard
# shape. Re-derive with the query in HANDOFF.md §5 whenever prompts change —
# every prompt edit in this codebase moves these.
# ---------------------------------------------------------------------------

# One agent action: persona + feed slice + memory in, a single action line out.
#
# This is the one profile that visibly scales with run size — 404 input tokens
# per action at 25 agents, 748 at 100 — because the feed and the agent's own
# memory both grow. It should plateau rather than keep climbing: adapters slice
# the feed to the top 8 posts and memory to the last 10 actions, so there is a
# ceiling. Calibrated at the standard shape, which means small runs are
# over-quoted (safe) and very large ones may be under-quoted — which is what
# `reconcile_run_cost`'s margin-floor check exists to catch.
#
# **Deliberately not recalibrated** from the first Founder-lens run, which
# measured 312 in / 175 out at the same nominal shape — 2.4x lower on input.
# The cause is the platform mix, not a shifted mean: that run used Hacker News
# and LinkedIn, whose feed slice is a compact `[id] title (points)` line per
# post, where the Phase 1 calibration ran on adapters that put post bodies in
# the feed. Calibrating down to 312 would under-quote every Twitter and Reddit
# run to make Hacker News runs exact. 750 over-quotes the compact adapters,
# which is the safe direction.
#
# The real fix is a per-adapter profile. Until then this number is a ceiling
# across platforms rather than an average of them, and that is on purpose.
AGENT_ACTION = _StageProfile(input_tokens=750, output_tokens=170)

# One agent generated during the prepare phase. Measured at 1,901/548 and
# 1,900/537 on the two Phase 1 runs — constant, as expected: the prompt is one
# archetype plus a fixed slice of document context.
#
# **Deliberately not recalibrated** from the Founder-lens run's 1,459 / 376. The
# input is document-dependent — the prompt carries `doc_context[:2000]`, and
# that project's two short Markdown files do not fill the slice the way a PDF
# deck does. The output is tail-heavy rather than low-mean: the same run had a
# profile truncate at 900 tokens against a 376-token mean, which is why the
# ceiling moved to 1,400. Calibrating to the mean of a thin-document run would
# under-quote every project that uploads a real deck.
AGENT_GENERATION = _StageProfile(input_tokens=1900, output_tokens=550)

# Per-event measurement, batched ~25 events per call. Output was badly
# under-estimated: the classifier returns six fields per event including an
# objections array, which costs more than the 40 tokens originally assumed.
EVENT_MEASUREMENT = _StageProfile(input_tokens=78, output_tokens=87)

# Objection canonicalization: one main-model call over the run's distinct
# objection phrasings, charged once per run. Its input is the number of
# *distinct* phrasings, which grows with run size but far slower than events do
# — 124 distinct from 72 events, 601 from 497, 728 from 480 on a Founder-lens
# run with an adversarial cohort.
#
# The cohort is why this moved: incumbent-aligned agents raise objections buyers
# never do, so a Founder-lens run generates materially more distinct phrasings
# at the same event count.
#
# Measured on the first live Founder-lens run at 13,950 in / 8,000 out — but the
# **output was capped**, so 8,000 is a floor and not a measurement. Priced here
# at 10,000 out, above the observed cap and below the raised 16,000 ceiling.
# Re-derive from `llm_usage` after the next run, when the output is free to find
# its own level.
OBJECTION_CANONICALIZATION = _StageProfile(input_tokens=14000, output_tokens=10000)

# ICP synthesis: one main-model pass over the founder's uploaded material,
# charged once per synthesis rather than per run.
#
# **ESTIMATED, not measured** — unlike every profile above it, which came out of
# `llm_usage`. Input is the material budget in icp_synthesizer (24k characters
# of the team's own material, 12k of competitor material, 6k of market context,
# plus the pack catalogue and the schema) at roughly 3.6 characters per token.
# Output is a whole profile: up to six buyer archetypes and four adversarial
# ones, each with seven or eight list fields.
#
# Re-derive from the ledger after the first live Founder-lens runs, with the
# query in HANDOFF.md §7. Until then this is the one stage in the model whose
# quote has not been checked against reality, and it is priced deliberately
# toward the high side — an over-quoted stage costs a customer credits they can
# see, while an under-quoted one is served at a loss nobody notices.
ICP_SYNTHESIS = _StageProfile(input_tokens=14_000, output_tokens=4_500)

# Inoculation asset drafting: one main-model pass over a run's top objections
# with their verbatim quotes, producing two publishable assets per objection.
#
# **ESTIMATED, not measured**, like ICP synthesis. Input is up to six objections
# with four quotes each plus the schema; output is up to twelve assets of
# 80–250 words with a hypothesis apiece. Re-derive from `llm_usage` after the
# first live loop — the stage is already attributed as `inoculation_draft`, so
# the data will be there.
INOCULATION_DRAFT = _StageProfile(input_tokens=4_500, output_tokens=5_000)

# Report generation, per **written** section (ReACT tool calls plus the
# write-up). The loop's evidence is capped — the seeded artifact at 6,000
# characters and each tool observation at 5,000 — so a section's context cannot
# run away.
#
# Recalibrated from the first live Founder-lens run: 8 Opus calls, 44,603 in /
# 25,917 out across 6 written sections = 7,434 / 4,320 each. The previous
# 5,650 / 4,250 was derived per *priced* section, and the two counts were not
# the same number — see REPORT_FIXED_SECTIONS.
REPORT_SECTION = _StageProfile(input_tokens=7450, output_tokens=4320)

# Sections the report writes on top of its outline: an executive summary and a
# conclusion ("Strategic Implications & Recommended Actions"). Both are
# main-model calls of ordinary section length; neither comes out of
# `report_section_count`.
#
# **Found by the first live Founder-lens run.** `report_section_count(480,
# "standard")` returned 4, the outline produced 4 sections, and the report then
# wrote 6 — so a third of the largest main-model stage in the run was never
# quoted. This is the same defect as Phase 1's #9 and #10 one level up: not the
# report being written at the wrong depth, nor its spend going unmetered, but
# the *unit count* in the quote disagreeing with what the writer actually does.
REPORT_FIXED_SECTIONS = 2


def _stage_cost(profile: _StageProfile, units: int, model: str) -> Decimal:
    return cost_usd(
        model,
        input_tokens=profile.input_tokens * units,
        output_tokens=profile.output_tokens * units,
    )


class SimulationCostEstimate(BaseModel):
    agent_count: int
    rounds: int
    platforms: int
    variants: int
    depth: str
    agent_rounds: int
    llm_calls: int
    report_sections: int
    actual_cost_usd: float
    retail_cost_usd: float
    credits: int
    margin_pct: float
    breakdown: dict[str, float]
    # How many standard runs' worth of capacity this shape consumes. Required
    # by PRICING_GUIDE.md §1.3 — the honesty line that stops a user who bought
    # "18 runs" from discovering afterwards that one run ate nine of them.
    standard_run_equivalents: float


class BudgetCheck(BaseModel):
    allowed: bool
    credits_required: int
    credits_remaining: int
    credits_after: int
    # Share of the remaining balance this run consumes; drives the >30% warning.
    balance_share_pct: float
    estimated_cost_usd: float
    retail_price_usd: float
    message: str


DEPTH_PRESETS = ("brief", "standard", "deep")

# Events below which a report gets N sections. V1 used
# `min(7, max(4, event_count // 30 + 2))`; the floor of 4 meant a 25-agent free
# run still generated 6 Opus-written sections — $1.07 of that run's $1.27 total,
# 84% of the cost of a run whose whole purpose is to be nearly free. Depth now
# scales down as well as up.
_SECTION_THRESHOLDS = ((150, 2), (400, 3), (900, 4), (1800, 5), (3500, 6))
_MAX_SECTIONS = 7
_MIN_SECTIONS = 2


def report_section_count(measured_events: int, depth: str = "standard") -> int:
    """Sections a report should have for a run of this size.

    A 25-agent run has 2 sections' worth to say. Writing 6 does not make it
    say more; it makes the same finding restated at Opus prices.
    """
    sections = _MAX_SECTIONS
    for threshold, count in _SECTION_THRESHOLDS:
        if measured_events < threshold:
            sections = count
            break
    if depth == "brief":
        sections -= 1
    elif depth == "deep":
        sections += 1
    return max(_MIN_SECTIONS, min(_MAX_SECTIONS, sections))


def estimate_simulation_cost(
    agent_count: int,
    rounds: int,
    platforms: int = 1,
    variants: int = 1,
    depth: str = "standard",
    action_model: str | None = None,
    reuse_agents: bool = False,
) -> SimulationCostEstimate:
    """Estimate what a run will cost to serve, and what to charge for it.

    Agent actions run on the fast model by default: they are the highest-volume
    stage by an order of magnitude, and the per-call judgment required is low.

    `reuse_agents` drops the generation stage entirely. Set for an inoculation
    re-simulation, whose agents are copied from its parent rather than generated
    — the run makes zero generation calls, so quoting for them would be billing
    for compute that is never performed.
    """
    if agent_count > MAX_AGENTS:
        raise ValueError(f"Agent count cannot exceed {MAX_AGENTS:,}")
    if agent_count <= 0 or rounds <= 0:
        raise ValueError("Agent count and rounds must be positive")
    if platforms <= 0 or variants <= 0:
        raise ValueError("Platforms and variants must be positive")
    if depth not in DEPTH_PRESETS:
        raise ValueError(f"depth must be one of {DEPTH_PRESETS}")

    breakdown, action_units, generation_units, section_units = _stage_costs(
        agent_count, rounds, variants, depth, action_model, reuse_agents
    )
    action_cost = breakdown["agent_actions"]
    generation_cost = breakdown["agent_generation"]
    measurement_cost = breakdown["event_measurement"]
    canonicalization_cost = breakdown["objection_canonicalization"]
    report_cost = breakdown["report"]
    actual = sum(breakdown.values(), Decimal("0"))

    # Price to the target margin, then enforce the floor.
    retail = actual / (Decimal("1") - TARGET_MARGIN_PCT / Decimal("100"))
    floor = actual / (Decimal("1") - MIN_MARGIN_PCT / Decimal("100"))
    retail = max(retail, floor)

    margin = (
        (retail - actual) / retail * Decimal("100") if retail > 0 else Decimal("0")
    )

    credits = credits_for(actual)
    standard_credits = _standard_run_credits()

    return SimulationCostEstimate(
        agent_count=agent_count,
        rounds=rounds,
        platforms=platforms,
        variants=variants,
        depth=depth,
        agent_rounds=agent_count * rounds,
        llm_calls=action_units + generation_units + section_units,
        report_sections=section_units,
        actual_cost_usd=float(actual),
        retail_cost_usd=float(retail),
        credits=credits,
        margin_pct=float(round(margin, 2)),
        breakdown={
            "agent_actions": float(action_cost),
            "agent_generation": float(generation_cost),
            "event_measurement": float(measurement_cost),
            "objection_canonicalization": float(canonicalization_cost),
            "report": float(report_cost),
        },
        standard_run_equivalents=round(credits / standard_credits, 2)
        if standard_credits
        else 0.0,
    )


def _stage_costs(
    agent_count: int,
    rounds: int,
    variants: int,
    depth: str,
    action_model: str | None = None,
    reuse_agents: bool = False,
) -> tuple[dict[str, Decimal], int, int, int]:
    """Cost of each pipeline stage for a run shape.

    The single place the unit counts are derived. They used to be written out
    twice — here and in the reference-run helper — and the two promptly drifted
    apart during recalibration, so a run's price and its "worth N standard runs"
    line were computed from different formulas.

    Note that `platforms` is absent: it does not appear in any unit count. The
    swarm is split across platforms rather than duplicated onto each, so adding
    a platform costs nothing and buys thinner coverage.
    """
    fast_model = action_model or settings.llm_fast_model
    main_model = settings.llm_model

    # Every agent acts once per round, in each variant arena. Measured: a
    # 100-agent, 5-round, 2-platform run made exactly 500 action calls, against
    # the 1,000 the old `× platforms` formula predicted. That multiplication
    # inflated the largest stage of every quote by the platform count, which is
    # most of why runs were being over-quoted roughly 2x.
    action_units = agent_count * rounds * variants
    # Agents are generated once and reused across variants — that reuse is what
    # makes matched-swarm comparison valid in the first place.
    #
    # An inoculation re-simulation reuses the *parent's* agents, copied row for
    # row, so it generates none at all. Charging for generation there would bill
    # for LLM calls the run provably never makes, and the honest quote is also
    # the one that makes the second run of the loop cheaper than the first —
    # which is exactly the right incentive for the step the product is sold on.
    generation_units = 0 if reuse_agents else agent_count
    # Nearly every action produces an event: measured 497 from 500. The old 80%
    # assumption came from agents answering NOTHING, which they now rarely do —
    # the action prompt states the subject and tells an agent facing an empty
    # feed to post.
    measurement_units = action_units
    section_units = report_section_count(measurement_units, depth)
    # What the writer actually produces: the outline's sections plus the
    # executive summary and the conclusion. Quoting `section_units` alone
    # under-counted the report by two Opus-written sections on every run.
    written_sections = section_units + REPORT_FIXED_SECTIONS

    breakdown = {
        "agent_actions": _stage_cost(AGENT_ACTION, action_units, fast_model),
        "agent_generation": _stage_cost(AGENT_GENERATION, generation_units, fast_model),
        "event_measurement": _stage_cost(EVENT_MEASUREMENT, measurement_units, fast_model),
        # Once per run, on the main model, regardless of run size.
        "objection_canonicalization": _stage_cost(OBJECTION_CANONICALIZATION, 1, main_model),
        "report": _stage_cost(REPORT_SECTION, written_sections, main_model),
    }
    return breakdown, action_units, generation_units, section_units


class SynthesisCostEstimate(BaseModel):
    """What one off-run main-model pass costs to serve, and what it charges.

    Its own object rather than a `SimulationCostEstimate` with zeroed fields:
    these passes have no agents, rounds, platforms or variants, and a
    shape-shaped estimate with 0 in every shape field invites a caller to price
    a run with it.
    """

    stage: str
    actual_cost_usd: float
    retail_cost_usd: float
    credits: int
    margin_pct: float
    standard_run_equivalents: float


def estimate_icp_synthesis_cost() -> SynthesisCostEstimate:
    """Price one ICP synthesis pass.

    Charged per synthesis, not per run. An ICP is a project-level object reused
    across every run in the project, so folding it into the run quote would
    charge the second run for work the first one did — and leaving it out of
    pricing altogether is Phase 1's bug #6, where objection canonicalization was
    24% of measured spend and 0% of the quote.
    """
    return _one_off_estimate(ICP_SYNTHESIS, "icp_synthesis")


def estimate_inoculation_draft_cost() -> SynthesisCostEstimate:
    """Price one asset-drafting pass.

    Also charged per pass rather than per run: a founder can draft assets,
    discard them, and draft again without ever paying for a re-simulation, and
    each of those passes is a main-model call that was actually made.
    """
    return _one_off_estimate(INOCULATION_DRAFT, "inoculation_draft")


def _one_off_estimate(profile: _StageProfile, stage: str) -> SynthesisCostEstimate:
    """Price a single main-model pass that is charged on its own."""
    actual = _stage_cost(profile, 1, settings.llm_model)

    retail = actual / (Decimal("1") - TARGET_MARGIN_PCT / Decimal("100"))
    floor = actual / (Decimal("1") - MIN_MARGIN_PCT / Decimal("100"))
    retail = max(retail, floor)
    margin = (retail - actual) / retail * Decimal("100") if retail > 0 else Decimal("0")

    credits = credits_for(actual)
    standard_credits = _standard_run_credits()

    return SynthesisCostEstimate(
        stage=stage,
        actual_cost_usd=float(actual),
        retail_cost_usd=float(retail),
        credits=credits,
        margin_pct=float(round(margin, 2)),
        standard_run_equivalents=round(credits / standard_credits, 2)
        if standard_credits
        else 0.0,
    )


_ONE_OFF_LABELS = {
    "icp_synthesis": "Synthesizing this ICP",
    "inoculation_draft": "Drafting these assets",
}


def check_one_off_budget(org_id: UUID, estimate: SynthesisCostEstimate) -> BudgetCheck:
    """Whether an org can afford a single off-run main-model pass."""
    balance, _granted, _plan = get_credit_balance(org_id)

    required = estimate.credits
    allowed = balance >= required
    share = round(required * 100 / balance, 2) if balance > 0 else 100.0
    label = _ONE_OFF_LABELS.get(estimate.stage, "This step")

    if allowed:
        msg = f"{label} uses {required:,} of your {balance:,} credits."
    else:
        msg = (
            f"Not enough credits. {label} needs {required:,}; "
            f"you have {balance:,}."
        )

    return BudgetCheck(
        allowed=allowed,
        credits_required=required,
        credits_remaining=balance,
        credits_after=max(0, balance - required),
        balance_share_pct=share,
        estimated_cost_usd=estimate.actual_cost_usd,
        retail_price_usd=estimate.retail_cost_usd,
        message=msg,
    )


def check_synthesis_budget(org_id: UUID) -> BudgetCheck:
    """Whether an org can afford an ICP synthesis, in credits."""
    return check_one_off_budget(org_id, estimate_icp_synthesis_cost())


def check_inoculation_draft_budget(org_id: UUID) -> BudgetCheck:
    """Whether an org can afford one asset-drafting pass, in credits."""
    return check_one_off_budget(org_id, estimate_inoculation_draft_cost())


@lru_cache(maxsize=1)
def _standard_run_credits() -> int:
    """Credit cost of the reference run, from the same formula as every quote.

    Derived rather than hardcoded: when the token profiles are recalibrated from
    measured usage, the "worth N standard runs" line moves with them instead of
    quietly describing a run shape that no longer costs that.
    """
    agents, rounds, _platforms, variants = STANDARD_RUN
    breakdown, *_ = _stage_costs(agents, rounds, variants, "standard")
    return credits_for(sum(breakdown.values(), Decimal("0")))


def get_credit_balance(org_id: UUID) -> tuple[int, int, str]:
    """Return (balance, granted, plan) for an org."""
    admin = get_supabase_admin()
    org = (
        admin.table("organizations")
        .select("plan, credits_balance, credits_granted")
        .eq("id", str(org_id))
        .single()
        .execute()
    ).data or {}

    plan = org.get("plan") or _DEFAULT_PLAN
    granted = int(org.get("credits_granted") or 0) or tier_grant(plan)
    return int(org.get("credits_balance") or 0), granted, plan


def check_credit_budget(
    org_id: UUID,
    agent_count: int,
    rounds: int,
    platforms: int = 1,
    variants: int = 1,
    depth: str = "standard",
    reuse_agents: bool = False,
) -> BudgetCheck:
    """Check whether an org can afford a run, in credits.

    This replaces the agent-round allowance check. That check compared two
    incompatible quantities — requested agent-rounds against
    `usage_records.simulations_run`, a count of *simulations* — so an org that
    had run 3 simulations was treated as having consumed 3 of its 150,000
    agent-rounds. Even with that arithmetic corrected, an agent-round allowance
    could not price a run whose cost varies 56x at constant agent-rounds
    depending on variants and platforms.
    """
    balance, _granted, _plan = get_credit_balance(org_id)
    estimate = estimate_simulation_cost(
        agent_count, rounds, platforms, variants, depth, reuse_agents=reuse_agents
    )

    required = estimate.credits
    allowed = balance >= required
    after = max(0, balance - required)
    share = round(required * 100 / balance, 2) if balance > 0 else 100.0

    if allowed:
        msg = f"This run uses {required:,} of your {balance:,} credits."
    else:
        msg = (
            f"Not enough credits. This run needs {required:,}; "
            f"you have {balance:,}."
        )

    return BudgetCheck(
        allowed=allowed,
        credits_required=required,
        credits_remaining=balance,
        credits_after=after,
        balance_share_pct=share,
        estimated_cost_usd=estimate.actual_cost_usd,
        retail_price_usd=estimate.retail_cost_usd,
        message=msg,
    )


def largest_affordable_run(
    org_id: UUID,
    agent_count: int,
    rounds: int,
    platforms: int,
    variants: int,
    depth: str = "standard",
) -> tuple[int, int, int, int] | None:
    """Biggest version of this shape that fits the balance, or None.

    Backs the "Reduce to fit my balance" action in PRICING_GUIDE §1.4, which
    turns a dead end into a run. Agents are shed first because they are the
    cheapest dimension to lose: halving the swarm widens the confidence bands
    but preserves the round structure and every variant comparison, whereas
    dropping a variant deletes a question the user asked.
    """
    balance, _granted, _plan = get_credit_balance(org_id)
    if balance <= 0:
        return None

    for candidate_variants in range(variants, 0, -1):
        for candidate_rounds in range(rounds, 0, -1):
            for candidate_agents in range(agent_count, 4, -5):
                estimate = estimate_simulation_cost(
                    candidate_agents, candidate_rounds, platforms,
                    candidate_variants, depth,
                )
                if estimate.credits <= balance:
                    return (
                        candidate_agents, candidate_rounds, platforms,
                        candidate_variants,
                    )
    return None


def deduct_credits(org_id: UUID, credits: int) -> None:
    """Deduct credits from an org's balance atomically."""
    if credits <= 0:
        return

    admin = get_supabase_admin()
    admin.rpc("deduct_credits", {
        "org_uuid": str(org_id),
        "amount": credits,
    }).execute()

    logger.info("credits_deducted", org_id=str(org_id), deducted=credits)
