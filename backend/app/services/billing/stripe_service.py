# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# create_checkout_session(org_id, plan) -> str
# create_customer_portal_session(org_id) -> str
# handle_webhook(payload, signature) -> None
# get_subscription_status(org_id) -> SubscriptionStatus
# check_simulation_quota(org_id) -> bool
# ─────────────────────────────────────────────────────────
from __future__ import annotations

from datetime import datetime
from uuid import UUID

import stripe
import structlog
from pydantic import BaseModel

from app.core.config import settings
from app.core.database import get_supabase_admin

logger = structlog.get_logger()

stripe.api_key = settings.stripe_secret_key

PLAN_PRICE_MAP = {
    "starter": "price_1TLd4VIqFuuRAGd4tWbna0Dd",   # Analyst $149/mo
    "pro": "price_1TLd5yIqFuuRAGd4k7ZSTPuq",        # Strategist $499/mo
    "enterprise": "price_1TLd6nIqFuuRAGd4Z6amqUOR",  # War Room $1,499/mo
}

FLASH_REPORT_PRICE_MAP = {
    "quick_read": "price_1TLd7YIqFuuRAGd4jIMH2J07",      # $197 one-time
    "deep_dive": "price_1TLd8GIqFuuRAGd4xkisiqPJ",       # $497 one-time
    "war_room_brief": "price_1TLd9RIqFuuRAGd4M0l0eGhF",  # $997 one-time
}

PLAN_LIMITS = {
    "starter": {"max_simulations_per_month": 15, "max_team_members": 3},
    "pro": {"max_simulations_per_month": 75, "max_team_members": 10},
    "enterprise": {"max_simulations_per_month": 999999, "max_team_members": 999999},
}


class SubscriptionStatus(BaseModel):
    plan: str
    status: str
    simulations_used: int
    simulations_limit: int
    agents_used: int = 0
    agents_limit: int = 0
    team_members: int
    team_members_limit: int
    current_period_end: str | None = None


async def create_checkout_session(org_id: UUID, plan: str) -> str:
    """Create a Stripe Checkout session and return the URL."""
    admin = get_supabase_admin()
    org = admin.table("organizations").select("*").eq("id", str(org_id)).single().execute().data

    # Get or create Stripe customer
    customer_id = org.get("stripe_customer_id")
    if not customer_id:
        customer = stripe.Customer.create(
            metadata={"org_id": str(org_id), "org_name": org["name"]},
        )
        customer_id = customer.id
        admin.table("organizations").update({
            "stripe_customer_id": customer_id,
        }).eq("id", str(org_id)).execute()

    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": PLAN_PRICE_MAP.get(plan, "price_starter"), "quantity": 1}],
        success_url=f"{settings.frontend_url}/billing?success=true",
        cancel_url=f"{settings.frontend_url}/billing?canceled=true",
        metadata={"org_id": str(org_id), "plan": plan},
    )
    return session.url


async def create_flash_report_checkout(org_id: UUID, report_type: str) -> str:
    """Create a Stripe Checkout session for a one-time Flash Report purchase."""
    price_id = FLASH_REPORT_PRICE_MAP.get(report_type)
    if not price_id:
        raise ValueError(f"Unknown report type: {report_type}")

    admin = get_supabase_admin()
    org = admin.table("organizations").select("*").eq("id", str(org_id)).single().execute().data

    customer_id = org.get("stripe_customer_id")
    if not customer_id:
        customer = stripe.Customer.create(
            metadata={"org_id": str(org_id), "org_name": org["name"]},
        )
        customer_id = customer.id
        admin.table("organizations").update({
            "stripe_customer_id": customer_id,
        }).eq("id", str(org_id)).execute()

    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="payment",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{settings.frontend_url}/billing?flash_report={report_type}&success=true",
        cancel_url=f"{settings.frontend_url}/billing?canceled=true",
        metadata={"org_id": str(org_id), "report_type": report_type},
    )
    return session.url


async def create_customer_portal_session(org_id: UUID) -> str:
    """Create a Stripe Customer Portal session."""
    admin = get_supabase_admin()
    org = admin.table("organizations").select(
        "stripe_customer_id"
    ).eq("id", str(org_id)).single().execute().data

    if not org.get("stripe_customer_id"):
        raise ValueError("No billing account found")

    session = stripe.billing_portal.Session.create(
        customer=org["stripe_customer_id"],
        return_url=f"{settings.frontend_url}/billing",
    )
    return session.url


async def handle_webhook(payload: bytes, signature: str) -> None:
    """Process Stripe webhook events."""
    try:
        event = stripe.Webhook.construct_event(
            payload, signature, settings.stripe_webhook_secret,
        )
    except stripe.error.SignatureVerificationError:
        raise ValueError("Invalid webhook signature")

    admin = get_supabase_admin()
    event_type = event["type"]
    data = event["data"]["object"]

    logger.info("stripe_webhook", event_type=event_type)

    if event_type == "checkout.session.completed":
        org_id = data.get("metadata", {}).get("org_id")
        plan = data.get("metadata", {}).get("plan", "starter")
        if org_id:
            limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["starter"])
            admin.table("organizations").update({
                "plan": plan,
                "stripe_subscription_id": data.get("subscription"),
                "subscription_status": "active",
                **limits,
            }).eq("id", org_id).execute()
            logger.info("subscription_activated", org_id=org_id, plan=plan)

    elif event_type == "invoice.payment_succeeded":
        customer_id = data.get("customer")
        orgs = admin.table("organizations").select("id").eq(
            "stripe_customer_id", customer_id
        ).execute().data
        if orgs:
            org_id = orgs[0]["id"]
            month = datetime.now().strftime("%Y-%m")
            admin.table("usage_records").upsert({
                "organization_id": org_id,
                "month": month,
                "simulations_run": 0,
            }, on_conflict="organization_id,month").execute()

    elif event_type == "invoice.payment_failed":
        customer_id = data.get("customer")
        logger.warning("payment_failed", customer_id=customer_id)

    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer")
        orgs = admin.table("organizations").select("id").eq(
            "stripe_customer_id", customer_id
        ).execute().data
        if orgs:
            admin.table("organizations").update({
                "plan": "starter",
                "subscription_status": "canceled",
                **PLAN_LIMITS["starter"],
            }).eq("id", orgs[0]["id"]).execute()
            logger.info("subscription_canceled", org_id=orgs[0]["id"])


async def get_subscription_status(org_id: UUID) -> SubscriptionStatus:
    """Get current subscription status and usage from actual data."""
    admin = get_supabase_admin()
    org = admin.table("organizations").select("*").eq("id", str(org_id)).single().execute().data

    # Count actual simulations run this month (any status except draft)
    month_start = datetime.now().strftime("%Y-%m-01T00:00:00")
    sims = admin.table("simulations").select(
        "id", count="exact"
    ).eq("organization_id", str(org_id)).neq(
        "status", "draft"
    ).gte("created_at", month_start).execute()
    sims_used = sims.count or 0

    # Count total agents created this month
    agents = admin.table("simulation_agents").select(
        "id", count="exact"
    ).eq("organization_id", str(org_id)).gte(
        "created_at", month_start
    ).execute()
    agents_used = agents.count or 0

    members = admin.table("organization_members").select(
        "id", count="exact"
    ).eq("organization_id", str(org_id)).execute()

    plan = org.get("plan", "starter")
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["starter"])
    agent_limits = {"starter": 150_000, "pro": 7_500_000, "enterprise": 50_000_000}

    return SubscriptionStatus(
        plan=plan,
        status=org.get("subscription_status", "trialing"),
        simulations_used=sims_used,
        simulations_limit=limits["max_simulations_per_month"],
        agents_used=agents_used,
        agents_limit=agent_limits.get(plan, 50_000),
        team_members=members.count or 0,
        team_members_limit=limits["max_team_members"],
    )


async def check_simulation_quota(org_id: UUID) -> bool:
    """Returns True if org has simulation quota remaining this month."""
    status = await get_subscription_status(org_id)
    return status.simulations_used < status.simulations_limit
