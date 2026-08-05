"""A discovery is charged for what it delivered, not for what it asked for.

The defect these tests exist for, in production, run 534353e7:

    query_count=12  queries_completed=6  queries_empty=1  queries_failed=0
    status=partial  error="deadline of 180s reached"
    credits_charged=1254   (the full 12-query price)   candidates_found=1

Twelve queries were bought and seven ran. Nothing reconciled. That is the same
shape as the apportionment defect where a customer paid for 48 agents and got 45
— the customer sees one number before committing and a different quantity of
work afterwards, and the difference stays in Saibyl's pocket unless something
gives it back.

Log assertions use `structlog.testing.capture_logs`; `caplog` passes vacuously
in this codebase because structlog is not bound to stdlib logging outside
`create_app`.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from structlog.testing import capture_logs

from app.services.gtm import discovery, store
from app.services.gtm.pricing import (
    delivered_queries,
    estimate_discovery_cost,
    reconcile_discovery_charge,
)
from app.services.gtm.query_compiler import MAX_QUERIES_PER_DISCOVERY

# The production run, verbatim.
LIVE_RUN = {
    "id": "534353e7-a3ab-4f42-852f-da53103f9f2b",
    "organization_id": "ac1b90b7-0c24-4987-b163-4dbc0010e0ff",
    "status": "partial",
    "query_count": 12,
    "queries_completed": 6,
    "queries_empty": 1,
    "queries_failed": 0,
    "candidates_found": 1,
    "credits_charged": 1254,
    "error": "deadline of 180s reached",
    "credits_refunded": 0,
    "refunded_at": None,
}


def _events(logs) -> set[str]:
    return {entry["event"] for entry in logs}


# ── The arithmetic ───────────────────────────────────────


def test_the_live_partial_run_is_owed_the_five_queries_it_never_ran():
    """1,254 charged for 12; 7 delivered are worth 732; 522 goes back."""
    delivery = reconcile_discovery_charge(LIVE_RUN)

    assert delivery.queries_requested == 12
    assert delivery.queries_delivered == 7
    assert delivery.credits_charged == 1254
    assert delivery.credits_kept == estimate_discovery_cost(7).credits == 732
    assert delivery.credits_refundable == 522
    assert delivery.owes_refund


def test_an_empty_search_is_delivered_work_and_a_failed_one_is_not():
    """An empty result is a finding; a failure is Saibyl's cost to eat.

    "Nobody out there matches this" costs a full search to establish and is a
    real answer about a market. A query that raised gave the founder nothing,
    so it is not billed — the direction of the doubt has to favour the person
    who paid or the guarantee is decorative.
    """
    run = {"query_count": 6, "queries_completed": 2, "queries_empty": 2, "queries_failed": 2}
    assert delivered_queries(run) == 4


def test_a_run_that_delivered_everything_is_owed_nothing():
    run = {**LIVE_RUN, "queries_completed": 11, "queries_empty": 1}
    delivery = reconcile_discovery_charge(run)

    assert delivery.queries_delivered == 12
    assert delivery.credits_refundable == 0
    assert not delivery.owes_refund


def test_a_run_that_delivered_nothing_is_refunded_in_full():
    """A provider outage charged in full is the worst version of this defect."""
    run = {**LIVE_RUN, "status": "failed", "queries_completed": 0, "queries_empty": 0,
           "queries_failed": 12}
    assert reconcile_discovery_charge(run).credits_refundable == 1254


def test_impossible_counters_cannot_refund_more_than_was_charged():
    """The counters and the total are written by different code paths.

    A row claiming more delivered queries than it requested must not produce a
    negative refund, and one claiming none must not produce a refund larger than
    the charge.
    """
    over = reconcile_discovery_charge({**LIVE_RUN, "queries_completed": 99})
    assert over.queries_delivered == 12
    assert over.credits_refundable == 0

    under = reconcile_discovery_charge({**LIVE_RUN, "credits_charged": 10,
                                        "queries_completed": 0, "queries_empty": 0})
    assert under.credits_kept == 0
    assert under.credits_refundable == 10


def test_the_refund_never_re_rounds_what_the_quote_already_rounded_up():
    """Pro-rating the charge would quietly keep the rounding remainder.

    `credits_for` rounds up once, at the point of sale. Refunding
    `charged * undelivered / requested` would round a second time against the
    customer on every partial run.
    """
    for delivered in range(0, MAX_QUERIES_PER_DISCOVERY + 1):
        charged = estimate_discovery_cost(MAX_QUERIES_PER_DISCOVERY).credits
        run = {"query_count": MAX_QUERIES_PER_DISCOVERY, "credits_charged": charged,
               "queries_completed": delivered, "queries_empty": 0, "queries_failed": 0}
        delivery = reconcile_discovery_charge(run)
        assert delivery.credits_kept == estimate_discovery_cost(delivered).credits
        assert delivery.credits_kept + delivery.credits_refundable == charged


# ── Idempotency ──────────────────────────────────────────


class _RefundRpc:
    """A stand-in for `refund_discovery_credits` with its real semantics.

    The compare-and-set lives in the database, so this models the row it claims:
    the first call for a run returns the amount, every later call returns 0.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []
        self._claimed: set[str] = set()

    def rpc(self, name, params):
        assert name == "refund_discovery_credits", name
        assert set(params) == {"run_uuid", "amount"}, params
        self.calls.append((params["run_uuid"], params["amount"]))
        first = params["run_uuid"] not in self._claimed
        self._claimed.add(params["run_uuid"])
        amount = params["amount"] if first else 0
        return SimpleNamespace(
            execute=lambda: SimpleNamespace(
                data=[{"refunded": amount, "balance": 12276 if amount else None}]
            )
        )


def test_a_second_refund_for_the_same_run_credits_nothing(monkeypatch):
    """A retry or a double callback must not grant twice."""
    rpc = _RefundRpc()
    monkeypatch.setattr(store, "get_supabase_admin", lambda: rpc)

    assert store.refund_run(LIVE_RUN["id"], 522) == 522
    assert store.refund_run(LIVE_RUN["id"], 522) == 0
    assert store.refund_run(LIVE_RUN["id"], 522) == 0

    # All three reached the database. The check is the database's, not ours —
    # a read-then-write in Python has a window between the two halves, which is
    # exactly how a run gets refunded twice.
    assert len(rpc.calls) == 3


def test_reconcile_run_is_safe_to_call_repeatedly(monkeypatch):
    rpc = _RefundRpc()
    monkeypatch.setattr(store, "get_supabase_admin", lambda: rpc)

    first = discovery.reconcile_run(LIVE_RUN)
    assert first["credits_refunded"] == 522
    assert first["refunded_at"] is not None

    # The row now carries `refunded_at`, so the second pass does not even reach
    # the database.
    with capture_logs() as logs:
        second = discovery.reconcile_run(first)
    assert second["credits_refunded"] == 522
    assert "gtm_discovery_already_reconciled" in _events(logs)
    assert len(rpc.calls) == 1


def test_grant_credits_is_never_used_for_a_refund(monkeypatch):
    """`grant_credits` starts a new billing cycle at the refund amount.

    Its real body in production — verified against `pg_proc`, not read off the
    migration — sets `credits_granted = amount` and `credit_cycle_start = NOW()`.
    Refunding 522 credits through it would tell a starter org, and every screen
    that reads the grant, that its plan is now 522 credits a month.
    """
    seen: list[str] = []

    class _Admin:
        def rpc(self, name, params):
            seen.append(name)
            return SimpleNamespace(
                execute=lambda: SimpleNamespace(data=[{"refunded": 0, "balance": None}])
            )

    monkeypatch.setattr(store, "get_supabase_admin", lambda: _Admin())
    store.refund_run(LIVE_RUN["id"], 522)
    assert seen == ["refund_discovery_credits"]


def test_a_refund_that_cannot_be_attempted_is_loud_and_not_fatal(monkeypatch):
    """Migration 028 unapplied must not cost the founder their candidates.

    The run is closed and the companies are stored. Losing that to a billing
    problem would be a worse outcome than the missing refund, so this logs
    everything needed to replay the refund by hand and returns the run.
    """
    class _Broken:
        def rpc(self, name, params):
            raise RuntimeError("function public.refund_discovery_credits does not exist")

    monkeypatch.setattr(store, "get_supabase_admin", lambda: _Broken())

    with capture_logs() as logs:
        run = discovery.reconcile_run(LIVE_RUN)

    assert run["credits_refunded"] == 0
    assert run.get("refunded_at") is None
    entry = next(e for e in logs if e["event"] == "gtm_refund_unavailable")
    assert entry["credits_owed"] == 522
    assert entry["queries_delivered"] == 7
    assert entry["organization_id"] == LIVE_RUN["organization_id"]


# ── The deadline ─────────────────────────────────────────


def test_the_deadline_can_finish_what_the_estimate_sells():
    """A deadline sized for a smaller run than the one being sold is the defect.

    At a flat 180s the estimate offered 12 queries and the first live 12-query
    run delivered 7. This fails if `MAX_QUERIES_PER_DISCOVERY`,
    `QUERY_CONCURRENCY` or the ceiling ever drift back into that state, rather
    than leaving it to the next customer to find out.
    """
    waves = -(-MAX_QUERIES_PER_DISCOVERY // discovery.QUERY_CONCURRENCY)
    needed = discovery._DEADLINE_MARGIN_SECONDS + discovery._SECONDS_PER_WAVE * waves
    assert discovery.DISCOVERY_DEADLINE_SECONDS >= needed, (
        f"the estimate sells {MAX_QUERIES_PER_DISCOVERY} queries, which need "
        f"{needed}s at concurrency {discovery.QUERY_CONCURRENCY}, but the ceiling "
        f"is {discovery.DISCOVERY_DEADLINE_SECONDS}s"
    )
    assert discovery.discovery_deadline_seconds(MAX_QUERIES_PER_DISCOVERY) == needed


@pytest.mark.parametrize("queries", [0, 1, 3, 4, 5, 8, 12])
def test_the_deadline_scales_with_the_query_count(queries):
    """A three-query run has no business waiting six minutes to give up."""
    seconds = discovery.discovery_deadline_seconds(queries)
    assert 0 < seconds <= discovery.DISCOVERY_DEADLINE_SECONDS
    assert seconds >= discovery.discovery_deadline_seconds(max(0, queries - 4))


def test_the_client_waits_longer_than_the_server_deadline():
    """The frontend mirror moves in the same commit as the ceiling.

    A client timeout below the server's deadline abandons a run that is about to
    succeed — and the credits are already spent, so the founder pays for a
    result they never see.
    """
    import re
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "frontend" / "src" / "lib" / "gtm.ts"
    ).read_text(encoding="utf-8")
    mirrored = int(re.search(r"DISCOVERY_DEADLINE_SECONDS = (\d+)", source).group(1))

    assert mirrored == discovery.DISCOVERY_DEADLINE_SECONDS, (
        "frontend/src/lib/gtm.ts mirrors the server deadline and has drifted "
        f"({mirrored}s vs {discovery.DISCOVERY_DEADLINE_SECONDS}s)"
    )
