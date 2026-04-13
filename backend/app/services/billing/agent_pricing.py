# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# estimate_simulation_cost(agent_count, rounds) -> SimulationCostEstimate
# check_agent_budget(org_id, agent_count, rounds) -> BudgetCheck
# deduct_agent_credits(org_id, agent_rounds) -> None
# ─────────────────────────────────────────────────────────
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import structlog
from pydantic import BaseModel

from app.core.database import get_supabase_admin

logger = structlog.get_logger()

COST_PER_AGENT_ROUND = Decimal("0.000017")
MARKUP_MULTIPLIER = Decimal("4.0")
MAX_AGENTS = 1_000_000

# Plan base allowances (agent-rounds per month)
PLAN_ALLOWANCES = {
    "starter": 150_000,       # 10,000 agents × 15 sims
    "pro": 7_500_000,         # 100,000 agents × 75 sims
    "enterprise": 50_000_000,  # effectively unlimited
}


class SimulationCostEstimate(BaseModel):
    agent_count: int
    rounds: int
    agent_rounds: int
    actual_cost_usd: float
    retail_cost_usd: float
    margin_pct: float = 75.0


class BudgetCheck(BaseModel):
    allowed: bool
    agent_rounds_requested: int
    plan_allowance_remaining: int
    credits_remaining: int
    covered_by_plan: bool
    covered_by_credits: bool
    estimated_cost_usd: float
    message: str


def estimate_simulation_cost(agent_count: int, rounds: int) -> SimulationCostEstimate:
    """Calculate estimated cost for a simulation run."""
    if agent_count > MAX_AGENTS:
        raise ValueError(f"Agent count cannot exceed {MAX_AGENTS:,}")
    if agent_count <= 0 or rounds <= 0:
        raise ValueError("Agent count and rounds must be positive")

    agent_rounds = agent_count * rounds
    actual_cost = agent_rounds * COST_PER_AGENT_ROUND
    retail_cost = actual_cost * MARKUP_MULTIPLIER

    return SimulationCostEstimate(
        agent_count=agent_count,
        rounds=rounds,
        agent_rounds=agent_rounds,
        actual_cost_usd=float(actual_cost),
        retail_cost_usd=float(retail_cost),
    )


def check_agent_budget(org_id: UUID, agent_count: int, rounds: int) -> BudgetCheck:
    """Check if an org can afford a simulation run."""
    admin = get_supabase_admin()

    org = admin.table("organizations").select(
        "plan, agent_credits_balance"
    ).eq("id", str(org_id)).single().execute().data

    plan = org.get("plan", "starter")
    credits = org.get("agent_credits_balance", 0) or 0
    allowance = PLAN_ALLOWANCES.get(plan, 0)

    # Get current month usage
    from datetime import datetime
    month = datetime.now().strftime("%Y-%m")
    usage = admin.table("usage_records").select(
        "simulations_run"
    ).eq("organization_id", str(org_id)).eq("month", month).execute().data

    used_this_month = 0
    if usage:
        used_this_month = usage[0].get("simulations_run", 0)

    agent_rounds = agent_count * rounds
    estimate = estimate_simulation_cost(agent_count, rounds)
    remaining_allowance = max(0, allowance - used_this_month)

    covered_by_plan = agent_rounds <= remaining_allowance
    covered_by_credits = (not covered_by_plan) and credits >= agent_rounds

    allowed = covered_by_plan or covered_by_credits

    if allowed:
        msg = "Covered by your plan" if covered_by_plan else "Will use agent credits"
    else:
        msg = f"Insufficient budget. Need {agent_rounds:,} agent-rounds, have {remaining_allowance + credits:,} available."

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


def deduct_agent_credits(org_id: UUID, agent_rounds: int) -> None:
    """Deduct agent-rounds from org's credit balance atomically."""
    admin = get_supabase_admin()
    admin.rpc("deduct_agent_credits", {
        "org_uuid": str(org_id),
        "amount": agent_rounds,
    }).execute()

    logger.info("agent_credits_deducted", org_id=str(org_id), deducted=agent_rounds)
