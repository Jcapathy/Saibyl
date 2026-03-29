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


@celery_app.task(name="run_market_prediction", bind=True, max_retries=1)
def task_run_market_prediction(self, market_id: str, org_id: str):
    """Run a prediction market simulation."""
    from app.services.markets.prediction_runner import run_prediction

    try:
        logger.info("task_market_prediction_started", market_id=market_id)
        result = _run_async(run_prediction(market_id, org_id))
        logger.info("task_market_prediction_complete", market_id=market_id, prediction_id=result["id"])
        return {"prediction_id": result["id"], "status": "complete"}
    except Exception as exc:
        logger.error("task_market_prediction_failed", market_id=market_id, error=str(exc))
        raise self.retry(exc=exc, countdown=120)
