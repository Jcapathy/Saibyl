# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# run_ingest_document(document_id: str) -> dict
# ─────────────────────────────────────────────────────────
"""Background entry point for the one ingest path.

Replaces `run_process_asset`, which drove
`services/ingestion/asset_processor.py` against the `project_assets` table.
Nothing that table held was ever read by ICP synthesis, so every image, video,
spreadsheet and article it processed was invisible to the product. See
`services/ingestion/pipeline.py` for the full account.
"""
from __future__ import annotations

import structlog

logger = structlog.get_logger()


async def run_ingest_document(document_id: str) -> dict:
    """Extract, persist and classify one uploaded document."""
    from app.services.ingestion.pipeline import ingest_document

    logger.info("task_ingest_document_started", document_id=document_id)
    result = await ingest_document(document_id)
    logger.info(
        "task_ingest_document_complete",
        document_id=document_id,
        media_type=result.media_type,
        chars=result.chars,
    )
    return {
        "document_id": result.document_id,
        "media_type": result.media_type,
        "chars": result.chars,
        "status": "complete",
    }
