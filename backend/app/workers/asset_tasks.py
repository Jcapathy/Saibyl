import structlog

logger = structlog.get_logger()


async def run_process_asset(asset_id: str):
    """Process an uploaded media asset."""
    from app.services.ingestion.asset_processor import process_asset

    logger.info("task_process_asset_started", asset_id=asset_id)
    await process_asset(asset_id)
    logger.info("task_process_asset_complete", asset_id=asset_id)
    return {"asset_id": asset_id, "status": "ready"}
