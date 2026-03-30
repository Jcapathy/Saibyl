import structlog

logger = structlog.get_logger()


async def run_market_prediction(market_id: str, org_id: str):
    """Run a prediction market simulation."""
    from app.services.markets.prediction_runner import run_prediction

    logger.info("task_market_prediction_started", market_id=market_id)
    result = await run_prediction(market_id, org_id)
    logger.info("task_market_prediction_complete", market_id=market_id, prediction_id=result["id"])
    return {"prediction_id": result["id"], "status": "complete"}
