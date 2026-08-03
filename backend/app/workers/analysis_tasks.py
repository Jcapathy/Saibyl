"""Post-run measurement, analysis, and cost reconciliation.

Runs as one task because the three steps are strictly ordered and share a
failure story: measure the events, build the artifact from them, then check what
the run actually cost against what it was quoted.

A failure here does not fail the run. The events are real and already stored, so
the correct behaviour is to record that the artifact is missing and why —
`simulation_analysis.build_status` — rather than throw away a completed
simulation. What must never happen is a run reported as complete with a
*partial* artifact presented as a whole one, which is why the artifact carries
its own coverage figure.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog

from app.core.database import get_supabase_admin
from app.services.billing.agent_pricing import MIN_MARGIN_PCT, credits_for, deduct_credits
from app.services.billing.usage_ledger import get_simulation_cost
from app.services.intelligence.analysis_builder import build_simulation_analysis
from app.services.intelligence.event_measurement import measure_simulation_events

logger = structlog.get_logger()


async def run_analysis(simulation_id: str, organization_id: str) -> dict[str, Any]:
    """Measure a finished run's events and build its analysis artifact."""
    admin = get_supabase_admin()

    try:
        measurement = await measure_simulation_events(simulation_id, organization_id)
        analysis = await build_simulation_analysis(simulation_id, organization_id)
    except Exception as exc:
        logger.exception("analysis_failed", simulation_id=simulation_id)
        _record_failure(simulation_id, organization_id, exc)
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}

    reconciliation = reconcile_run_cost(simulation_id, organization_id)

    summary = {
        "available": True,
        "coverage_pct": analysis.quality.coverage_pct,
        "events_measured": measurement.events_measured,
        "events_failed": measurement.events_failed,
        "objections": len(analysis.objections),
        "flashpoints": len(analysis.flashpoints),
        "confidence": analysis.quality.confidence,
        **reconciliation,
    }

    admin.table("simulations").update({
        "retail_cost_usd": reconciliation.get("measured_cost_usd", 0.0),
    }).eq("id", simulation_id).execute()

    return summary


def _record_failure(simulation_id: str, organization_id: str, exc: BaseException) -> None:
    """Leave a row saying the artifact is missing and why.

    Without this the frontend cannot distinguish "not analysed yet" from
    "analysis failed", and would poll forever on a run that will never produce
    an artifact.
    """
    try:
        get_supabase_admin().table("simulation_analysis").upsert(
            {
                "simulation_id": simulation_id,
                "organization_id": organization_id,
                "schema_version": 0,
                "artifact": {},
                "build_status": "failed",
                "error_message": f"{type(exc).__name__}: {exc}",
                "updated_at": datetime.now(UTC).isoformat(),
            },
            on_conflict="simulation_id",
        ).execute()
    except Exception:
        logger.exception("analysis_failure_record_failed", simulation_id=simulation_id)


def reconcile_run_cost(simulation_id: str, organization_id: str) -> dict[str, Any]:
    """Compare the quote against measured spend, and charge any shortfall.

    This is the Phase 1 cost-integrity gate: quoted price must be at least
    measured cost times the margin floor. The stage token profiles behind every
    quote are estimates until the ledger has real data, so this check is what
    surfaces a bad profile on the first run rather than in a month's P&L.

    A shortfall is charged rather than absorbed, because absorbing it silently
    is how a pricing bug becomes a business one. It is logged loudly either way.
    """
    measured = get_simulation_cost(simulation_id)
    if not measured.get("available"):
        return {"cost_reconciled": False}

    measured_usd = float(measured.get("total_cost_usd") or 0.0)
    admin = get_supabase_admin()

    quotes = (
        admin.table("run_quotes")
        .select("id, credits, estimated_cost_usd, retail_price_usd")
        .eq("simulation_id", simulation_id)
        .limit(1)
        .execute()
    ).data or []

    measured_credits = credits_for(measured_usd)
    result: dict[str, Any] = {
        "cost_reconciled": True,
        "measured_cost_usd": round(measured_usd, 6),
        "measured_credits": measured_credits,
        "by_stage": measured.get("by_stage", []),
    }

    if not quotes:
        # An unquoted run — a legacy simulation, or one started before the
        # configurator shipped. Charge measured cost so it is not free.
        deduct_credits(UUID(organization_id), measured_credits)
        result["credits_charged"] = measured_credits
        result["quoted"] = False
        logger.warning(
            "run_had_no_quote",
            simulation_id=simulation_id,
            charged_credits=measured_credits,
        )
        return result

    quote = quotes[0]
    quoted_credits = int(quote["credits"])
    retail = float(quote["retail_price_usd"])
    shortfall = max(0, measured_credits - quoted_credits)

    if shortfall:
        deduct_credits(UUID(organization_id), shortfall)

    # Margin held on what was actually charged, against what it actually cost.
    floor_price = measured_usd / (1 - float(MIN_MARGIN_PCT) / 100) if measured_usd else 0.0
    margin_held = retail >= floor_price

    result.update({
        "quoted": True,
        "quote_id": quote["id"],
        "quoted_credits": quoted_credits,
        "credits_charged": quoted_credits + shortfall,
        "shortfall_credits": shortfall,
        "margin_floor_held": margin_held,
    })

    if not margin_held:
        logger.error(
            "margin_floor_breached",
            simulation_id=simulation_id,
            measured_cost_usd=round(measured_usd, 6),
            quoted_retail_usd=retail,
            required_retail_usd=round(floor_price, 6),
            note="recalibrate the stage token profiles in agent_pricing.py",
        )
    elif shortfall:
        logger.warning(
            "quote_underestimated_run",
            simulation_id=simulation_id,
            quoted_credits=quoted_credits,
            measured_credits=measured_credits,
        )

    return result
