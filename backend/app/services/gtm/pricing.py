# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# GTM_DISCOVERY_STAGE, GTM_SEARCH_TOKENS, GTM_EXTRACTION_TOKENS
# WEB_SEARCH_USD_PER_REQUEST, SEARCHES_PER_QUERY
# estimate_discovery_cost(queries) -> DiscoveryCostEstimate
# check_discovery_budget(org_id, queries) -> BudgetCheck
# search_fee_usd(searches) -> Decimal
# delivered_queries(run) -> int
# reconcile_discovery_charge(run) -> DeliveryReconciliation
# ─────────────────────────────────────────────────────────
"""What a go-to-market discovery costs, and the one part of it the ledger
cannot see.

HANDOFF §7 closes the cost model and names three things that legitimately
reopen it. A new unit of work is one of them, and this is one: discovery is not
a run, not a report section and not an off-run synthesis pass. It is priced per
**compiled query**, because that is the unit that maps to the work — one query
is one search turn plus one extraction turn — and because the query count is the
number a founder can see before committing.

**These figures are estimates, and every one of them is labelled as such.**
There are no `llm_usage` rows for `gtm_discovery` yet, so unlike every other
profile in `agent_pricing.py` these are not derived from the ledger. They are
constructed from bounds the code actually enforces rather than from guesses
about behaviour, which is the most defensible thing available before the first
live run:

  search turn, input   19,000  `max_uses` is 2 (search_adapter.MAX_SEARCHES_PER_QUERY)
                               and retrieved page content is billed as input to
                               that turn. ~9,000 tokens per search of decrypted
                               result content, plus a ~600-token prompt. The
                               multiplier is enforced; the per-search content
                               size is the estimated part.
  search turn, output   1,200  MAX_SOURCES_PER_QUERY is 8 digests, ~150 tokens
                               each, bounded by _SEARCH_MAX_TOKENS = 3,000.
  extract turn, input   2,900  8 digests (~150 each) + the archetype brief
                               (~900) + the tool schema (~800).
  extract turn, output  1,800  MAX_CANDIDATES_PER_QUERY is 8 records with
                               evidence, ~220 tokens each, bounded by
                               _EXTRACTION_MAX_TOKENS = 6,000.

Both are high-side within their bounds, which is the safe direction: an
over-quoted stage costs the customer margin they can see, an under-quoted one
costs Saibyl margin nobody sees until reconciliation. **Re-derive from the
ledger after the first live discovery** with the query in HANDOFF §7, scoped to
`stage = 'gtm_discovery'`. The two rows will be distinguishable by `model` — the
search turn runs on the fast model, the extraction turn on the main one.

**The per-search charge is real money no token count can express**, and it does
reach the ledger. The Anthropic web search tool bills **$10 per 1,000 searches**
on top of tokens. `record_llm_call` takes `surcharge_usd` for exactly this, and
the search adapter reports the searches billed on a response onto the same
`llm_usage` row as the tokens that response produced — read off one `usage`
object, so the fee cannot drift from the call that incurred it.

This is load-bearing rather than tidy. `reconcile_run_cost` sums
`llm_usage.cost_usd` to decide whether the margin floor held, so a cost that
never arrives there is one the gate structurally cannot see: the stage would
reconcile as cheaper than it is, and `margin_floor_breached` could not fire for
the missing portion. At 2 searches a query and 12 queries a discovery the fee is
$0.24, which is ~19% of serving cost — not a rounding error.

⚠ One consequence for anyone re-deriving profiles: `gtm_discovery` rows carry a
`cost_usd` deliberately higher than their token counts imply. The re-derivation
query in HANDOFF §7 reads token medians and is unaffected; a cost-based
derivation would over-state this stage.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from pydantic import BaseModel

from app.core.config import settings
from app.services.billing.agent_pricing import (
    GTM_EXTRACTION,
    GTM_SEARCH,
    MIN_MARGIN_PCT,
    TARGET_MARGIN_PCT,
    WEB_SEARCH_USD_PER_REQUEST,
    BudgetCheck,
    credits_for,
    get_credit_balance,
    search_fee_usd,
    standard_run_credits,
)
from app.services.billing.model_pricing import cost_usd
from app.services.gtm.query_compiler import MAX_QUERIES_PER_DISCOVERY
from app.services.gtm.search_adapter import MAX_SEARCHES_PER_QUERY

log = structlog.get_logger()

# The ledger stage name. New, as HANDOFF §7 requires for a new unit of work —
# spend that is not in `llm_usage` under a stage is invisible to
# `reconcile_run_cost`, and the margin gate reads that ledger.
GTM_DISCOVERY_STAGE = "gtm_discovery"


@dataclass(frozen=True)
class StageTokens:
    """Expected tokens for one unit of work, mirroring `_StageProfile`.

    Declared here rather than in `agent_pricing.py` because this service owns
    no file there. The profile to add is reported alongside this build; until
    it is added, this is the single source of truth and nothing else reads it.
    """

    input_tokens: int
    output_tokens: int


# Per compiled query. **These now live in `agent_pricing.py`**, alongside every
# other stage profile, and are re-exported here so this module's readers keep
# one import. They were declared locally only because this service owned no
# file there during the build.
#
# Do not reintroduce local copies. Every stage profile living in one module is
# what makes "re-derive whenever prompts change" (HANDOFF §7) a single, findable
# operation — a profile kept beside its own service is a profile the next
# recalibration pass will miss, and an un-recalibrated profile is silently wrong
# rather than loudly absent.
GTM_SEARCH_TOKENS = StageTokens(
    input_tokens=GTM_SEARCH.input_tokens,
    output_tokens=GTM_SEARCH.output_tokens,
)
GTM_EXTRACTION_TOKENS = StageTokens(
    input_tokens=GTM_EXTRACTION.input_tokens,
    output_tokens=GTM_EXTRACTION.output_tokens,
)

# `WEB_SEARCH_USD_PER_REQUEST` and `search_fee_usd` are re-exported from
# `agent_pricing` above — $10 per 1,000 searches, Anthropic first-party rates.
# One constant, not a number scattered through the quote path.
__all__ = [
    "GTM_EXTRACTION_TOKENS",
    "GTM_SEARCH_TOKENS",
    "SEARCHES_PER_QUERY",
    "WEB_SEARCH_USD_PER_REQUEST",
    "DeliveryReconciliation",
    "DiscoveryCostEstimate",
    "delivered_queries",
    "estimate_discovery_cost",
    "reconcile_discovery_charge",
    "search_fee_usd",
]

# Charged at the tool's `max_uses` rather than at an expected value. The API
# bills only searches that actually ran, so quoting the ceiling over-charges a
# query that needed one search — the safe direction, and the only one available
# before the ledger can say what the real rate is.
SEARCHES_PER_QUERY = MAX_SEARCHES_PER_QUERY


class DiscoveryCostEstimate(BaseModel):
    """What one discovery costs to serve, and what it charges.

    Separate from `SimulationCostEstimate` and `SynthesisCostEstimate` for the
    reason given in the latter: a shape-shaped estimate with zeros in every
    shape field invites a caller to price the wrong thing with it. Discovery has
    queries and searches, not agents and rounds.
    """

    queries: int
    searches: int
    token_cost_usd: float
    # Broken out rather than folded in, because it is the component the token
    # ledger cannot corroborate.
    search_fee_usd: float
    actual_cost_usd: float
    retail_cost_usd: float
    credits: int
    margin_pct: float
    standard_run_equivalents: float
    # False until these profiles are re-derived from live `llm_usage` rows.
    measured: bool = False


def _token_cost(queries: int) -> Decimal:
    """Token cost of `queries` queries, across both turns and both models."""
    search = cost_usd(
        settings.llm_fast_model,
        input_tokens=GTM_SEARCH_TOKENS.input_tokens * queries,
        output_tokens=GTM_SEARCH_TOKENS.output_tokens * queries,
    )
    extraction = cost_usd(
        settings.llm_model,
        input_tokens=GTM_EXTRACTION_TOKENS.input_tokens * queries,
        output_tokens=GTM_EXTRACTION_TOKENS.output_tokens * queries,
    )
    return search + extraction


def _standard_run_credits() -> int:
    """Credits for the reference run, from `agent_pricing`'s own definition.

    Derived rather than hardcoded so the "worth N standard runs" line moves when
    the token profiles are recalibrated, instead of quietly describing a run
    shape that no longer costs that.

    **Not rebuilt from `STANDARD_RUN` here.** That tuple carries agents, rounds,
    platforms and variants — it does not carry `subject_brief`, and the
    reference run does carry one. Reconstructing the reference from the tuple
    alone computed a figure ~10% below the one every quote in the product is
    compared against, which made this module's "≈ N standard runs" line quietly
    overstate how much of a founder's balance a discovery is worth.
    `standard_run_credits()` is public for exactly this reason.
    """
    return standard_run_credits()


def estimate_discovery_cost(queries: int) -> DiscoveryCostEstimate:
    """Price a discovery of `queries` compiled queries."""
    queries = max(0, min(queries, MAX_QUERIES_PER_DISCOVERY))
    searches = queries * SEARCHES_PER_QUERY

    tokens = _token_cost(queries)
    fee = search_fee_usd(searches)
    actual = tokens + fee

    retail = actual / (Decimal("1") - TARGET_MARGIN_PCT / Decimal("100"))
    floor = actual / (Decimal("1") - MIN_MARGIN_PCT / Decimal("100"))
    retail = max(retail, floor)
    margin = (retail - actual) / retail * Decimal("100") if retail > 0 else Decimal("0")

    standard = _standard_run_credits()
    credits = credits_for(actual)

    return DiscoveryCostEstimate(
        queries=queries,
        searches=searches,
        token_cost_usd=float(tokens),
        search_fee_usd=float(fee),
        actual_cost_usd=float(actual),
        retail_cost_usd=float(retail),
        credits=credits,
        margin_pct=float(round(margin, 2)),
        standard_run_equivalents=round(credits / standard, 2) if standard else 0.0,
    )


def check_discovery_budget(org_id: UUID | str, queries: int) -> BudgetCheck:
    """Whether an org can afford this discovery, in credits.

    Charged at the start, like a run. The compute is spent whether or not the
    founder keeps the result, and a balance that is only debited on completion
    funds ten concurrent jobs at once.
    """
    estimate = estimate_discovery_cost(queries)
    balance, _granted, _plan = get_credit_balance(org_id)

    required = estimate.credits
    allowed = balance >= required
    share = round(required * 100 / balance, 2) if balance > 0 else 100.0

    if allowed:
        message = (
            f"Finding prospects from {estimate.queries} searches uses "
            f"{required:,} of your {balance:,} credits."
        )
    else:
        message = (
            f"Not enough credits. Finding prospects from {estimate.queries} "
            f"searches needs {required:,}; you have {balance:,}."
        )

    return BudgetCheck(
        allowed=allowed,
        credits_required=required,
        credits_remaining=balance,
        credits_after=max(0, balance - required),
        balance_share_pct=share,
        estimated_cost_usd=estimate.actual_cost_usd,
        retail_price_usd=estimate.retail_cost_usd,
        message=message,
    )


# ---------------------------------------------------------------------------
# Reconciliation — charged for requested, kept for delivered
# ---------------------------------------------------------------------------
#
# Credits are taken before the first search, from the *requested* query count.
# That part is right and stays: the compute is spent whether or not the founder
# keeps the result, and a balance debited on completion funds ten concurrent
# jobs from one balance.
#
# What was wrong is that nothing gave the difference back. Run 534353e7 asked
# for 12 queries, ran 7, closed `partial` on the deadline, and kept the full
# 12-query price — the same shape as the apportionment defect where a customer
# paid for 48 agents and received 45. "No refund on partial" was a deliberate
# choice and it is indefensible in front of the person who paid.


class DeliveryReconciliation(BaseModel):
    """What a closed run asked for, what it delivered, and what it should keep.

    Pure arithmetic over a run row. It moves no money and touches no database —
    `store.refund_run` does that, so this can be asserted against directly and so
    the number quoted to the customer and the number credited are the same
    expression evaluated once.
    """

    queries_requested: int
    queries_delivered: int
    credits_charged: int
    #: What the delivered work is worth at the same per-query rate.
    credits_kept: int
    #: `credits_charged - credits_kept`, never negative.
    credits_refundable: int

    @property
    def owes_refund(self) -> bool:
        return self.credits_refundable > 0


def delivered_queries(run: Mapping[str, Any]) -> int:
    """Queries this run actually put a result in front of the founder for.

    `completed + empty`. Those two are the queries that reached the search
    provider and produced an answer — an empty result is a real finding about a
    market, priced the same as a full one because it costs the same to obtain.

    **`failed` is not delivered.** A query that raised in search or extraction
    consumed some spend and gave the customer nothing, and Saibyl eats the cost
    of its own failures rather than billing for them. That is the whole point of
    charging for delivered work: the direction of the doubt has to favour the
    person who paid, or the guarantee is decorative.

    Clamped to `query_count` so a row with impossible counters — the counters and
    the total are written by different code paths — can never produce a negative
    refund or a `credits_kept` above what was charged.
    """
    requested = max(0, int(run.get("query_count") or 0))
    completed = max(0, int(run.get("queries_completed") or 0))
    empty = max(0, int(run.get("queries_empty") or 0))
    return min(requested, completed + empty)


def reconcile_discovery_charge(run: Mapping[str, Any]) -> DeliveryReconciliation:
    """Price a closed run against what it actually delivered.

    The refund is `charged - estimate_discovery_cost(delivered).credits` rather
    than a pro-rata share of `charged`, so the customer keeps the benefit of the
    same rounding rule the original quote used (`credits_for` rounds up, once,
    at the point of sale). Pro-rating the charge instead would re-round a figure
    that was already rounded up and quietly keep the remainder.

    `credits_kept` is floored at zero and capped at `credits_charged`: a run can
    never be refunded more than it took, whatever the counters say.
    """
    requested = max(0, int(run.get("query_count") or 0))
    charged = max(0, int(run.get("credits_charged") or 0))
    delivered = delivered_queries(run)

    kept = min(charged, estimate_discovery_cost(delivered).credits)
    return DeliveryReconciliation(
        queries_requested=requested,
        queries_delivered=delivered,
        credits_charged=charged,
        credits_kept=kept,
        credits_refundable=max(0, charged - kept),
    )
