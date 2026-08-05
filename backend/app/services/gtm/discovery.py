# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# run_discovery(project_id, org_id, profile_row, *, max_queries=None,
#               created_by=None, adapter=None) -> dict
# preview_discovery(profile_row, *, max_queries=None) -> DiscoveryPreview
# reconcile_run(run) -> dict
# DiscoveryPreview, DiscoveryRefusedError, DiscoveryUnavailableError
# DISCOVERY_DEADLINE_SECONDS, QUERY_CONCURRENCY
# discovery_deadline_seconds(queries) -> int
# ─────────────────────────────────────────────────────────
"""Run one go-to-market discovery: ICP in, ranked candidates out.

**The job model, stated rather than inherited.** Discovery runs *inline*, in
the request that started it, with bounded parallelism and a hard deadline. It is
not an `asyncio.create_task`. Background jobs in this codebase are not durable
(HANDOFF §8 item 2 — no queue, no worker, every job is a task in the API
process), and open audit item 19 is specifically about detached tasks with no
strong reference, which the garbage collector may collect mid-flight. Detaching
this would trade a wait the founder is already having for a class of failure
that leaves a run marked `running` forever with nobody to notice.

**Failure behaviour, explicitly:**

  * Each query's candidates are written **as that query completes**, not at the
    end. Anything already found survives whatever happens next.
  * The whole batch runs under a `DISCOVERY_DEADLINE_SECONDS` deadline. On
    expiry the run is closed `partial` with the number of queries that finished
    — a real outcome with a count attached, not an error.
  * A single query that raises is logged with its query text and counted; the
    other queries continue and the run closes `partial`.
  * If the search provider itself is unavailable, no query can succeed, and the
    run closes `failed` with the provider's reason. That is deliberately not
    the same state as "found nothing".
  * **If the API process dies mid-run, the run row stays `running`.** There is
    no worker to reap it. That is the honest limit of the current
    infrastructure, and the alternative — pretending a detached task makes it
    durable — is worse. `completed_at IS NULL AND status = 'running'` older
    than the deadline is the query that identifies these.

**Credits are charged before the first search**, the same as a run. The compute
is spent whether or not the founder keeps the result, and a balance debited on
completion funds ten concurrent jobs from one balance.

**And reconciled after it.** Charging up front from the *requested* query count
is right; keeping the difference when the run delivered fewer is not. Every run
closes through `reconcile_run`, which prices the queries that actually ran and
credits the rest back — once, by a compare-and-set in the database. This module
used to say "there is no refund path for a partial run"; that was a deliberate
choice, and in front of the customer who paid 1,254 credits for 12 queries and
received 7 it was indefensible.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import ValidationError

from app.services.billing.agent_pricing import BudgetCheck, deduct_credits
from app.services.billing.usage_ledger import usage_context
from app.services.engine.personas.icp_schema import ICPArchetype, ICPProfile
from app.services.gtm import store
from app.services.gtm.exclusions import CategoryExclusions, build_exclusions
from app.services.gtm.extraction import extract_candidates
from app.services.gtm.pricing import (
    GTM_DISCOVERY_STAGE,
    check_discovery_budget,
    estimate_discovery_cost,
    reconcile_discovery_charge,
    search_fee_usd,
)
from app.services.gtm.privacy import (
    CONTACT_BLOCKED_DOMAINS,
    ContactGateUnavailableError,
    contact_discovery_gate,
)
from app.services.gtm.query_compiler import MAX_QUERIES_PER_DISCOVERY, compile_queries
from app.services.gtm.schema import Candidate, DiscoveryQuery
from app.services.gtm.scoring import score_candidates
from app.services.gtm.search_adapter import (
    AnthropicWebSearchAdapter,
    SearchAdapter,
    SearchUnavailableError,
)

log = structlog.get_logger()

# Queries in flight at once. Four keeps a twelve-query discovery inside the
# deadline while staying well under any per-organization search rate limit.
QUERY_CONCURRENCY = 4

# Wall clock ceiling for the whole batch. Past this the run closes `partial`
# with what it has.
#
# **A deadline is not a failure to hide, and it must not be a promise the
# product cannot keep.** At a flat 180s the estimate offered 12 queries and the
# first live 12-query run delivered 7 — the deadline was sized for a shape
# smaller than the one being sold. Two ways out: scale the deadline, or stop
# offering 12. This scales it, because the ICP compiler produces up to 12
# genuinely distinct angles and cutting the offer to what a fixed 180s happens
# to fit would shrink the product to fit a constant.
#
# Bounded, because the run is inline: the founder is holding an HTTP connection
# open, and a server that outlasts the client's timeout produces the worst
# outcome available — the credits are spent and the founder never sees the
# result. `frontend/src/lib/gtm.ts` waits `DISCOVERY_DEADLINE_SECONDS + 60`, and
# that constant moves in the same commit as this one.
#
# Sized so the largest discovery the estimate offers — `MAX_QUERIES_PER_DISCOVERY`
# at `QUERY_CONCURRENCY` — fits inside it. If either of those changes, this has
# to be checked against them again; `test_the_deadline_can_finish_what_the_estimate_sells`
# fails when it stops being true, rather than leaving it to the next customer to
# discover.
DISCOVERY_DEADLINE_SECONDS = 360

# Wall clock for one wave of `QUERY_CONCURRENCY` queries, plus a fixed margin
# for closing the run and replying.
#
# Measured, not assumed: run 534353e7 delivered 7 of 12 queries in 180s at
# concurrency 4, which is ~103s for four queries in flight. 110 is that with a
# little headroom; the margin covers `finish_run`, the reconciliation and the
# response. Re-derive from `gtm_discovery_runs` (completed_at - created_at over
# queries_completed) once there are enough runs to have a distribution rather
# than a point.
_SECONDS_PER_WAVE = 110
_DEADLINE_MARGIN_SECONDS = 20


def discovery_deadline_seconds(queries: int) -> int:
    """How long a batch of `queries` queries gets, bounded by the ceiling.

    A run of three queries has no business waiting six minutes before it is
    allowed to give up, and a run of twelve had no business being cut off at the
    time three would take. One wave is `QUERY_CONCURRENCY` queries in flight.
    """
    waves = max(1, -(-max(0, queries) // QUERY_CONCURRENCY))  # ceil division
    return min(
        DISCOVERY_DEADLINE_SECONDS,
        _DEADLINE_MARGIN_SECONDS + _SECONDS_PER_WAVE * waves,
    )


class DiscoveryRefusedError(RuntimeError):
    """Refused before anything was spent — no credits, no searches.

    Carries the `BudgetCheck` so the API can quote the shortfall rather than
    saying "not enough credits" with no number.
    """

    def __init__(self, budget: BudgetCheck) -> None:
        super().__init__(budget.message)
        self.budget = budget


class DiscoveryUnavailableError(RuntimeError):
    """The discovery could not start for a reason that is not the balance."""


def _profile_of(profile_row: dict[str, Any]) -> ICPProfile:
    try:
        return ICPProfile.model_validate(profile_row["profile"])
    except (KeyError, ValidationError) as exc:
        raise DiscoveryUnavailableError(
            f"ICP profile {profile_row.get('id')} does not validate: {exc}"
        ) from exc


@dataclass(frozen=True)
class DiscoveryPreview:
    """What a discovery would search for, and what it would leave out."""

    queries: list[DiscoveryQuery]
    exclusions: CategoryExclusions


def preview_discovery(
    profile_row: dict[str, Any],
    *,
    max_queries: int | None = None,
) -> DiscoveryPreview:
    """What this ICP would run, without spending anything.

    The founder sees this before committing credits. Both halves are pure
    functions of the same profile, so what this returns is what runs — which is
    the whole point of the screen, and the reason the exclusions travel with the
    queries rather than being fetched separately. A preview whose two halves
    were computed from two reads could disagree with itself.
    """
    profile = _profile_of(profile_row)
    return DiscoveryPreview(
        queries=compile_queries(
            profile,
            max_queries=min(
                max_queries or MAX_QUERIES_PER_DISCOVERY, MAX_QUERIES_PER_DISCOVERY
            ),
        ),
        exclusions=build_exclusions(profile),
    )


async def _run_one_query(
    query: DiscoveryQuery,
    archetype: ICPArchetype,
    profile: ICPProfile,
    adapter: SearchAdapter,
    run: dict[str, Any],
    include_contacts: bool,
    limit: asyncio.Semaphore,
    outcome: dict[str, Any],
) -> None:
    """Search, extract, score, store — for one compiled query."""
    async with limit:
        try:
            results = await adapter.search(
                query.query,
                blocked_domains=list(CONTACT_BLOCKED_DOMAINS) if include_contacts else None,
            )
        except SearchUnavailableError:
            # Provider-level: every other query will fail the same way. Raised
            # so the batch fails as a provider outage rather than degrading into
            # a run that reports an empty market.
            raise
        except Exception:
            log.exception("gtm_query_search_failed", query=query.query)
            outcome["failed"].append(query.query)
            return

        if not results:
            outcome["empty"].append(query.query)
            return

        try:
            candidates = await extract_candidates(
                results,
                archetype,
                profile,
                query=query.query,
                angle=query.angle,
                include_contacts=include_contacts,
            )
        except Exception:
            log.exception("gtm_query_extraction_failed", query=query.query)
            outcome["failed"].append(query.query)
            return

        ranked: list[Candidate] = score_candidates(candidates, archetype)
        if ranked:
            try:
                stored = store.insert_candidates(run, ranked)
            except Exception:
                # The searches are already paid for. A storage failure that
                # logged nothing would present as a query that found nothing.
                log.exception("gtm_candidate_store_failed", query=query.query)
                outcome["failed"].append(query.query)
                return
            outcome["stored"] += stored
            outcome["contacts"] += sum(len(c.contacts) for c in ranked)
        outcome["completed"].append(query.query)


async def run_discovery(
    project_id: str,
    org_id: str,
    profile_row: dict[str, Any],
    *,
    max_queries: int | None = None,
    created_by: str | None = None,
    adapter: SearchAdapter | None = None,
) -> dict[str, Any]:
    """Find real companies for one ICP. Returns the closed run row."""
    profile = _profile_of(profile_row)
    cap = min(max_queries or MAX_QUERIES_PER_DISCOVERY, MAX_QUERIES_PER_DISCOVERY)
    queries = compile_queries(profile, max_queries=cap)
    if not queries:
        raise DiscoveryUnavailableError(
            "This ICP has no archetype with enough detail to search on. Add a "
            "role, the tools they already use, or what they complain about."
        )

    # Company discovery is the default path and is complete on its own. The
    # gate only decides whether named people are collected as well.
    try:
        gate = contact_discovery_gate(org_id)
        include_contacts = gate.enabled
    except ContactGateUnavailableError as exc:
        # Cannot prove the org authorised contact collection, so it is not
        # done. Company discovery proceeds — refusing it too would make an
        # unrelated failure look like a broken feature.
        log.error("gtm_contact_gate_unavailable", org_id=org_id, detail=str(exc))
        include_contacts = False

    budget = check_discovery_budget(org_id, len(queries))
    if not budget.allowed:
        # Refused before it starts: nothing spent, nothing stored, no run row.
        log.info(
            "gtm_discovery_refused",
            org_id=org_id,
            queries=len(queries),
            credits_required=budget.credits_required,
            credits_remaining=budget.credits_remaining,
        )
        raise DiscoveryRefusedError(budget)

    estimate = estimate_discovery_cost(len(queries))
    deduct_credits(org_id, budget.credits_required)

    run = store.create_run(
        project_id=project_id,
        org_id=org_id,
        icp_profile_id=profile_row.get("id"),
        queries=queries,
        contacts_enabled=include_contacts,
        credits_charged=budget.credits_required,
        estimated_cost_usd=estimate.actual_cost_usd,
        created_by=created_by,
    )

    adapter = adapter or AnthropicWebSearchAdapter()
    by_id = {a.id: a for a in profile.archetypes}
    limit = asyncio.Semaphore(QUERY_CONCURRENCY)
    outcome: dict[str, Any] = {
        "completed": [], "failed": [], "empty": [], "stored": 0, "contacts": 0,
    }

    status = "completed"
    error: str | None = None
    deadline = discovery_deadline_seconds(len(queries))

    with usage_context(GTM_DISCOVERY_STAGE, organization_id=org_id):
        try:
            await asyncio.wait_for(
                asyncio.gather(*(
                    _run_one_query(
                        query, by_id[query.archetype_id], profile, adapter, run,
                        include_contacts, limit, outcome,
                    )
                    for query in queries
                    if query.archetype_id in by_id
                )),
                timeout=deadline,
            )
        except TimeoutError:
            status = "partial"
            error = f"deadline of {deadline}s reached"
            log.warning(
                "gtm_discovery_deadline",
                run_id=run["id"],
                deadline_seconds=deadline,
                completed=len(outcome["completed"]),
                total=len(queries),
            )
        except SearchUnavailableError as exc:
            status = "failed"
            error = str(exc)
            log.error("gtm_discovery_provider_unavailable", run_id=run["id"], detail=error)
        except Exception as exc:
            status = "failed"
            error = f"{type(exc).__name__}: {exc}"
            log.exception("gtm_discovery_failed", run_id=run["id"])

    if status == "completed" and outcome["failed"]:
        status = "partial"
        error = f"{len(outcome['failed'])} of {len(queries)} queries failed"

    searches = getattr(adapter, "searches_performed", 0)
    fee = search_fee_usd(searches)

    # The fee reaches `llm_usage` per call, via `record_llm_call(surcharge_usd=…)`
    # in the search adapter. This is the run-level total, recorded on the run row
    # and logged so the two can be reconciled against each other: the adapter's
    # count and the ledger's sum are independent paths to the same number, and a
    # disagreement between them means searches were billed by a call whose row
    # never landed.
    log.info(
        "gtm_search_fee_recorded",
        run_id=run["id"],
        org_id=org_id,
        searches=searches,
        fee_usd=float(fee),
        stage=GTM_DISCOVERY_STAGE,
    )

    closed = store.finish_run(
        run["id"],
        status,
        queries_completed=len(outcome["completed"]),
        queries_failed=len(outcome["failed"]),
        queries_empty=len(outcome["empty"]),
        candidates_found=outcome["stored"],
        contacts_found=outcome["contacts"],
        searches_performed=searches,
        search_fee_usd=float(fee),
        error=error,
    )

    # Written before the log line so `gtm_discovery_finished` states the net
    # charge rather than the gross one. A log that reports what was taken and
    # never what was given back is how the original defect stayed invisible for
    # as long as it did.
    closed = reconcile_run(closed or {**run, "status": status, "error": error})

    log.info(
        "gtm_discovery_finished",
        run_id=run["id"],
        org_id=org_id,
        status=status,
        queries=len(queries),
        completed=len(outcome["completed"]),
        failed=len(outcome["failed"]),
        empty=len(outcome["empty"]),
        candidates=outcome["stored"],
        contacts=outcome["contacts"],
        contacts_enabled=include_contacts,
        searches=searches,
        credits_charged=budget.credits_required,
        credits_refunded=int(closed.get("credits_refunded") or 0),
        credits_net=int(closed.get("credits_charged") or 0)
        - int(closed.get("credits_refunded") or 0),
    )
    return closed


def reconcile_run(run: dict[str, Any]) -> dict[str, Any]:
    """Charge a closed run for what it delivered. Returns the run row.

    Safe to call any number of times on the same run — the refund is claimed by
    a compare-and-set in `refund_discovery_credits`, so the second call credits
    nothing. That is what makes this callable from the end of `run_discovery`
    *and* from `POST /gtm/runs/{id}/reconcile` without the two racing.

    A failure here never fails the run. The founder's candidates are stored and
    the run row is closed; a refund that could not be attempted is an
    `gtm_refund_unavailable` at error level with everything needed to replay it
    by hand, which is strictly better than losing the discovery to a billing
    problem. The most likely cause is migration 028 not yet being applied.
    """
    delivery = reconcile_discovery_charge(run)
    refunded = int(run.get("credits_refunded") or 0)

    if run.get("refunded_at"):
        # Already settled. Reported rather than silently skipped, because the
        # difference between "owed nothing" and "already paid" is the difference
        # a double-callback investigation turns on.
        log.info(
            "gtm_discovery_already_reconciled",
            run_id=run.get("id"),
            credits_refunded=refunded,
        )
        return run

    try:
        refunded = store.refund_run(run["id"], delivery.credits_refundable)
    except store.RefundUnavailableError as exc:
        log.error(
            "gtm_refund_unavailable",
            run_id=run.get("id"),
            organization_id=run.get("organization_id"),
            credits_owed=delivery.credits_refundable,
            queries_requested=delivery.queries_requested,
            queries_delivered=delivery.queries_delivered,
            detail=str(exc),
        )
        return run

    # Reflected onto the row the caller already holds rather than re-read: the
    # RPC is authoritative about what it credited, and a second round trip could
    # only disagree with it.
    return {
        **run,
        "credits_refunded": refunded,
        "refunded_at": datetime.now(UTC).isoformat(),
    }
