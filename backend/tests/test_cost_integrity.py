"""Tests for the cost-integrity gate and the metering ledger behind it.

Every test here guards the same failure shape: a lookup that found nothing
returning the same value as a lookup that found zero. Those two are opposite
facts — "unmeasured" and "free" — and collapsing them is what let a run pass the
margin gate, charge nothing, and report success.

The margin-floor check is the only signal that reopens the closed cost model, so
the assertion that matters most is that an empty ledger makes the gate report
`None` rather than pass.
"""
from __future__ import annotations

import pytest
from structlog.testing import capture_logs

from app.services.billing import usage_ledger
from app.workers import analysis_tasks


def _events(logs) -> set[str]:
    """Event names from a `capture_logs` block.

    structlog is not bound to stdlib logging outside `create_app`, so `caplog`
    would see nothing and every log assertion here would pass vacuously — which
    is the same defect these tests exist to catch.
    """
    return {entry["event"] for entry in logs}


# ── Fakes ────────────────────────────────────────────────

class _FakeQuery:
    """Chainable stub covering the postgrest builder calls used here."""

    def __init__(self, data):
        self._data = data

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def update(self, *_args, **_kwargs):
        return self

    def execute(self):
        return type("Result", (), {"data": self._data})()


class _FakeAdmin:
    def __init__(self, tables=None):
        self.tables = tables or {}

    def table(self, name):
        return _FakeQuery(self.tables.get(name, []))


class _FailingInsert:
    def __init__(self):
        self.attempts = 0

    def table(self, _name):
        return self

    def insert(self, rows):
        self.attempts += 1
        raise RuntimeError("connection reset by peer")


class _RecordingInsert:
    def __init__(self):
        self.inserted = []

    def table(self, _name):
        return self

    def insert(self, rows):
        self.inserted.append(list(rows))
        return self

    def execute(self):
        return type("Result", (), {"data": []})()


def _ctx(**kwargs):
    return usage_ledger._UsageContext(
        stage=kwargs.get("stage", "agent_actions"),
        simulation_id=kwargs.get("simulation_id", "sim-1"),
        organization_id=kwargs.get("organization_id", "org-1"),
    )


def _row(cost=0.01):
    return {"stage": "agent_actions", "model": "claude-haiku-4-5", "cost_usd": cost}


# ── The margin gate must not pass on no data ─────────────

def test_empty_ledger_does_not_pass_the_margin_gate(monkeypatch):
    """The load-bearing one.

    `floor_price = ... if measured_usd else 0.0` made `retail >= 0.0`
    unconditionally true, so a run with no metering at all reported
    `margin_floor_held=True` and charged `credits_for(0) == 0`. A gate that
    cannot fail is not a gate.
    """
    monkeypatch.setattr(
        analysis_tasks,
        "get_simulation_cost",
        lambda _sim: {
            "total_cost_usd": None,
            "by_stage": [],
            "available": False,
            "reason": "no_ledger_rows",
        },
    )

    result = analysis_tasks.reconcile_run_cost("sim-1", "org-1")

    assert result["cost_reconciled"] is False
    assert result["margin_floor_held"] is None, "an unchecked gate must not report a pass"
    assert result["credits_charged"] == 0
    assert result["reason"] == "no_ledger_rows"


def test_zero_measured_cost_does_not_pass_the_margin_gate(monkeypatch):
    """Rows present but summing to nothing is the same lie with more steps."""
    monkeypatch.setattr(
        analysis_tasks,
        "get_simulation_cost",
        lambda _sim: {
            "total_cost_usd": 0.0,
            "by_stage": [_row(cost=0.0)],
            "available": True,
        },
    )

    result = analysis_tasks.reconcile_run_cost("sim-1", "org-1")

    assert result["cost_reconciled"] is False
    assert result["margin_floor_held"] is None
    assert result["reason"] == "zero_measured_cost"


def test_an_unreconciled_run_says_so(monkeypatch):
    """A completed run that will not be charged must be loud about it."""
    monkeypatch.setattr(
        analysis_tasks,
        "get_simulation_cost",
        lambda _sim: {"available": False, "reason": "lookup_failed", "total_cost_usd": None},
    )

    with capture_logs() as logs:
        analysis_tasks.reconcile_run_cost("sim-1", "org-1")

    assert "cost_reconciliation_unavailable" in _events(logs)


def test_a_real_underpriced_run_still_breaches_the_floor(monkeypatch):
    """The gate must keep failing on the case it exists for."""
    charged = []
    monkeypatch.setattr(
        analysis_tasks,
        "get_simulation_cost",
        lambda _sim: {"total_cost_usd": 10.0, "by_stage": [_row(10.0)], "available": True},
    )
    monkeypatch.setattr(
        analysis_tasks,
        "get_supabase_admin",
        lambda: _FakeAdmin({
            "run_quotes": [
                # Retail of $12 against $10 measured is a 17% margin — far under
                # the 70% floor, which needs $33.33.
                {"id": "q-1", "credits": 100_000, "estimated_cost_usd": 10.0,
                 "retail_price_usd": 12.0},
            ]
        }),
    )
    monkeypatch.setattr(
        analysis_tasks, "deduct_credits", lambda org, credits: charged.append(credits)
    )

    with capture_logs() as logs:
        result = analysis_tasks.reconcile_run_cost("sim-1", "org-1")

    assert result["cost_reconciled"] is True
    assert result["margin_floor_held"] is False
    assert "margin_floor_breached" in _events(logs)


def test_a_healthily_priced_run_holds_the_floor(monkeypatch):
    monkeypatch.setattr(
        analysis_tasks,
        "get_simulation_cost",
        lambda _sim: {"total_cost_usd": 1.0, "by_stage": [_row(1.0)], "available": True},
    )
    monkeypatch.setattr(
        analysis_tasks,
        "get_supabase_admin",
        lambda: _FakeAdmin({
            "run_quotes": [
                {"id": "q-1", "credits": 10_000, "estimated_cost_usd": 1.0,
                 "retail_price_usd": 5.0},
            ]
        }),
    )
    monkeypatch.setattr(analysis_tasks, "deduct_credits", lambda org, credits: None)

    result = analysis_tasks.reconcile_run_cost("sim-1", "org-1")

    assert result["margin_floor_held"] is True
    assert result["measured_credits"] > 0


# ── The ledger must not report availability it does not have ──

def test_an_empty_ledger_is_unavailable_not_free(monkeypatch):
    monkeypatch.setattr(
        usage_ledger, "get_supabase_admin", lambda: _StubRpc(rows=[])
    )

    with capture_logs() as logs:
        measured = usage_ledger.get_simulation_cost("sim-1")

    assert measured["available"] is False
    assert measured["total_cost_usd"] is None, "unknown cost must not be reported as $0"
    assert measured["reason"] == "no_ledger_rows"
    assert "simulation_cost_ledger_empty" in _events(logs)


def test_a_populated_ledger_is_available(monkeypatch):
    monkeypatch.setattr(
        usage_ledger,
        "get_supabase_admin",
        lambda: _StubRpc(rows=[{"stage": "report", "cost_usd": 0.25}]),
    )

    measured = usage_ledger.get_simulation_cost("sim-1")

    assert measured["available"] is True
    assert measured["total_cost_usd"] == pytest.approx(0.25)


def test_a_failed_lookup_reports_no_cost_rather_than_zero(monkeypatch):
    monkeypatch.setattr(usage_ledger, "get_supabase_admin", lambda: _StubRpc(raises=True))

    measured = usage_ledger.get_simulation_cost("sim-1")

    assert measured["available"] is False
    assert measured["total_cost_usd"] is None
    assert measured["reason"] == "lookup_failed"


class _StubRpc:
    def __init__(self, rows=None, raises=False):
        self._rows = rows or []
        self._raises = raises

    def rpc(self, _name, _params):
        if self._raises:
            raise RuntimeError("rpc unavailable")
        return self

    def execute(self):
        return type("Result", (), {"data": self._rows})()


# ── The buffer must survive a failed insert ──────────────

def test_buffer_survives_a_failed_insert(monkeypatch):
    """The rows were cleared before the insert was confirmed, so one transient
    error destroyed up to a full batch of metering — and the run then reconciled
    against a total missing them."""
    admin = _FailingInsert()
    monkeypatch.setattr(usage_ledger, "get_supabase_admin", lambda: admin)

    ctx = _ctx()
    ctx.buffer.extend([_row(), _row(), _row()])

    with capture_logs() as logs:
        usage_ledger._flush_buffer(ctx)

    assert len(ctx.buffer) == 3, "a failed insert must not consume the rows"
    assert "llm_usage_flush_failed" in _events(logs)


def test_retained_rows_are_written_by_the_next_successful_flush(monkeypatch):
    failing = _FailingInsert()
    monkeypatch.setattr(usage_ledger, "get_supabase_admin", lambda: failing)

    ctx = _ctx()
    ctx.buffer.extend([_row(), _row()])
    usage_ledger._flush_buffer(ctx)

    recording = _RecordingInsert()
    monkeypatch.setattr(usage_ledger, "get_supabase_admin", lambda: recording)
    usage_ledger._flush_buffer(ctx)

    assert len(recording.inserted[0]) == 2
    assert ctx.buffer == []


def test_a_confirmed_insert_clears_only_what_it_wrote(monkeypatch):
    """Concurrent platform tasks append while a flush is in flight."""
    recording = _RecordingInsert()
    monkeypatch.setattr(usage_ledger, "get_supabase_admin", lambda: recording)

    ctx = _ctx()
    ctx.buffer.extend([_row(0.01), _row(0.02)])

    rows_snapshot = list(ctx.buffer)
    original_insert = recording.insert

    def insert_then_append(rows):
        result = original_insert(rows)
        ctx.buffer.append(_row(0.99))  # arrives mid-flush
        return result

    recording.insert = insert_then_append
    usage_ledger._flush_buffer(ctx)

    assert recording.inserted[0] == rows_snapshot
    assert len(ctx.buffer) == 1, "the row that arrived mid-flush must not be dropped"
    assert ctx.buffer[0]["cost_usd"] == 0.99


def test_a_failing_ledger_does_not_retry_on_every_single_call(monkeypatch):
    """Retained rows keep the buffer over the threshold; without a backoff every
    subsequent call would re-hammer a database that is down."""
    admin = _FailingInsert()
    monkeypatch.setattr(usage_ledger, "get_supabase_admin", lambda: admin)

    ctx = _ctx()
    ctx.buffer.extend([_row()] * usage_ledger._FLUSH_THRESHOLD)
    usage_ledger._flush_buffer(ctx)

    assert admin.attempts == 1
    assert ctx.next_flush_size > len(ctx.buffer)


def test_the_retained_buffer_is_bounded_and_says_what_it_dropped(monkeypatch):
    admin = _FailingInsert()
    monkeypatch.setattr(usage_ledger, "get_supabase_admin", lambda: admin)

    ctx = _ctx()
    ctx.buffer.extend([_row()] * (usage_ledger._MAX_BUFFERED_ROWS + 10))

    with capture_logs() as logs:
        usage_ledger._flush_buffer(ctx)

    assert len(ctx.buffer) == usage_ledger._MAX_BUFFERED_ROWS
    assert "llm_usage_buffer_overflow" in _events(logs)


def test_rows_lost_at_context_exit_are_reported(monkeypatch):
    admin = _FailingInsert()
    monkeypatch.setattr(usage_ledger, "get_supabase_admin", lambda: admin)

    with capture_logs() as logs:
        with usage_ledger.usage_context("report", simulation_id="sim-1") as ctx:
            ctx.buffer.append(_row())

    assert "llm_usage_rows_lost" in _events(logs)


def test_a_successful_context_leaves_nothing_behind(monkeypatch):
    recording = _RecordingInsert()
    monkeypatch.setattr(usage_ledger, "get_supabase_admin", lambda: recording)

    with usage_ledger.usage_context("report", simulation_id="sim-1"):
        usage_ledger.record_llm_call("claude-haiku-4-5", input_tokens=100, output_tokens=50)

    assert len(recording.inserted) == 1
    assert recording.inserted[0][0]["stage"] == "report"
    assert recording.inserted[0][0]["cost_usd"] > 0
