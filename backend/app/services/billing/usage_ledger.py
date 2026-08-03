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


@dataclass
class _UsageContext:
    stage: str
    simulation_id: str | None = None
    organization_id: str | None = None
    buffer: list[dict[str, Any]] = field(default_factory=list)


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
        _current.reset(token)


def record_llm_call(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> None:
    """Record one call. A no-op outside a usage_context.

    Never raises: a billing-ledger failure must not take down a simulation.
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
        if len(ctx.buffer) >= _FLUSH_THRESHOLD:
            _flush_buffer(ctx)
    except Exception:
        logger.exception("llm_usage_record_failed", model=model)


def flush_usage() -> None:
    """Force a flush of the active context's buffer."""
    ctx = _current.get()
    if ctx is not None:
        _flush_buffer(ctx)


def _flush_buffer(ctx: _UsageContext) -> None:
    if not ctx.buffer:
        return

    rows, ctx.buffer = ctx.buffer, []
    try:
        get_supabase_admin().table("llm_usage").insert(rows).execute()
    except Exception:
        # Losing ledger rows degrades cost reporting; it must not fail the run.
        logger.exception(
            "llm_usage_flush_failed",
            stage=ctx.stage,
            simulation_id=ctx.simulation_id,
            dropped_rows=len(rows),
        )


async def flush_usage_async() -> None:
    """Flush without blocking the event loop (the Supabase client is sync)."""
    ctx = _current.get()
    if ctx is not None and ctx.buffer:
        await asyncio.to_thread(_flush_buffer, ctx)


def get_simulation_cost(simulation_id: str) -> dict[str, Any]:
    """Measured cost of a simulation, broken down by stage.

    This is the ground truth a run quote is checked against.
    """
    admin = get_supabase_admin()
    try:
        rows = admin.rpc(
            "simulation_llm_cost", {"sim_uuid": simulation_id}
        ).execute().data or []
    except Exception:
        logger.exception("simulation_cost_lookup_failed", simulation_id=simulation_id)
        return {"total_cost_usd": 0.0, "by_stage": [], "available": False}

    total = sum(Decimal(str(r.get("cost_usd") or 0)) for r in rows)
    return {
        "total_cost_usd": float(total),
        "by_stage": rows,
        "available": True,
    }
