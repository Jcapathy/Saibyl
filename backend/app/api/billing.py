from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.auth import get_current_org
from app.services.billing.agent_pricing import (
    CREDITS_PER_USD,
    STANDARD_RUN,
    check_credit_budget,
    estimate_simulation_cost,
    get_credit_balance,
    largest_affordable_run,
    tier_caps,
)
from app.services.billing.run_quote import QuoteError, issue_quote
from app.services.billing.stripe_service import (
    create_checkout_session,
    create_customer_portal_session,
    create_flash_report_checkout,
    get_subscription_status,
    handle_webhook,
)

router = APIRouter(tags=["billing"])


class CheckoutRequest(BaseModel):
    plan: str  # starter | pro | enterprise


class FlashReportCheckoutRequest(BaseModel):
    report_type: str  # quick_read | deep_dive | war_room_brief


class RunShape(BaseModel):
    """A run configuration to be priced."""

    agent_count: int = Field(ge=1, le=1_000_000)
    rounds: int = Field(ge=1, le=100)
    platforms: int = Field(default=1, ge=1, le=12)
    variants: int = Field(default=1, ge=1, le=8)
    depth: Literal["brief", "standard", "deep"] = "standard"


@router.post("/checkout")
async def checkout(body: CheckoutRequest, auth: dict = Depends(get_current_org)):
    """Create Stripe Checkout session."""
    if auth["role"] not in ("owner", "admin"):
        raise HTTPException(403, "Only owners/admins can manage billing")
    url = await create_checkout_session(auth["org_id"], body.plan)
    return {"checkout_url": url}


@router.post("/flash-report")
async def flash_report_checkout(body: FlashReportCheckoutRequest, auth: dict = Depends(get_current_org)):
    """Create Stripe Checkout session for a one-time Flash Report purchase."""
    try:
        url = await create_flash_report_checkout(auth["org_id"], body.report_type)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"checkout_url": url}


@router.post("/portal")
async def portal(auth: dict = Depends(get_current_org)):
    """Create Stripe Customer Portal session."""
    if auth["role"] not in ("owner", "admin"):
        raise HTTPException(403, "Only owners/admins can manage billing")
    url = await create_customer_portal_session(auth["org_id"])
    return {"portal_url": url}


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Stripe webhook handler (no auth — verified via HMAC signature)."""
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        await handle_webhook(payload, signature)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"received": True}


@router.get("/status")
async def billing_status(auth: dict = Depends(get_current_org)):
    """Get current subscription status and usage."""
    status = await get_subscription_status(auth["org_id"])
    return status.model_dump()


@router.get("/agent-pricing")
async def agent_pricing():
    """Reference pricing: what a standard run costs and what the presets cost."""
    agents, rounds, platforms, variants = STANDARD_RUN
    return {
        "credits_per_usd": CREDITS_PER_USD,
        "standard_run": {
            "agent_count": agents,
            "rounds": rounds,
            "platforms": platforms,
            "variants": variants,
            # PRICING_GUIDE §1.5: never show a run count without this attached.
            "definition": (
                f"{agents} agents, {rounds} rounds, {platforms} platforms, "
                f"{variants} variant"
            ),
            **estimate_simulation_cost(agents, rounds, platforms, variants).model_dump(),
        },
        "presets": [
            estimate_simulation_cost(25, 3, 2, 1).model_dump(),
            estimate_simulation_cost(100, 5, 2, 1).model_dump(),
            estimate_simulation_cost(100, 5, 1, 8).model_dump(),
            estimate_simulation_cost(250, 10, 4, 1).model_dump(),
        ],
        "max_agents": 1_000_000,
    }


@router.get("/credits")
async def credit_balance(auth: dict = Depends(get_current_org)):
    """Current credit balance, grant, and the run caps for this tier."""
    balance, granted, plan = get_credit_balance(auth["org_id"])
    caps = tier_caps(plan)
    return {
        "plan": plan,
        "credits_balance": balance,
        "credits_granted": granted,
        "balance_pct": round(balance * 100 / granted, 1) if granted else 0.0,
        "caps": caps.model_dump(),
    }


@router.post("/quote")
async def quote_run(body: RunShape, auth: dict = Depends(get_current_org)):
    """Price a run shape and return a signed, single-use quote.

    The client never computes a price. It posts a shape, displays what comes
    back, and hands the quote id to `POST /simulations/{id}/start`.
    """
    try:
        quote = issue_quote(
            auth["org_id"],
            body.agent_count,
            body.rounds,
            body.platforms,
            body.variants,
            body.depth,
        )
    except QuoteError as exc:
        raise HTTPException(400, str(exc)) from exc
    return quote.model_dump(mode="json")


@router.post("/estimate-cost")
async def estimate_cost(body: RunShape, auth: dict = Depends(get_current_org)):
    """Unsigned estimate plus budget check — for display while sliders move.

    Cheaper than issuing a quote on every slider tick, and issuing one per tick
    would leave hundreds of unconsumed quote rows per configured run.
    """
    estimate = estimate_simulation_cost(
        body.agent_count, body.rounds, body.platforms, body.variants, body.depth
    )
    budget = check_credit_budget(
        auth["org_id"], body.agent_count, body.rounds,
        body.platforms, body.variants, body.depth,
    )
    _balance, _granted, plan = get_credit_balance(auth["org_id"])

    fits = None
    if not budget.allowed:
        # Backs the "Reduce to fit my balance" action — PRICING_GUIDE §1.4.
        # A dead end that offers a one-click smaller run converts; one that
        # only says "no" does not.
        reduced = largest_affordable_run(
            auth["org_id"], body.agent_count, body.rounds,
            body.platforms, body.variants, body.depth,
        )
        if reduced:
            fits = {
                "agent_count": reduced[0],
                "rounds": reduced[1],
                "platforms": reduced[2],
                "variants": reduced[3],
            }

    return {
        "estimate": estimate.model_dump(),
        "budget": budget.model_dump(),
        "caps": tier_caps(plan).model_dump(),
        "plan": plan,
        "largest_affordable": fits,
    }
