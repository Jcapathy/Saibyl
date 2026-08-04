# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# run_discovery(project_id, org_id, profile_row, *, max_queries=None,
#               created_by=None, adapter=None) -> dict
# preview_queries(profile_row, *, max_queries=None) -> list[DiscoveryQuery]
# DiscoveryRefusedError, DiscoveryUnavailableError
# DISCOVERY_DEADLINE_SECONDS, QUERY_CONCURRENCY
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
completion funds ten concurrent jobs from one balance. There is no refund path
for a partial run: what a partial run consumed is what it consumed, and the
credits charged, the searches performed and the queries completed are all on the
run row so the difference is visible rather than argued about.
"""
from __future__ import annotations

import asyncio
from typing import Any

import structlog
from pydantic import ValidationError

from app.services.billing.agent_pricing import BudgetCheck, deduct_credits
from app.services.billing.usage_ledger import usage_context
from app.services.engine.personas.icp_schema import ICPArchetype, ICPProfile
from app.services.gtm import store
from app.services.gtm.extraction import extract_candidates
from app.services.gtm.pricing import (
    GTM_DISCOVERY_STAGE,
    check_discovery_budget,
    estimate_discovery_cost,
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

# Wall clock for the whole batch. Past this the run closes `partial` with what
# it has. Chosen so an HTTP client with a conventional timeout is still
# connected when the response arrives; raising it means raising the client's
# timeout too, in the same commit.
DISCOVERY_DEADLINE_SECONDS = 180


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


def preview_queries(
    profile_row: dict[str, Any],
    *,
    max_queries: int | None = None,
) -> list[DiscoveryQuery]:
    """The queries this ICP would run, without spending anything.

    The founder sees these before committing credits. The compiler is
    deterministic, so what this returns is what runs.
    """
    profile = _profile_of(profile_row)
    return compile_queries(
        profile,
        max_queries=min(max_queries or MAX_QUERIES_PER_DISCOVERY, MAX_QUERIES_PER_DISCOVERY),
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
                timeout=DISCOVERY_DEADLINE_SECONDS,
            )
        except TimeoutError:
            status = "partial"
            error = f"deadline of {DISCOVERY_DEADLINE_SECONDS}s reached"
            log.warning(
                "gtm_discovery_deadline",
                run_id=run["id"],
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
    )
    return closed or {**run, "status": status, "error": error}
