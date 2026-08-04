"""The web-search fee must reach `llm_usage`, or the margin gate cannot see it.

`reconcile_run_cost` sums `llm_usage.cost_usd` and compares it against the
quoted price. The server-side web search tool bills **per search on top of
tokens**, and no token count expresses that — so a fee left off the ledger makes
`gtm_discovery` reconcile as cheaper than it is. On a 12-query discovery that is
~19% of serving cost.

That failure would be silent in the worst way: the run completes, the quote
looks honest, and `margin_floor_breached` — the single signal HANDOFF names as
grounds for reopening the closed cost model — cannot fire for the portion that
never arrived. Same shape as the margin gate passing on an empty ledger, one
level up.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.billing import usage_ledger
from app.services.billing.agent_pricing import (
    WEB_SEARCH_USD_PER_REQUEST,
    search_fee_usd,
)
from app.services.billing.model_pricing import cost_usd

MODEL = "claude-haiku-4-5-20251001"


def _buffered(rows):
    return [r for r in rows if r["stage"] == "gtm_discovery"]


@pytest.fixture
def ledger(monkeypatch):
    """A usage context whose buffer never flushes, so it can be inspected."""
    monkeypatch.setattr(usage_ledger, "_flush_buffer", lambda ctx: None)
    with usage_ledger.usage_context(
        organization_id="org-1", simulation_id=None, stage="gtm_discovery"
    ) as ctx:
        yield ctx


def test_the_fee_is_added_to_the_row_the_tokens_are_on(ledger):
    """One row, one cost: tokens plus the searches that produced them."""
    usage_ledger.record_llm_call(
        MODEL, input_tokens=19_000, output_tokens=1_200, surcharge_usd=search_fee_usd(2)
    )

    rows = _buffered(ledger.buffer)
    assert len(rows) == 1

    tokens_only = cost_usd(MODEL, input_tokens=19_000, output_tokens=1_200)
    expected = tokens_only + (WEB_SEARCH_USD_PER_REQUEST * 2)

    assert rows[0]["cost_usd"] == pytest.approx(float(expected))
    assert rows[0]["cost_usd"] > float(tokens_only), (
        "the per-search fee did not reach the ledger — reconcile_run_cost will "
        "understate this stage and the margin floor cannot see the difference"
    )


def test_a_call_with_no_searches_is_unchanged(ledger):
    """Absence of a fee is not a fee of zero applied wrongly."""
    usage_ledger.record_llm_call(MODEL, input_tokens=1_000, output_tokens=100)

    rows = _buffered(ledger.buffer)
    assert rows[0]["cost_usd"] == pytest.approx(
        float(cost_usd(MODEL, input_tokens=1_000, output_tokens=100))
    )


def test_every_other_stage_is_untouched_by_the_new_parameter(ledger):
    """The surcharge defaults to zero, so no existing caller changes cost."""
    usage_ledger.record_llm_call(MODEL, input_tokens=500, output_tokens=50)
    baseline = _buffered(ledger.buffer)[0]["cost_usd"]

    usage_ledger.record_llm_call(
        MODEL, input_tokens=500, output_tokens=50, surcharge_usd=0
    )
    assert _buffered(ledger.buffer)[1]["cost_usd"] == pytest.approx(baseline)


def test_a_negative_surcharge_is_refused_rather_than_credited(ledger):
    """A negative fee would *reduce* measured cost and lift margin on paper.

    `record_llm_call` never raises — a ledger failure must not kill a run — so
    the guard shows up as a logged failure and no row, not an exception.
    """
    usage_ledger.record_llm_call(MODEL, input_tokens=100, surcharge_usd=Decimal("-1"))

    assert _buffered(ledger.buffer) == []


def test_the_fee_scales_with_searches_not_with_calls():
    """$10 per 1,000 searches, and zero searches costs nothing."""
    assert search_fee_usd(0) == Decimal("0")
    assert search_fee_usd(1) == WEB_SEARCH_USD_PER_REQUEST
    assert search_fee_usd(12) == WEB_SEARCH_USD_PER_REQUEST * 12
    # Defensive: a negative count is a bug upstream, never a credit.
    assert search_fee_usd(-5) == Decimal("0")


def test_the_adapter_reports_its_searches_onto_the_ledger(ledger, monkeypatch):
    """End to end through the adapter's own usage hook.

    Asserting on `search_fee_usd` alone would only prove the helper works. The
    defect being guarded is the wiring: the adapter counting searches for a log
    line while the ledger never learns about them.
    """
    from app.services.gtm.search_adapter import AnthropicWebSearchAdapter

    class _Usage:
        input_tokens = 19_000
        output_tokens = 1_200
        cache_read_input_tokens = 0
        cache_creation_input_tokens = 0
        server_tool_use = type("_S", (), {"web_search_requests": 3})()

    adapter = AnthropicWebSearchAdapter.__new__(AnthropicWebSearchAdapter)
    adapter._model = MODEL
    adapter.searches_performed = 0

    adapter._record_usage(type("_R", (), {"usage": _Usage()})())

    rows = _buffered(ledger.buffer)
    assert len(rows) == 1
    assert adapter.searches_performed == 3

    tokens_only = cost_usd(MODEL, input_tokens=19_000, output_tokens=1_200)
    assert rows[0]["cost_usd"] == pytest.approx(
        float(tokens_only + WEB_SEARCH_USD_PER_REQUEST * 3)
    )
