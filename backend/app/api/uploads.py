from __future__ import annotations

import mimetypes
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.auth import get_current_org
from app.core.database import get_supabase_admin
from app.services.billing.storage_billing import check_storage_quota, update_org_storage_usage

router = APIRouter(tags=["uploads"])

ALLOWED_EXTENSIONS = {
    "document": {"pdf", "docx", "txt", "md"},
    "image": {"jpg", "jpeg", "png", "gif", "webp"},
    "video": {"mp4", "mov", "webm", "avi"},
    "spreadsheet": {"xlsx", "csv", "xls"},
    "presentation": {"pptx"},
}

MAX_FILE_SIZES = {
    "document": 50 * 1024 * 1024,
    "image": 25 * 1024 * 1024,
    "video": 500 * 1024 * 1024,
    "spreadsheet": 20 * 1024 * 1024,
    "presentation": 50 * 1024 * 1024,
    "news_article": 5 * 1024 * 1024,
}


class UploadResponse(BaseModel):
    asset_id: str
    status: str
    message: str


@router.post("", response_model=UploadResponse)
async def upload_asset(
    project_id: str,
    media_type: str,
    file: UploadFile = File(...),
    title: str | None = None,
    source_url: str | None = None,
    auth: dict = Depends(get_current_org),
):
    """Upload a media asset to a project."""
    org_id = auth["org_id"]
    admin = get_supabase_admin()

    # Validate media type
    if media_type not in ALLOWED_EXTENSIONS and media_type != "news_article":
        raise HTTPException(400, f"Invalid media_type: {media_type}")

    # Validate file extension
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if file.filename else ""
    if media_type != "news_article":
        valid_exts = ALLOWED_EXTENSIONS.get(media_type, set())
        if ext not in valid_exts:
            raise HTTPException(400, "File type not allowed")

    # Read file
    file_bytes = await file.read()
    file_size = len(file_bytes)

    # Validate file size
    max_size = MAX_FILE_SIZES.get(media_type, 50 * 1024 * 1024)
    if file_size > max_size:
        raise HTTPException(413, f"File too large. Max {max_size / 1024 / 1024:.0f} MB for {media_type}")

    # Check storage quota
    quota = check_storage_quota(org_id, file_size)
    if not quota.allowed:
        raise HTTPException(402, quota.message)

    # Generate storage path
    asset_id = str(uuid.uuid4())
    storage_path = f"uploads/{org_id}/{project_id}/{asset_id}.{ext}"

    # Upload to Supabase Storage
    admin.storage.from_("project-media").upload(
        storage_path,
        file_bytes,
        {"content-type": mimetypes.types_map.get(f".{ext}", "application/octet-stream")},
    )

    # Create project_assets record
    asset_title = title or file.filename or f"Untitled {media_type}"
    admin.table("project_assets").insert({
        "id": asset_id,
        "organization_id": org_id,
        "project_id": project_id,
        "title": asset_title,
        "media_type": media_type,
        "file_extension": ext,
        "storage_path": storage_path,
        "source_url": source_url,
        "file_size_bytes": file_size,
        "status": "uploaded",
    }).execute()

    # Update org storage usage
    update_org_storage_usage(org_id, file_size)

    # Dispatch processing task
    import asyncio
    from app.workers.asset_tasks import run_process_asset

    async def _safe_task(coro, name: str):
        try:
            await coro
        except Exception:
            import structlog
            structlog.get_logger().exception("background_task_failed", task=name)

    asyncio.create_task(_safe_task(run_process_asset(asset_id), "process_asset"))

    return UploadResponse(
        asset_id=asset_id,
        status="processing",
        message=f"Asset uploaded and queued for processing ({file_size / 1024:.0f} KB)",
    )


@router.get("")
async def list_assets(project_id: str, auth: dict = Depends(get_current_org)):
    """List all assets for a project."""
    admin = get_supabase_admin()
    result = admin.table("project_assets").select("*").eq(
        "project_id", project_id
    ).eq("organization_id", auth["org_id"]).order("created_at", desc=True).execute()
    return result.data


@router.get("/{asset_id}")
async def get_asset(asset_id: str, auth: dict = Depends(get_current_org)):
    """Get asset details."""
    admin = get_supabase_admin()
    result = admin.table("project_assets").select("*").eq(
        "id", asset_id
    ).eq("organization_id", auth["org_id"]).single().execute()
    if not result.data:
        raise HTTPException(404, "Asset not found")
    return result.data


@router.delete("/{asset_id}")
async def delete_asset(asset_id: str, auth: dict = Depends(get_current_org)):
    """Delete an asset and reclaim storage."""
    admin = get_supabase_admin()
    asset = admin.table("project_assets").select("*").eq(
        "id", asset_id
    ).eq("organization_id", auth["org_id"]).single().execute().data

    if not asset:
        raise HTTPException(404, "Asset not found")

    # Delete from storage
    try:
        admin.storage.from_("project-media").remove([asset["storage_path"]])
        if asset.get("processed_text_path"):
            admin.storage.from_("project-media").remove([asset["processed_text_path"]])
    except Exception:
        pass

    # Delete record
    admin.table("project_assets").delete().eq("id", asset_id).execute()

    # Update storage usage
    update_org_storage_usage(auth["org_id"], -asset["file_size_bytes"])

    return {"message": "Asset deleted", "storage_reclaimed_bytes": asset["file_size_bytes"]}
