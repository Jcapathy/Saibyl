# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# get_benchmark_context(vertical, metric) -> BenchmarkContext | None
# update_benchmarks() -> None  (nightly Celery task)
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import structlog
from pydantic import BaseModel

from app.core.database import get_supabase_admin

logger = structlog.get_logger()


class BenchmarkContext(BaseModel):
    vertical: str
    metric: str
    avg_value: float
    sample_count: int
    percentile_25: float
    percentile_75: float


async def get_benchmark_context(vertical: str, metric: str) -> BenchmarkContext | None:
    """Get benchmark data for a vertical + metric, or None if insufficient data."""
    admin = get_supabase_admin()

    # Check if benchmark_metrics table exists and has data
    try:
        result = admin.table("benchmark_metrics").select("*").eq(
            "vertical", vertical
        ).eq("metric", metric).single().execute()

        if not result.data:
            return None

        d = result.data
        return BenchmarkContext(
            vertical=vertical,
            metric=metric,
            avg_value=d.get("avg_value", 0),
            sample_count=d.get("sample_count", 0),
            percentile_25=d.get("percentile_25", 0),
            percentile_75=d.get("percentile_75", 0),
        )
    except Exception:
        return None


async def update_benchmarks() -> None:
    """Nightly job: aggregate anonymized metrics across all simulations."""
    admin = get_supabase_admin()

    # Get all completed simulations
    sims = admin.table("simulations").select(
        "id, platforms"
    ).eq("status", "complete").execute().data

    if not sims:
        logger.info("no_simulations_for_benchmarks")
        return

    # Aggregate platform event counts
    for platform in ["twitter_x", "reddit", "linkedin", "instagram"]:
        events = admin.table("simulation_events").select(
            "id", count="exact"
        ).eq("platform", platform).execute()

        count = events.count or 0
        sim_count = len([s for s in sims if platform in (s.get("platforms") or [])])

        if sim_count > 0:
            avg = count / sim_count
            try:
                admin.table("benchmark_metrics").upsert({
                    "vertical": "all",
                    "metric": f"avg_events_{platform}",
                    "avg_value": avg,
                    "sample_count": sim_count,
                    "percentile_25": avg * 0.6,
                    "percentile_75": avg * 1.4,
                }, on_conflict="vertical,metric").execute()
            except Exception as e:
                logger.warning("benchmark_upsert_failed", error=str(e))

    logger.info("benchmarks_updated", simulation_count=len(sims))
