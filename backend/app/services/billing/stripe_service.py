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

# How many runs a tier's grant actually buys, and how large a team may be.
#
# **The run allowance is derived, not declared.** It was declared, and the
# declaration went stale the moment V3 renamed the tiers: this table held only
# `starter`/`pro`/`enterprise`, so `founder`, `growth` and `agency` all fell
# through to `PLAN_LIMITS["starter"]` and every paying customer on a V3 tier
# was enforced at 15 runs a month. An Agency customer at $999 lost the large
# majority of the capacity they had paid for, and nothing failed — the
# fallback made it look deliberate.
#
# Deriving it from the tier's own credit grant makes that impossible to repeat.
# `TIER_CREDIT_GRANTS` is the single place a tier is defined, so a tier that
# exists there cannot be missing here, and a limit can never contradict what
# the founder was actually sold. The credit balance is still the real ration —
# `RunCaps` says so — and this stays a backstop against runaway automation
# rather than a second, quieter pricing scheme.
_TEAM_SEATS = {
    "free": 1,
    "trial": 1,
    "founder": 3,
    "starter": 3,
    "growth": 10,
    "pro": 10,
    "agency": 999_999,
    "enterprise": 999_999,
}


# The cap must sit ABOVE what the grant buys, never level with it.
#
# Set equal to the grant's worth of runs, this table would silently become the
# binding constraint the moment a founder bought top-up credits: they would
# have paid for credits the monthly cap forbids them to spend. Credits ration;
# this stops a runaway loop. Ten times the grant is far beyond any honest
# month's use and still catches automation gone wrong.
_BACKSTOP_MULTIPLE = 10


def _plan_limits() -> dict[str, dict[str, int]]:
    from app.services.billing.agent_pricing import (
        TIER_CREDIT_GRANTS,
        capped_run_credits,
    )

    limits: dict[str, dict[str, int]] = {}
    for plan, grant in TIER_CREDIT_GRANTS.items():
        per_run = max(capped_run_credits(plan), 1)
        buys = max(grant // per_run, 1)
        limits[plan] = {
            # A tier whose seats nobody set gets the most conservative real
            # answer rather than an invented generous one.
            "max_team_members": _TEAM_SEATS.get(plan, 1),
            "max_simulations_per_month": buys * _BACKSTOP_MULTIPLE,
        }
    return limits


PLAN_LIMITS = _plan_limits()


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
        success_url=f"{settings.frontend_url}/settings?success=true",
        cancel_url=f"{settings.frontend_url}/settings?canceled=true",
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
        success_url=f"{settings.frontend_url}/settings?flash_report={report_type}&success=true",
        cancel_url=f"{settings.frontend_url}/settings?canceled=true",
        metadata={"org_id": str(org_id), "report_type": report_type},
    )
    return session.url


async def create_topup_checkout(
    org_id: UUID, amount_cents: int, created_by: str | None = None
) -> str:
    """Check out a one-off credit top-up of an arbitrary amount.

    **No Price ID.** `price_data` carries the amount inline, which is the whole
    reason this could ship while the tier migration is still waiting on Stripe
    Products — a variable amount cannot be a fixed Price anyway.

    The `credit_topups` row is written *before* the session is handed back, so
    the webhook has something to claim when payment lands. Writing it afterwards
    would leave a window in which a founder pays and the callback finds no row
    to credit, which is the worst outcome this whole path has.

    `credits` is stored on that row rather than recomputed on credit: the number
    quoted on screen is what they are owed, even if the rate changes between
    opening Checkout and paying.
    """
    from app.services.billing.topups import quote_topup

    quote = quote_topup(amount_cents)

    admin = get_supabase_admin()
    org = admin.table("organizations").select("*").eq(
        "id", str(org_id)
    ).single().execute().data

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
        line_items=[{
            "quantity": 1,
            "price_data": {
                "currency": "usd",
                "unit_amount": quote.amount_cents,
                "product_data": {
                    "name": f"{quote.credits:,} Saibyl credits",
                    "description": (
                        "Credits do not expire and are used as you run. "
                        "One-off - this does not start a subscription."
                    ),
                },
            },
        }],
        success_url=(
            f"{settings.frontend_url}/app/settings/billing"
            f"?topup=success&credits={quote.credits}"
        ),
        cancel_url=f"{settings.frontend_url}/app/settings/billing?topup=canceled",
        metadata={
            "org_id": str(org_id),
            # The discriminator the webhook branches on. Without it a top-up
            # falls through to the subscription branch, which would rewrite the
            # org's plan and null its subscription id - the exact defect the
            # Flash Report branch was added to fix.
            "kind": "credit_topup",
            "credits": str(quote.credits),
        },
    )

    admin.table("credit_topups").insert({
        "organization_id": str(org_id),
        "stripe_session_id": session.id,
        "amount_cents": quote.amount_cents,
        "credits": quote.credits,
        "status": "pending",
        "created_by": created_by,
    }).execute()

    logger.info(
        "topup_checkout_opened",
        org_id=str(org_id),
        amount_cents=quote.amount_cents,
        credits=quote.credits,
        session=session.id,
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
        return_url=f"{settings.frontend_url}/settings",
    )
    return session.url


async def handle_webhook(payload: bytes, signature: str) -> None:
    """Process Stripe webhook events."""
    import json

    # Verify signature using Stripe SDK
    try:
        stripe.Webhook.construct_event(
            payload, signature, settings.stripe_webhook_secret,
        )
    except stripe.error.SignatureVerificationError:
        raise ValueError("Invalid webhook signature")

    # Parse raw JSON to avoid StripeObject attribute access issues
    event_dict = json.loads(payload)
    admin = get_supabase_admin()
    event_type = event_dict["type"]
    data = event_dict["data"]["object"]

    logger.info("stripe_webhook", event_type=event_type)

    if event_type == "checkout.session.completed":
        metadata = data.get("metadata") or {}
        org_id = metadata.get("org_id")
        plan = metadata.get("plan")

        if not org_id:
            # Ack'd 200 by the caller, so Stripe never retries. A payment that
            # reaches nobody has to be loud or it is simply lost.
            logger.error(
                "stripe_webhook_missing_org",
                event_type=event_type,
                session=data.get("id"),
                detail="checkout completed with no org_id in metadata; "
                       "the purchase was not applied to any organisation",
            )
        elif plan:
            limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["starter"])
            admin.table("organizations").update({
                "plan": plan,
                "stripe_subscription_id": data.get("subscription"),
                "subscription_status": "active",
                **limits,
            }).eq("id", org_id).execute()
            logger.info("subscription_activated", org_id=org_id, plan=plan)
        elif metadata.get("kind") == "credit_topup":
            # Credited by the database, not here. `apply_credit_topup` claims
            # the row on `credited_at IS NULL` and moves the balance in one
            # transaction, so a Stripe retry - which is routine, not an edge
            # case - credits nothing the second time.
            #
            # Deliberately not `grant_credits`: that RPC sets
            # `credits_granted = amount` and restarts the billing cycle, so a
            # $10 top-up would take a founder org from 19,800 granted to 1,500
            # and reset their month. Migration 031 has the full reasoning.
            result = admin.rpc("apply_credit_topup", {
                "session_id": data.get("id"),
                "payment_intent": data.get("payment_intent"),
            }).execute()
            rows = result.data or []
            if isinstance(rows, dict):
                rows = [rows]
            credited = int((rows[0] or {}).get("credited") or 0) if rows else 0
            if credited:
                logger.info(
                    "topup_credited",
                    org_id=org_id,
                    session=data.get("id"),
                    credits=credited,
                    balance=(rows[0] or {}).get("balance"),
                )
            else:
                # Either a retry of something already applied, or a session we
                # have no row for. The second is money we took and cannot
                # attribute, so it is an error rather than a shrug - but it is
                # still a 200, because asking Stripe to retry will not conjure
                # the row.
                existing = admin.table("credit_topups").select("id").eq(
                    "stripe_session_id", data.get("id")
                ).execute().data
                if existing:
                    logger.info(
                        "topup_already_credited",
                        org_id=org_id,
                        session=data.get("id"),
                    )
                else:
                    logger.error(
                        "topup_paid_with_no_row",
                        org_id=org_id,
                        session=data.get("id"),
                        detail="a credit top-up was paid for and no "
                               "credit_topups row exists to credit it",
                    )
        elif metadata.get("report_type"):
            # A one-off Flash Report. **This used to fall through the
            # subscription branch**, because `plan` defaulted to "starter" when
            # absent — and `create_flash_report_checkout` never sets it. So an
            # Agency customer buying a single report was downgraded to starter
            # limits, and `data["subscription"]` is None on a `mode="payment"`
            # session, so their subscription id was nulled at the same time.
            # The purchase is fulfilled elsewhere; there is nothing to do to the
            # organisation here except not corrupt it.
            logger.info(
                "flash_report_purchased",
                org_id=org_id,
                report_type=metadata.get("report_type"),
            )
        else:
            logger.error(
                "stripe_webhook_unclassified_checkout",
                org_id=org_id,
                session=data.get("id"),
                detail="checkout completed with neither a plan nor a "
                       "report_type; nothing was applied",
            )

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
