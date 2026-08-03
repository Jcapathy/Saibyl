# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# estimate_simulation_cost(agent_count, rounds, platforms=1, variants=1,
#                          action_model=None) -> SimulationCostEstimate
# check_agent_budget(org_id, agent_count, rounds, ...) -> BudgetCheck
# deduct_agent_credits(org_id, agent_rounds) -> None
# ─────────────────────────────────────────────────────────
"""Run cost estimation and budget enforcement.

Cost is derived from a per-stage token profile priced against the real model
rates in model_pricing, not from a single flat per-agent-round constant. The
previous constant (0.000017 USD) understated the true cost of an Opus-backed
agent action by roughly 440x, which meant every run was quoted far below what
it cost to serve.

The token profiles below are conservative starting estimates. Once llm_usage
has real data, recalibrate them from measured medians — that is the whole
point of the ledger.
"""
from __future__ import annotations

from decimal import Decimal
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


# ---------------------------------------------------------------------------
# Per-stage token profiles
# ---------------------------------------------------------------------------

class _StageProfile(BaseModel):
    """Expected tokens for one unit of work in a pipeline stage."""

    input_tokens: int
    output_tokens: int


# One agent action: persona + feed slice + memory in, a single action line out.
AGENT_ACTION = _StageProfile(input_tokens=1000, output_tokens=120)

# One agent generated during the prepare phase.
AGENT_GENERATION = _StageProfile(input_tokens=1200, output_tokens=350)

# Per-event measurement, batched ~25 events per call — hence the small
# per-event share.
EVENT_MEASUREMENT = _StageProfile(input_tokens=140, output_tokens=40)

# Report generation, per section (ReACT tool calls plus the write-up).
REPORT_SECTION = _StageProfile(input_tokens=18000, output_tokens=2500)


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
    agent_rounds: int
    llm_calls: int
    actual_cost_usd: float
    retail_cost_usd: float
    margin_pct: float
    breakdown: dict[str, float]


class BudgetCheck(BaseModel):
    allowed: bool
    agent_rounds_requested: int
    plan_allowance_remaining: int
    credits_remaining: int
    covered_by_plan: bool
    covered_by_credits: bool
    estimated_cost_usd: float
    message: str


# Plan allowances, in agent-rounds per month.
PLAN_ALLOWANCES = {
    "starter": 150_000,
    "pro": 7_500_000,
    "enterprise": 50_000_000,
}


def estimate_simulation_cost(
    agent_count: int,
    rounds: int,
    platforms: int = 1,
    variants: int = 1,
    action_model: str | None = None,
) -> SimulationCostEstimate:
    """Estimate what a run will cost to serve, and what to charge for it.

    Agent actions run on the fast model by default: they are the highest-volume
    stage by an order of magnitude, and the per-call judgment required is low.
    """
    if agent_count > MAX_AGENTS:
        raise ValueError(f"Agent count cannot exceed {MAX_AGENTS:,}")
    if agent_count <= 0 or rounds <= 0:
        raise ValueError("Agent count and rounds must be positive")
    if platforms <= 0 or variants <= 0:
        raise ValueError("Platforms and variants must be positive")

    fast_model = action_model or settings.llm_fast_model
    main_model = settings.llm_model

    # Every agent acts once per platform per round, in each variant arena.
    action_units = agent_count * rounds * platforms * variants
    # Agents are generated once and reused across variants — that reuse is what
    # makes matched-swarm comparison valid in the first place.
    generation_units = agent_count
    # Not every action produces an event; roughly 80% do (some yield NOTHING).
    measurement_units = int(action_units * 0.8)
    section_units = min(7, max(4, measurement_units // 30 + 2))

    action_cost = _stage_cost(AGENT_ACTION, action_units, fast_model)
    generation_cost = _stage_cost(AGENT_GENERATION, generation_units, fast_model)
    measurement_cost = _stage_cost(EVENT_MEASUREMENT, measurement_units, fast_model)
    report_cost = _stage_cost(REPORT_SECTION, section_units, main_model)

    actual = action_cost + generation_cost + measurement_cost + report_cost

    # Price to the target margin, then enforce the floor.
    retail = actual / (Decimal("1") - TARGET_MARGIN_PCT / Decimal("100"))
    floor = actual / (Decimal("1") - MIN_MARGIN_PCT / Decimal("100"))
    retail = max(retail, floor)

    margin = (
        (retail - actual) / retail * Decimal("100") if retail > 0 else Decimal("0")
    )

    return SimulationCostEstimate(
        agent_count=agent_count,
        rounds=rounds,
        platforms=platforms,
        variants=variants,
        agent_rounds=agent_count * rounds,
        llm_calls=action_units + generation_units + section_units,
        actual_cost_usd=float(actual),
        retail_cost_usd=float(retail),
        margin_pct=float(round(margin, 2)),
        breakdown={
            "agent_actions": float(action_cost),
            "agent_generation": float(generation_cost),
            "event_measurement": float(measurement_cost),
            "report": float(report_cost),
        },
    )


def check_agent_budget(
    org_id: UUID,
    agent_count: int,
    rounds: int,
    platforms: int = 1,
    variants: int = 1,
) -> BudgetCheck:
    """Check whether an org can afford a run.

    Both sides of the allowance comparison are agent-rounds. The previous
    implementation compared requested agent-rounds against
    usage_records.simulations_run — a count of simulations — so the check was
    meaningless: an org that had run 3 simulations was treated as having
    consumed 3 agent-rounds.
    """
    admin = get_supabase_admin()

    org = admin.table("organizations").select(
        "plan, agent_credits_balance"
    ).eq("id", str(org_id)).single().execute().data

    plan = org.get("plan", "starter")
    credits = org.get("agent_credits_balance", 0) or 0
    allowance = PLAN_ALLOWANCES.get(plan, 0)

    agent_rounds = agent_count * rounds
    estimate = estimate_simulation_cost(agent_count, rounds, platforms, variants)

    used_this_month = _agent_rounds_used_this_month(org_id)
    remaining_allowance = max(0, allowance - used_this_month)

    covered_by_plan = agent_rounds <= remaining_allowance
    covered_by_credits = (not covered_by_plan) and credits >= agent_rounds
    allowed = covered_by_plan or covered_by_credits

    if allowed:
        msg = "Covered by your plan" if covered_by_plan else "Will use agent credits"
    else:
        msg = (
            f"Insufficient budget. Need {agent_rounds:,} agent-rounds, "
            f"have {remaining_allowance + credits:,} available."
        )

    return BudgetCheck(
        allowed=allowed,
        agent_rounds_requested=agent_rounds,
        plan_allowance_remaining=remaining_allowance,
        credits_remaining=credits,
        covered_by_plan=covered_by_plan,
        covered_by_credits=covered_by_credits,
        estimated_cost_usd=estimate.retail_cost_usd,
        message=msg,
    )


def _agent_rounds_used_this_month(org_id: UUID) -> int:
    """Sum agent-rounds consumed by this org's simulations in the current month."""
    from datetime import datetime

    admin = get_supabase_admin()
    month_start = datetime.now().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    ).isoformat()

    try:
        rows = (
            admin.table("simulations")
            .select("agent_rounds_consumed")
            .eq("organization_id", str(org_id))
            .gte("created_at", month_start)
            .execute()
        ).data or []
    except Exception:
        logger.exception("agent_rounds_lookup_failed", org_id=str(org_id))
        # Fail closed on the allowance side rather than granting free capacity.
        return 0

    return sum(int(r.get("agent_rounds_consumed") or 0) for r in rows)


def deduct_agent_credits(org_id: UUID, agent_rounds: int) -> None:
    """Deduct agent-rounds from an org's credit balance atomically."""
    if agent_rounds <= 0:
        return

    admin = get_supabase_admin()
    admin.rpc("deduct_agent_credits", {
        "org_uuid": str(org_id),
        "amount": agent_rounds,
    }).execute()

    logger.info("agent_credits_deducted", org_id=str(org_id), deducted=agent_rounds)
