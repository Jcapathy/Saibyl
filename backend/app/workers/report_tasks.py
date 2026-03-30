import structlog

logger = structlog.get_logger()


async def run_generate_report(simulation_id: str, variant: str = "a"):
    """Generate intelligence report from simulation results."""
    from app.services.intelligence.report_agent import ReACTConfig, generate_report

    logger.info("task_generate_report_started", simulation_id=simulation_id, variant=variant)
    config = ReACTConfig(evidence_depth="standard")
    result = await generate_report(simulation_id, config)
    logger.info("task_generate_report_complete", report_id=result["id"])
    return {"report_id": result["id"], "status": result["status"]}


async def run_generate_ab_report(simulation_id: str):
    """Generate A/B comparison report."""
    from app.services.intelligence.report_agent import (
        ReACTConfig,
        generate_ab_comparison_report,
    )

    logger.info("task_generate_ab_report_started", simulation_id=simulation_id)
    config = ReACTConfig(evidence_depth="standard", ab_comparison=True)
    result = await generate_ab_comparison_report(simulation_id, config)
    logger.info("task_generate_ab_report_complete", report_id=result["id"])
    return {"report_id": result["id"], "status": result["status"]}
