from __future__ import annotations

from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.auth import get_current_org
from app.core.database import get_supabase_admin
from app.services.billing.agent_pricing import (
    CREDITS_PER_USD,
    STANDARD_RUN,
    answer_pack_credits,
    capital_shortlist_credits,
    capped_run_credits,
    check_credit_budget,
    clearance_credits,
    estimate_simulation_cost,
    get_credit_balance,
    largest_affordable_run,
    messaging_doc_credits,
    outbound_sequence_credits,
    standard_run_credits,
    tier_caps,
    website_check_credits,
    website_revision_credits,
)
from app.services.billing.run_quote import QuoteError, issue_quote
from app.services.billing.stripe_service import (
    create_checkout_session,
    create_customer_portal_session,
    create_flash_report_checkout,
    create_topup_checkout,
    get_subscription_status,
    handle_webhook,
)
from app.services.billing.topups import (
    MAX_TOPUP_CENTS,
    MIN_TOPUP_CENTS,
    SUGGESTED_TOPUP_USD,
    TopupRefusedError,
    credits_for_topup,
    quote_topup,
)

log = structlog.get_logger()

router = APIRouter(tags=["billing"])


class CheckoutRequest(BaseModel):
    plan: str  # starter | pro | enterprise


class FlashReportCheckoutRequest(BaseModel):
    report_type: str  # quick_read | deep_dive | war_room_brief


class TopupRequest(BaseModel):
    """How much a founder wants to put on, in cents.

    Cents rather than dollars because money in a float drifts, and this number
    is handed to Stripe and reconciled against it.

    **The bounds are deliberately not `ge`/`le` here.** Pydantic validates
    before the handler runs, so declaring the range on the field meant a founder
    who typed $5 got back `Input should be greater than or equal to 1000` — a
    validation code, in cents, about a field name they never see. The sentences
    in `quote_topup` were written precisely to avoid that and were unreachable
    from the API; the tests passed because they call the function directly.

    The loose bound that remains is an absurdity guard, not a price rule: it
    stops an unbounded integer reaching Stripe. Everything a founder can
    plausibly type is refused by `quote_topup`, in words, with the remedy.
    """

    amount_cents: int = Field(gt=0, le=100_000_000)


class RunShape(BaseModel):
    """A run configuration to be priced."""

    agent_count: int = Field(ge=1, le=1_000_000)
    rounds: int = Field(ge=1, le=100)
    platforms: int = Field(default=1, ge=1, le=12)
    variants: int = Field(default=1, ge=1, le=8)
    depth: Literal["brief", "standard", "deep"] = "standard"

    # The run being priced, when there is one (P0-6).
    #
    # A price is not a property of a shape alone. A run whose agents read the
    # project's uploaded material carries that material in every action prompt,
    # and `POST /simulations/{id}/start` charges for it — while this endpoint,
    # knowing only the shape, quoted as though it did not. The founder saw one
    # number and was charged one 8–14% higher.
    #
    # Optional because the configurator legitimately prices a shape before a
    # run exists. Absent, the answer is False, which is then the true answer:
    # a run with no simulation behind it carries no brief.
    simulation_id: str | None = None


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


@router.get("/topup/options")
async def topup_options(auth: dict = Depends(get_current_org)):
    """What a top-up costs and what each suggested amount buys.

    Read before anything is charged, so the founder sees the credits, the runs
    and the fact that subscribing is better value **before** they reach Stripe.
    Priced by the same function that prices the real checkout, so the screen and
    the charge cannot disagree.
    """
    quotes = []
    for usd in SUGGESTED_TOPUP_USD:
        try:
            quotes.append(quote_topup(usd * 100).model_dump())
        except TopupRefusedError:
            # A suggested amount outside the accepted range is a configuration
            # mistake, not a user error. Skipped rather than 500, and loud in
            # the response by its absence.
            continue
    # What a full-size run costs **the founder**, not what it costs us. The
    # serving cost is internal and deliberately stays off customer-facing
    # surfaces; the number that belongs on a page asking for money is the price
    # they would actually pay, at the rate this very panel charges.
    run_credits = standard_run_credits()
    per_dollar = credits_for_topup(100)
    return {
        "min_cents": MIN_TOPUP_CENTS,
        "max_cents": MAX_TOPUP_CENTS,
        "suggested": quotes,
        "standard_run": {
            "credits": run_credits,
            "definition": "100 buyers, 5 rounds, 2 places",
            # None rather than a divide-by-zero or a zero that reads as free.
            "usd_at_topup_rate": (
                round(run_credits / per_dollar, 2) if per_dollar else None
            ),
        },
    }


@router.post("/topup/quote")
async def topup_quote(body: TopupRequest, auth: dict = Depends(get_current_org)):
    """Price an arbitrary amount, for the field beside the suggested buttons."""
    try:
        return quote_topup(body.amount_cents).model_dump()
    except TopupRefusedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/topup")
async def topup(body: TopupRequest, auth: dict = Depends(get_current_org)):
    """Open Checkout for a one-off credit top-up of any amount.

    Not restricted to owners and admins, unlike `/checkout`. A subscription
    changes what the organisation is committed to every month; a top-up adds
    credits once, and a member who has run out mid-task should not have to find
    an admin to spend $10.
    """
    try:
        url = await create_topup_checkout(
            auth["org_id"], body.amount_cents, created_by=auth["user"]["id"]
        )
    except TopupRefusedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
    per_run = standard_run_credits()
    return {
        "plan": plan,
        "credits_balance": balance,
        "credits_granted": granted,
        "balance_pct": round(balance * 100 / granted, 1) if granted else 0.0,
        "caps": caps.model_dump(),
        # What a run of the reference shape costs, so a client can say "about
        # four more runs" instead of printing a five-digit number at someone
        # deciding whether they can afford to click. Sent rather than computed
        # client-side: the run price is a pricing fact and belongs on one side.
        "standard_run_credits": per_run,
        # And what a run costs at THIS tier's ceiling. The client must divide
        # by this one to say "about N more runs": dividing a free balance by
        # the 100-agent reference price answers a question a capped account
        # cannot ask, and printed "About 0 more runs" to every new signup
        # holding a grant that covers a full capped run.
        "capped_run_credits": capped_run_credits(plan),
        # Aliases. The two readers of this endpoint were both written against
        # `balance`/`grant` and would have rendered silent zeros - a balance of
        # 0 is the one number that stops a founder clicking. Kept as aliases
        # rather than renamed, because `credits_balance` is what the older
        # callers read and breaking them to tidy a name is not worth it.
        "balance": balance,
        "grant": granted,
    }


@router.get("/prices")
async def paid_feature_prices(auth: dict = Depends(get_current_org)):
    """What each paid thing costs, and whether this balance covers it.

    Exists so a founder learns the price **before** doing the work rather
    than after. Every paid surface refused with a 402 at submit — "this check
    needs 1,750; you have 1,500" — which arrives once the URL is typed and
    the form filled, and reads as a wall rather than an offer.

    The shape of the business is deliberate and is encoded here: the idea
    evaluation is the loss leader (the free grant covers one full run at the
    free cap) and the checks that save a founder real money — the website
    read, the USPTO clearance — are what they pay for. So this endpoint
    reports the free thing as free and prices the rest honestly, with the
    shortfall already worked out.
    """
    balance, _granted, plan = get_credit_balance(auth["org_id"])

    def entry(credits: int, label: str, free_note: str | None = None) -> dict:
        return {
            "credits": credits,
            "label": label,
            "affordable": balance >= credits,
            "shortfall": max(0, credits - balance),
            "free": credits == 0,
            "note": free_note,
        }

    return {
        "balance": balance,
        "plan": plan,
        "idea_evaluation": entry(
            capped_run_credits(plan),
            "A room of buyers reacts to your idea",
            "Your free credits cover one of these.",
        ),
        "website_check": entry(
            website_check_credits(), "We read your page like a buyer would"
        ),
        "answer_pack": entry(
            answer_pack_credits(), "What to say when they push back"
        ),
        "website_revision": entry(
            website_revision_credits(), "We rewrite the page and prove the difference"
        ),
        # Three artifacts were priced in `agent_pricing` and charged by their
        # routes, but never published here — so the one surface whose whole
        # purpose is "learn the price before doing the work" could not price
        # them, and a founder met the cost as a 402 at submit. That is the
        # exact failure this endpoint exists to prevent, and it happened three
        # times because nothing fails when an artifact is left out. See the
        # test that now enumerates every priced artifact and requires it here.
        "capital_shortlist": entry(
            capital_shortlist_credits(), "Who would fund this, and who would not"
        ),
        "messaging_doc": entry(
            messaging_doc_credits(), "The words that landed, written down"
        ),
        "outbound_sequence": entry(
            outbound_sequence_credits(), "Sixteen touches, built from real objections"
        ),
        "clearance": {
            tier: entry(clearance_credits(tier), f"USPTO search — {tier.lower()}")
            for tier in ("QUICK", "STANDARD", "COMPREHENSIVE")
        },
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
            subject_brief=_carries_subject_brief(body.simulation_id, auth["org_id"]),
        )
    except QuoteError as exc:
        raise HTTPException(400, str(exc)) from exc
    return quote.model_dump(mode="json")


def _carries_subject_brief(simulation_id: str | None, org_id: str) -> bool:
    """Will this run send the project's material with every action?

    Org-scoped: pricing another organisation's run would leak whether they
    uploaded material. A row we cannot read prices as False, which is also the
    honest answer — we will not charge for material we cannot confirm is
    there.
    """
    if not simulation_id:
        return False
    try:
        row = (
            get_supabase_admin()
            .table("simulations")
            .select("id, project_id, parent_simulation_id")
            .eq("id", simulation_id)
            .eq("organization_id", org_id)
            .limit(1)
            .execute()
        ).data
    except Exception:  # noqa: BLE001 - pricing must not fail on a lookup
        log.exception("subject_brief_pricing_lookup_failed", simulation_id=simulation_id)
        return False
    if not row:
        return False

    from app.services.intelligence.subject_brief import run_will_carry_subject_brief

    try:
        return run_will_carry_subject_brief(row[0])
    except Exception:  # noqa: BLE001
        log.exception("subject_brief_pricing_failed", simulation_id=simulation_id)
        return False


@router.post("/estimate-cost")
async def estimate_cost(body: RunShape, auth: dict = Depends(get_current_org)):
    """Unsigned estimate plus budget check — for display while sliders move.

    Cheaper than issuing a quote on every slider tick, and issuing one per tick
    would leave hundreds of unconsumed quote rows per configured run.
    """
    subject_brief = _carries_subject_brief(body.simulation_id, auth["org_id"])
    estimate = estimate_simulation_cost(
        body.agent_count, body.rounds, body.platforms, body.variants, body.depth,
        subject_brief=subject_brief,
    )
    budget = check_credit_budget(
        auth["org_id"], body.agent_count, body.rounds,
        body.platforms, body.variants, body.depth,
        subject_brief=subject_brief,
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
