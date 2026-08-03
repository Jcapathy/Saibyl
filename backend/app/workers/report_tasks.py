"""Report generation tasks.

Both entry points wrap generation in a `usage_context`. Without one the report's
LLM calls are not metered at all: `run_generate_report` is fired via
`asyncio.create_task` from `run_simulation` *after* the run's own usage contexts
have exited, so `record_llm_call` finds no active context and returns early.

That mattered more than it looks. The report is the most expensive main-model
stage in a run — roughly a fifth of a standard run's cost — so an unmetered
report made `simulation_llm_cost` under-report every run by that much, and
`reconcile_run_cost` compared each quote against a measured figure with its
largest main-model line missing. A margin breach could have passed the gate.
"""
import structlog

logger = structlog.get_logger()


def _org_for(simulation_id: str) -> str | None:
    """The owning org, so report usage is attributed to the right account."""
    from app.core.database import get_supabase_admin

    try:
        row = (
            get_supabase_admin()
            .table("simulations")
            .select("organization_id")
            .eq("id", simulation_id)
            .single()
            .execute()
        ).data
        return (row or {}).get("organization_id")
    except Exception:
        # Metering must never block a report. An unattributed row still records
        # the spend against the simulation.
        logger.warning("report_org_lookup_failed", simulation_id=simulation_id)
        return None


async def run_generate_report(
    simulation_id: str,
    variant: str = "a",
    evidence_depth: str = "deep",
    max_sections: int | None = None,
):
    """Generate intelligence report from simulation results."""
    from app.services.billing.usage_ledger import usage_context
    from app.services.intelligence.report_agent import ReACTConfig, generate_report

    logger.info("task_generate_report_started", simulation_id=simulation_id, variant=variant)
    config = ReACTConfig(evidence_depth=evidence_depth, section_count=max_sections)

    with usage_context(
        "report",
        simulation_id=simulation_id,
        organization_id=_org_for(simulation_id),
    ):
        result = await generate_report(simulation_id, config)

    logger.info("task_generate_report_complete", report_id=result["id"])
    return {"report_id": result["id"], "status": result["status"]}


async def run_generate_ab_report(simulation_id: str):
    """Generate A/B comparison report."""
    from app.services.billing.usage_ledger import usage_context
    from app.services.intelligence.report_agent import (
        ReACTConfig,
        generate_ab_comparison_report,
    )

    logger.info("task_generate_ab_report_started", simulation_id=simulation_id)
    config = ReACTConfig(evidence_depth="deep", ab_comparison=True)

    with usage_context(
        "report",
        simulation_id=simulation_id,
        organization_id=_org_for(simulation_id),
    ):
        result = await generate_ab_comparison_report(simulation_id, config)

    logger.info("task_generate_ab_report_complete", report_id=result["id"])
    return {"report_id": result["id"], "status": result["status"]}
