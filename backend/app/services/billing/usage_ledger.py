# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# usage_context(stage, simulation_id=None, organization_id=None)  [context manager]
# record_llm_call(model, input_tokens, output_tokens, ...) -> None
# flush_usage() -> None
# get_simulation_cost(simulation_id) -> dict[str, Any]
# ─────────────────────────────────────────────────────────
"""Records what each LLM call actually cost, per pipeline stage.

Attribution uses a contextvar rather than a parameter threaded through every
call site: agent actions are issued deep inside platform adapters that have no
reason to know about billing, and passing a stage through them would couple
the two for no benefit. Because the simulation engine is asyncio-based,
contextvars follow the task correctly across concurrent platform runs.

Writes are buffered and flushed in batches — a 100-agent, 5-round run makes
500 calls, and 500 individual inserts would dominate the run's wall clock.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import structlog

from app.core.database import get_supabase_admin
from app.services.billing.model_pricing import cost_usd

logger = structlog.get_logger()

# Rows are flushed once the buffer reaches this size, and again at the end of
# the enclosing usage_context.
_FLUSH_THRESHOLD = 50

# Rows survive a failed insert, so the buffer has to be bounded or a database
# outage turns a long run into unbounded memory growth. At the cap the oldest
# rows are dropped — loudly, because dropped rows understate what a run cost.
_MAX_BUFFERED_ROWS = 1_000


@dataclass
class _UsageContext:
    stage: str
    simulation_id: str | None = None
    organization_id: str | None = None
    buffer: list[dict[str, Any]] = field(default_factory=list)
    # Raised past the threshold after a failed insert so that every subsequent
    # call does not re-hammer a database that is currently down; reset to the
    # threshold on the first confirmed insert.
    next_flush_size: int = _FLUSH_THRESHOLD


_current: ContextVar[_UsageContext | None] = ContextVar("llm_usage_context", default=None)


@contextmanager
def usage_context(
    stage: str,
    simulation_id: str | None = None,
    organization_id: str | None = None,
):
    """Attribute every LLM call made inside this block to `stage`.

    Nesting is supported: an inner context replaces the outer one for its
    duration and restores it on exit.
    """
    ctx = _UsageContext(
        stage=stage,
        simulation_id=simulation_id,
        organization_id=organization_id,
    )
    token = _current.set(ctx)
    try:
        yield ctx
    finally:
        _flush_buffer(ctx)
        if ctx.buffer:
            # Last chance: the context is about to go out of scope, so anything
            # still buffered is genuinely lost rather than merely retried.
            logger.error(
                "llm_usage_rows_lost",
                stage=ctx.stage,
                simulation_id=ctx.simulation_id,
                lost_rows=len(ctx.buffer),
                note="cost for this stage is understated by these rows",
            )
        _current.reset(token)


def record_llm_call(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    surcharge_usd: Decimal | float = 0,
) -> None:
    """Record one call. A no-op outside a usage_context.

    Never raises: a billing-ledger failure must not take down a simulation.

    `surcharge_usd` is real serving cost this call incurred that **no token
    count can express** — a per-request fee charged alongside the tokens. The
    server-side web search tool is the first: it bills per search on top of the
    tokens its results occupy.

    It exists because `reconcile_run_cost` compares the quoted price against
    the sum of `llm_usage.cost_usd`, so a cost that never reaches this ledger
    is invisible to the margin floor. A stage whose spend is partly off-ledger
    reconciles as cheaper than it is, and `margin_floor_breached` — the single
    signal that reopens the cost model — cannot fire for the portion that is
    missing. Recording it here keeps one definition of what a run cost.
    """
    ctx = _current.get()
    if ctx is None:
        return

    try:
        cost = cost_usd(
            model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
        )
        # Decimal throughout: the fee is a price, and float addition against a
        # Decimal cost is how a rounding difference gets into a margin gate.
        surcharge = Decimal(str(surcharge_usd))
        if surcharge < 0:
            raise ValueError(f"surcharge_usd must not be negative, got {surcharge}")
        cost += surcharge
        ctx.buffer.append({
            "organization_id": ctx.organization_id,
            "simulation_id": ctx.simulation_id,
            "stage": ctx.stage,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": cache_read_tokens,
            "cache_write_tokens": cache_write_tokens,
            "cost_usd": float(cost),
            "call_count": 1,
        })
        if len(ctx.buffer) >= ctx.next_flush_size:
            _flush_buffer(ctx)
    except Exception:
        logger.exception("llm_usage_record_failed", model=model)


def flush_usage() -> None:
    """Force a flush of the active context's buffer."""
    ctx = _current.get()
    if ctx is not None:
        _flush_buffer(ctx)


def _flush_buffer(ctx: _UsageContext) -> None:
    """Insert the buffered rows, and clear them only once the insert lands.

    The buffer is emptied *after* a confirmed insert, never before. Clearing
    first meant one transient error destroyed up to a full batch of metering
    rows, and the run then reconciled against a cost that was missing them —
    which reads as a cheap run, not as a broken ledger.
    """
    if not ctx.buffer:
        return

    # A snapshot rather than a swap: concurrent platform tasks may append while
    # the (synchronous) insert is in flight under `flush_usage_async`, and those
    # later rows must not be consumed by this flush's success or failure.
    rows = list(ctx.buffer)
    try:
        get_supabase_admin().table("llm_usage").insert(rows).execute()
    except Exception:
        # Retained, not dropped. A failing ledger must not fail the run either,
        # so this stays non-fatal — but it is now recoverable on the next flush.
        logger.exception(
            "llm_usage_flush_failed",
            stage=ctx.stage,
            simulation_id=ctx.simulation_id,
            retained_rows=len(rows),
        )
        ctx.next_flush_size = len(ctx.buffer) + _FLUSH_THRESHOLD
        _trim_buffer(ctx)
        return

    del ctx.buffer[: len(rows)]
    ctx.next_flush_size = _FLUSH_THRESHOLD


def _trim_buffer(ctx: _UsageContext) -> None:
    """Bound the retained buffer, reporting anything it has to discard."""
    overflow = len(ctx.buffer) - _MAX_BUFFERED_ROWS
    if overflow <= 0:
        return

    del ctx.buffer[:overflow]
    logger.error(
        "llm_usage_buffer_overflow",
        stage=ctx.stage,
        simulation_id=ctx.simulation_id,
        dropped_rows=overflow,
        note="ledger has been unwritable long enough to lose rows; cost is understated",
    )


async def flush_usage_async() -> None:
    """Flush without blocking the event loop (the Supabase client is sync)."""
    ctx = _current.get()
    if ctx is not None and ctx.buffer:
        await asyncio.to_thread(_flush_buffer, ctx)


def get_simulation_cost(simulation_id: str) -> dict[str, Any]:
    """Measured cost of a simulation, broken down by stage.

    This is the ground truth a run quote is checked against, so "no rows" must
    never be answered with a number. An unmetered run and a $0 run are the same
    figure and opposite facts: `available=False` plus `total_cost_usd=None` is
    what keeps the caller from charging nothing and calling it reconciled.
    """
    admin = get_supabase_admin()
    try:
        rows = admin.rpc(
            "simulation_llm_cost", {"sim_uuid": simulation_id}
        ).execute().data or []
    except Exception:
        logger.exception("simulation_cost_lookup_failed", simulation_id=simulation_id)
        return {
            "total_cost_usd": None,
            "by_stage": [],
            "available": False,
            "reason": "lookup_failed",
        }

    if not rows:
        logger.error(
            "simulation_cost_ledger_empty",
            simulation_id=simulation_id,
            note="no llm_usage rows for a run that should have spent; cost is unknown, not zero",
        )
        return {
            "total_cost_usd": None,
            "by_stage": [],
            "available": False,
            "reason": "no_ledger_rows",
        }

    total = sum(Decimal(str(r.get("cost_usd") or 0)) for r in rows)
    return {
        "total_cost_usd": float(total),
        "by_stage": rows,
        "available": True,
    }
