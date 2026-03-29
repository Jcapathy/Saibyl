from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.core.auth import get_current_org
from app.services.billing.agent_pricing import check_agent_budget, estimate_simulation_cost
from app.services.billing.stripe_service import (
    create_checkout_session,
    create_customer_portal_session,
    get_subscription_status,
    handle_webhook,
)

router = APIRouter(tags=["billing"])


class CheckoutRequest(BaseModel):
    plan: str  # starter | pro | enterprise


class CostEstimateRequest(BaseModel):
    agent_count: int
    rounds: int


@router.post("/checkout")
async def checkout(body: CheckoutRequest, auth: dict = Depends(get_current_org)):
    """Create Stripe Checkout session."""
    if auth["role"] not in ("owner", "admin"):
        raise HTTPException(403, "Only owners/admins can manage billing")
    url = await create_checkout_session(auth["org_id"], body.plan)
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
    """Return agent pricing info and cost estimator."""
    examples = [
        estimate_simulation_cost(1_000, 5).model_dump(),
        estimate_simulation_cost(10_000, 5).model_dump(),
        estimate_simulation_cost(100_000, 5).model_dump(),
    ]
    return {"examples": examples, "max_agents": 1_000_000}


@router.post("/estimate-cost")
async def estimate_cost(body: CostEstimateRequest, auth: dict = Depends(get_current_org)):
    """Estimate cost for a simulation run and check budget."""
    estimate = estimate_simulation_cost(body.agent_count, body.rounds)
    budget = check_agent_budget(auth["org_id"], body.agent_count, body.rounds)
    return {"estimate": estimate.model_dump(), "budget": budget.model_dump()}
