# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# issue_quote(org_id, agent_count, rounds, platforms, variants, depth) -> RunQuote
# load_quote(quote_id, org_id) -> RunQuote
# consume_quote(quote_id, org_id, simulation_id, actual_shape) -> RunQuote
# QUOTE_TTL_MINUTES
# ─────────────────────────────────────────────────────────
"""Server-side signed run quotes.

The client must never compute a price. Without a server-issued quote, the run
shape that gets billed is whatever the browser posted, and a user who edits
`agent_count` in a request body gets a 250-agent run at a 25-agent price. So the
server prices the shape, signs the priced fields, stores the quote, and the
client hands back an id.

The signature is belt-and-braces on top of the stored row: the row is the
authority, and the HMAC catches the case where a quote is somehow replayed or
mutated in storage. Verification checks the signature, the owning org, the
expiry, and that the quote has not already been consumed — a quote is
single-use, or one cheap quote could fund unlimited runs.

Quotes are consumed at *start*, not at completion. A run that is quoted, started,
and then fails still consumed compute, and reconciliation against the measured
`llm_usage` cost happens afterwards.
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from pydantic import BaseModel

from app.core.config import settings
from app.core.database import get_supabase_admin
from app.services.billing.agent_pricing import (
    MAX_AGENTS,
    MAX_RUNNABLE_VARIANTS,
    estimate_simulation_cost,
    get_credit_balance,
    tier_caps,
)

logger = structlog.get_logger()

# Long enough to finish configuring a run, short enough that a quote cannot
# outlive a price change or a recalibration of the token profiles.
QUOTE_TTL_MINUTES = 30


class RunQuote(BaseModel):
    id: str
    organization_id: str
    simulation_id: str | None = None

    agent_count: int
    rounds: int
    platforms: int
    variants: int
    depth: str

    estimated_cost_usd: float
    retail_price_usd: float
    credits: int
    margin_pct: float
    breakdown: dict[str, float]

    expires_at: datetime
    consumed_at: datetime | None = None

    # Balance context, so the configurator can render the warning states from
    # PRICING_GUIDE §1.4 without a second round trip.
    credits_balance: int = 0
    credits_after: int = 0
    balance_share_pct: float = 0.0
    standard_run_equivalents: float = 0.0
    caps_exceeded: list[str] = []


class QuoteError(ValueError):
    """A quote could not be issued or redeemed."""


def _signing_key() -> bytes:
    key = settings.secret_key or ""
    if not key:
        # Development only. In production the config validator already refuses
        # a key under 32 characters, so this cannot silently weaken a live
        # deployment.
        logger.warning("quote_signing_key_missing", note="using empty dev key")
    return key.encode("utf-8")


def _canonical(
    quote_id: str,
    org_id: str,
    agent_count: int,
    rounds: int,
    platforms: int,
    variants: int,
    depth: str,
    credits: int,
    expires_at: str,
) -> str:
    """The exact bytes signed. Order is fixed; adding a field must change it."""
    return "|".join(
        [
            quote_id, org_id, str(agent_count), str(rounds), str(platforms),
            str(variants), depth, str(credits), expires_at,
        ]
    )


def _sign(payload: str) -> str:
    return hmac.new(_signing_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _validate_shape(agent_count: int, rounds: int, platforms: int, variants: int) -> None:
    if agent_count <= 0 or rounds <= 0 or platforms <= 0 or variants <= 0:
        raise QuoteError("Agents, rounds, platforms and variants must all be positive")
    if agent_count > MAX_AGENTS:
        raise QuoteError(f"Agent count cannot exceed {MAX_AGENTS:,}")
    if variants > MAX_RUNNABLE_VARIANTS:
        # Refused rather than clamped: the engine runs one arena, so a
        # multi-variant quote would charge for arenas that are never executed.
        # Silently reducing it would price one thing and run another.
        raise QuoteError(
            f"Multi-variant runs are not available yet — the engine runs "
            f"{MAX_RUNNABLE_VARIANTS} arena. Matched-swarm variant testing "
            f"arrives with the Marketing lens."
        )


def issue_quote(
    org_id: UUID | str,
    agent_count: int,
    rounds: int,
    platforms: int = 1,
    variants: int = 1,
    depth: str = "standard",
    subject_brief: bool = False,
) -> RunQuote:
    """Price a run shape, sign it, and store it.

    `subject_brief` is whether the run's agents will read the project's
    uploaded material, which the start endpoint prices and this endpoint used
    to ignore (P0-6). A quote that omits it is honoured at the lower figure,
    so the gap was absorbed rather than charged — the quote is a promise, and
    the fix is to make the promise right rather than to break it later.
    """
    _validate_shape(agent_count, rounds, platforms, variants)

    balance, _granted, plan = get_credit_balance(UUID(str(org_id)))
    caps = tier_caps(plan)

    # Caps are reported, not enforced by clamping. Silently shrinking a run the
    # user configured would quote one thing and run another; the configurator
    # shows which limit was hit and what upgrading would lift it to.
    exceeded: list[str] = []
    if agent_count > caps.max_agents:
        exceeded.append(f"agents ({agent_count} > {caps.max_agents})")
    if rounds > caps.max_rounds:
        exceeded.append(f"rounds ({rounds} > {caps.max_rounds})")
    if platforms > caps.max_platforms:
        exceeded.append(f"platforms ({platforms} > {caps.max_platforms})")
    if variants > caps.max_variants:
        exceeded.append(f"variants ({variants} > {caps.max_variants})")

    estimate = estimate_simulation_cost(
        agent_count, rounds, platforms, variants, depth,
        subject_brief=subject_brief,
    )

    admin = get_supabase_admin()
    expires_at = datetime.now(UTC) + timedelta(minutes=QUOTE_TTL_MINUTES)
    expires_iso = expires_at.isoformat()

    row = (
        admin.table("run_quotes")
        .insert({
            "organization_id": str(org_id),
            "agent_count": agent_count,
            "rounds": rounds,
            "platforms": platforms,
            "variants": variants,
            "depth": depth,
            "estimated_cost_usd": estimate.actual_cost_usd,
            "retail_price_usd": estimate.retail_cost_usd,
            "credits": estimate.credits,
            "margin_pct": estimate.margin_pct,
            "breakdown": estimate.breakdown,
            # Placeholder: the signature covers the row's own id, which only
            # exists after the insert.
            "signature": "",
            "expires_at": expires_iso,
        })
        .execute()
    ).data[0]

    signature = _sign(
        _canonical(
            row["id"], str(org_id), agent_count, rounds, platforms, variants,
            depth, estimate.credits, expires_iso,
        )
    )
    admin.table("run_quotes").update({"signature": signature}).eq(
        "id", row["id"]
    ).execute()

    logger.info(
        "quote_issued",
        quote_id=row["id"],
        org_id=str(org_id),
        credits=estimate.credits,
        shape=f"{agent_count}a/{rounds}r/{platforms}p/{variants}v",
    )

    return RunQuote(
        id=row["id"],
        organization_id=str(org_id),
        agent_count=agent_count,
        rounds=rounds,
        platforms=platforms,
        variants=variants,
        depth=depth,
        estimated_cost_usd=estimate.actual_cost_usd,
        retail_price_usd=estimate.retail_cost_usd,
        credits=estimate.credits,
        margin_pct=estimate.margin_pct,
        breakdown=estimate.breakdown,
        expires_at=expires_at,
        credits_balance=balance,
        credits_after=max(0, balance - estimate.credits),
        balance_share_pct=(
            round(estimate.credits * 100 / balance, 2) if balance > 0 else 100.0
        ),
        standard_run_equivalents=estimate.standard_run_equivalents,
        caps_exceeded=exceeded,
    )


def _row_to_quote(row: dict) -> RunQuote:
    return RunQuote(
        id=row["id"],
        organization_id=row["organization_id"],
        simulation_id=row.get("simulation_id"),
        agent_count=row["agent_count"],
        rounds=row["rounds"],
        platforms=row["platforms"],
        variants=row["variants"],
        depth=row["depth"],
        estimated_cost_usd=float(row["estimated_cost_usd"]),
        retail_price_usd=float(row["retail_price_usd"]),
        credits=int(row["credits"]),
        margin_pct=float(row["margin_pct"]),
        breakdown=row.get("breakdown") or {},
        expires_at=datetime.fromisoformat(row["expires_at"]),
        consumed_at=(
            datetime.fromisoformat(row["consumed_at"]) if row.get("consumed_at") else None
        ),
    )


def load_quote(quote_id: str, org_id: UUID | str) -> RunQuote:
    """Load a quote and verify it belongs to this org, is signed, and is live."""
    admin = get_supabase_admin()
    rows = (
        admin.table("run_quotes")
        .select("*")
        .eq("id", quote_id)
        .eq("organization_id", str(org_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise QuoteError("Quote not found")

    row = rows[0]
    expected = _sign(
        _canonical(
            row["id"], row["organization_id"], row["agent_count"], row["rounds"],
            row["platforms"], row["variants"], row["depth"], int(row["credits"]),
            row["expires_at"],
        )
    )
    if not hmac.compare_digest(expected, row.get("signature") or ""):
        logger.error("quote_signature_mismatch", quote_id=quote_id)
        raise QuoteError("Quote signature is invalid")

    quote = _row_to_quote(row)
    if quote.consumed_at is not None:
        raise QuoteError("This quote has already been used")
    if quote.expires_at < datetime.now(UTC):
        raise QuoteError("This quote has expired — reconfigure the run for a new price")
    return quote


def consume_quote(
    quote_id: str,
    org_id: UUID | str,
    simulation_id: str,
    actual_shape: tuple[int, int, int, int],
) -> RunQuote:
    """Redeem a quote for a specific run, after checking it matches the shape.

    The shape check is the point of the whole mechanism: a quote for 25 agents
    cannot be redeemed against a 250-agent simulation row, however the two were
    submitted.
    """
    quote = load_quote(quote_id, org_id)
    agents, rounds, platforms, variants = actual_shape

    if (quote.agent_count, quote.rounds, quote.platforms, quote.variants) != actual_shape:
        logger.error(
            "quote_shape_mismatch",
            quote_id=quote_id,
            quoted=f"{quote.agent_count}a/{quote.rounds}r/{quote.platforms}p/{quote.variants}v",
            actual=f"{agents}a/{rounds}r/{platforms}p/{variants}v",
        )
        raise QuoteError(
            "This quote does not match the run being started. Reconfigure the "
            "run to get a current price."
        )

    now = datetime.now(UTC)
    # `.is_("consumed_at", "null")` is a compare-and-set, and its result has to
    # be read or it guards nothing a caller can act on. `load_quote` above
    # refuses an already-consumed quote, but that is a read followed by a write
    # with a network round-trip between them — two starts in the same window
    # both pass it, and the second one's UPDATE then matches zero rows. With the
    # result discarded, the loser went on to be charged for a run the winner had
    # already paid for. Whoever claims the row redeems it; everyone else is told
    # the quote is spent.
    claimed = (
        get_supabase_admin().table("run_quotes").update({
            "consumed_at": now.isoformat(),
            "simulation_id": simulation_id,
        }).eq("id", quote_id).is_("consumed_at", "null").execute()
    ).data or []
    if not claimed:
        logger.warning(
            "quote_already_consumed", quote_id=quote_id, simulation_id=simulation_id
        )
        raise QuoteError("This quote has already been used")

    quote.consumed_at = now
    quote.simulation_id = simulation_id
    logger.info(
        "quote_consumed",
        quote_id=quote_id,
        simulation_id=simulation_id,
        credits=quote.credits,
    )
    return quote
