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


@celery_app.task(name="process_asset", bind=True, max_retries=2)
def task_process_asset(self, asset_id: str):
    """Process an uploaded media asset."""
    from app.services.ingestion.asset_processor import process_asset

    try:
        logger.info("task_process_asset_started", asset_id=asset_id)
        _run_async(process_asset(asset_id))
        logger.info("task_process_asset_complete", asset_id=asset_id)
        return {"asset_id": asset_id, "status": "ready"}
    except Exception as exc:
        logger.error("task_process_asset_failed", asset_id=asset_id, error=str(exc))
        raise self.retry(exc=exc, countdown=60)
