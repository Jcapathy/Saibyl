# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# process_asset(asset_id: UUID) -> None
# ─────────────────────────────────────────────────────────
from __future__ import annotations

from uuid import UUID

import structlog

from app.core.database import get_supabase_admin
from app.services.engine.document_processor import process_document
from app.services.ingestion.article_processor import process_article
from app.services.ingestion.spreadsheet_processor import process_spreadsheet
from app.services.ingestion.video_processor import process_video
from app.services.ingestion.vision_processor import process_image

logger = structlog.get_logger()


async def process_asset(asset_id: UUID) -> None:
    """Download raw file, dispatch to correct processor, store extracted text."""
    admin = get_supabase_admin()

    asset = admin.table("project_assets").select("*").eq(
        "id", str(asset_id)
    ).single().execute().data

    admin.table("project_assets").update(
        {"status": "processing"}
    ).eq("id", str(asset_id)).execute()

    try:
        media_type = asset["media_type"]
        storage_path = asset["storage_path"]

        # Download raw file
        file_bytes = admin.storage.from_("project-media").download(storage_path)

        result: dict

        if media_type == "document":
            # Create a documents record and use the existing processor
            doc = admin.table("documents").insert({
                "project_id": asset["project_id"],
                "organization_id": asset["organization_id"],
                "filename": asset["title"],
                "file_type": asset.get("file_extension", "txt"),
                "storage_path": storage_path,
                "file_size_bytes": asset["file_size_bytes"],
            }).execute().data[0]
            await process_document(doc["id"])
            result = {"extracted_text": "Processed via document pipeline", "metadata": {}}

        elif media_type == "image":
            result = await process_image(file_bytes, asset["title"])

        elif media_type == "video":
            result = await process_video(file_bytes, asset["title"])

        elif media_type == "news_article":
            result = await process_article(
                source_url=asset.get("source_url"),
                html_content=file_bytes.decode("utf-8", errors="replace") if file_bytes else None,
            )

        elif media_type == "spreadsheet":
            result = await process_spreadsheet(file_bytes, asset["title"])

        elif media_type == "presentation":
            # Reuse document processor for PPTX
            doc = admin.table("documents").insert({
                "project_id": asset["project_id"],
                "organization_id": asset["organization_id"],
                "filename": asset["title"],
                "file_type": "docx",
                "storage_path": storage_path,
                "file_size_bytes": asset["file_size_bytes"],
            }).execute().data[0]
            await process_document(doc["id"])
            result = {"extracted_text": "Processed via document pipeline", "metadata": {}}

        else:
            raise ValueError(f"Unsupported media type: {media_type}")

        # Store extracted text
        extracted_text = result.get("extracted_text", "")
        text_path = storage_path.rsplit(".", 1)[0] + "_extracted.txt"

        admin.storage.from_("project-media").upload(
            text_path,
            extracted_text.encode("utf-8"),
            {"content-type": "text/plain"},
        )

        # Update asset record
        admin.table("project_assets").update({
            "status": "ready",
            "processed_text_path": text_path,
            "metadata": result.get("metadata", {}),
        }).eq("id", str(asset_id)).execute()

        # Update project asset count
        admin.rpc("increment_asset_count", {"p_project_id": asset["project_id"]})

        logger.info("asset_processed", asset_id=str(asset_id), media_type=media_type)

    except Exception as e:
        admin.table("project_assets").update({
            "status": "failed",
            "error_message": str(e)[:500],
        }).eq("id", str(asset_id)).execute()
        logger.error("asset_processing_failed", asset_id=str(asset_id), error=str(e))
        raise
