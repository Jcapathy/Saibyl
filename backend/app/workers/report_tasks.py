import asyncio

import structlog

from app.workers.celery_app import celery_app

logger = structlog.get_logger()


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="generate_report")
def task_generate_report(simulation_id: str, variant: str = "a"):
    """Generate intelligence report from simulation results."""
    from app.services.intelligence.report_agent import ReACTConfig, generate_report

    logger.info("task_generate_report_started", simulation_id=simulation_id, variant=variant)
    config = ReACTConfig(evidence_depth="standard")
    result = _run_async(generate_report(simulation_id, config))
    logger.info("task_generate_report_complete", report_id=result["id"])
    return {"report_id": result["id"], "status": result["status"]}


@celery_app.task(name="generate_ab_report")
def task_generate_ab_report(simulation_id: str):
    """Generate A/B comparison report."""
    from app.services.intelligence.report_agent import (
        ReACTConfig,
        generate_ab_comparison_report,
    )

    logger.info("task_generate_ab_report_started", simulation_id=simulation_id)
    config = ReACTConfig(evidence_depth="standard", ab_comparison=True)
    result = _run_async(generate_ab_comparison_report(simulation_id, config))
    logger.info("task_generate_ab_report_complete", report_id=result["id"])
    return {"report_id": result["id"], "status": result["status"]}
