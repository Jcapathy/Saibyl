# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# create_topup_checkout(org_id, amount_cents, created_by) -> str
# create_flash_report_checkout(org_id, report_type) -> str
# handle_webhook(payload, signature) -> None
# ─────────────────────────────────────────────────────────
from __future__ import annotations

from datetime import datetime
from uuid import UUID

import stripe
import structlog

from app.core.config import settings
from app.core.database import get_supabase_admin

logger = structlog.get_logger()

stripe.api_key = settings.stripe_secret_key

FLASH_REPORT_PRICE_MAP = {
    "quick_read": "price_1TLd7YIqFuuRAGd4jIMH2J07",      # $197 one-time
    "deep_dive": "price_1TLd8GIqFuuRAGd4xkisiqPJ",       # $497 one-time
    "war_room_brief": "price_1TLd9RIqFuuRAGd4M0l0eGhF",  # $997 one-time
}

# No plan limits, no subscription status, no subscription checkout.
#
# Removed 2026-08-25 with the tiers they served (PRD_V3 §6). What stood here
# was `PLAN_LIMITS` — a per-plan monthly run allowance and seat count — plus the
# `SubscriptionStatus` model and `create_checkout_session`, which opened Stripe
# in `mode="subscription"` against `PLAN_PRICE_MAP`.
#
# **Credits are the only ration now.** A founder runs what they have paid for,
# and nothing else may quietly forbid them to spend credits they bought. The
# monthly allowance was derived from the tier grant, so under a single grant it
# would have resolved to roughly ten runs a month and bound on the first
# founder to top up — the precise failure its own comment was written against.
#
# Stripe itself stays, in `mode="payment"`: `create_topup_checkout` below is how
# founders buy credits, and `create_flash_report_checkout` is the one-off
# report. Neither needs a Price ID, which is why both could ship while the tier
# migration never did.


def _mint_customer(admin, org_id: UUID, org: dict) -> str:
    """Create a Stripe customer for this org and persist its id."""
    customer = stripe.Customer.create(
        metadata={"org_id": str(org_id), "org_name": org["name"]},
    )
    admin.table("organizations").update({
        "stripe_customer_id": customer.id,
    }).eq("id", str(org_id)).execute()
    return customer.id


def _is_missing_customer(exc: Exception) -> bool:
    """Is this Stripe saying the customer we passed does not exist?

    `param` is `"customer"` when Checkout rejects the id we handed it, but the
    message is also matched because the same condition surfaces from more than
    one endpoint and a silent miss here costs a sale.
    """
    if not isinstance(exc, stripe.error.InvalidRequestError):
        return False
    if getattr(exc, "code", None) != "resource_missing":
        return False
    return (
        getattr(exc, "param", None) == "customer"
        or "no such customer" in str(exc).lower()
    )


def _checkout_recovering_stale_customer(admin, org_id: UUID, org: dict, build):
    """Open Checkout, and survive a `stripe_customer_id` Stripe has never heard of.

    **This is a defect that reached production and cost a real payment attempt.**
    On 2026-08-27 the founder's org held `cus_V9cLNGxXbbzvOo`, minted while the
    backend was pointed at a sandbox account. When the keys moved to live, both
    checkout paths kept handing that id to Stripe, because each only created a
    customer `if not customer_id` — a stored id was assumed to be a valid one.
    Stripe answered `resource_missing`, the request raised, and the founder saw
    "network error" with no `credit_topups` row and nothing in the product to
    explain it. There was no recovery path: every retry re-sent the same dead id.

    A customer id is only meaningful for the Stripe account that issued it, and
    the account can change under us — sandbox to live, a key rotation, a
    restored backup. So a stored id is a *hint*, not a fact.

    The check is a retry rather than a validating `Customer.retrieve` before
    every checkout: validating would add a round trip to every purchase forever
    to defend against something that happens approximately never. The retry
    costs nothing on the happy path and only runs when Stripe has already told
    us the id is dead.

    Retried exactly once. If the freshly-minted customer is also rejected, the
    problem is not a stale id and the error belongs to the caller.
    """
    customer_id = org.get("stripe_customer_id") or _mint_customer(admin, org_id, org)
    try:
        return build(customer_id)
    except stripe.error.InvalidRequestError as exc:
        if not _is_missing_customer(exc):
            raise
        logger.warning(
            "stripe_customer_missing_reminting",
            org_id=str(org_id),
            stale_customer_id=customer_id,
            detail="stored stripe_customer_id does not exist on the current "
                   "Stripe account; minting a fresh one and retrying once",
        )
        return build(_mint_customer(admin, org_id, org))


async def create_flash_report_checkout(org_id: UUID, report_type: str) -> str:
    """Create a Stripe Checkout session for a one-time Flash Report purchase."""
    price_id = FLASH_REPORT_PRICE_MAP.get(report_type)
    if not price_id:
        raise ValueError(f"Unknown report type: {report_type}")

    admin = get_supabase_admin()
    org = admin.table("organizations").select("*").eq("id", str(org_id)).single().execute().data

    session = _checkout_recovering_stale_customer(
        admin,
        org_id,
        org,
        lambda customer_id: stripe.checkout.Session.create(
            customer=customer_id,
            mode="payment",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=(
                f"{settings.frontend_url}/settings?flash_report={report_type}&success=true"
            ),
            cancel_url=f"{settings.frontend_url}/settings?canceled=true",
            metadata={"org_id": str(org_id), "report_type": report_type},
        ),
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

    # A stored `stripe_customer_id` is a hint, not a fact - it is only valid for
    # the Stripe account that issued it. See
    # `_checkout_recovering_stale_customer`: this is the exact call that failed
    # in production when the keys moved from a sandbox to the live account.
    session = _checkout_recovering_stale_customer(
        admin,
        org_id,
        org,
        lambda customer_id: stripe.checkout.Session.create(
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
                # falls through to the subscription branch, which would rewrite
                # the org's plan and null its subscription id - the exact defect
                # the Flash Report branch was added to fix.
                "kind": "credit_topup",
                "credits": str(quote.credits),
            },
        ),
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
