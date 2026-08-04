"""`/api/uploads` — the media upload path, now backed by `documents`.

This router used to be one half of a second, parallel upload system: it wrote to
`project_assets`, dispatched `ingestion/asset_processor.py`, and nothing that
table held was ever read by ICP synthesis. A client who uploaded a deck as
images, a customer spreadsheet, a CRM export, a demo video or a linked article
had every one of those files processed and none of them reach the audience their
simulation ran against. V1_AUDIT item 39; the full account is in
`services/ingestion/pipeline.py`.

The route is kept — deleting a public path breaks whatever integration is
calling it — but it now stores into `documents` through exactly the same
function `/api/documents/upload` uses. `project_assets` has no remaining reader
in `backend/app`; a migration should backfill it into `documents` and drop it.

`media_type` stays in the signature because callers send it. It is validated
against the extension rather than trusted: the media type decides which
processor reads the bytes, and a caller who mislabels a `.csv` as an `image`
would otherwise send it to the vision model.
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from app.api.documents import delete_upload, store_upload
from app.core.auth import get_current_org
from app.core.database import get_supabase_admin
from app.services.ingestion.media_types import extension_of, media_type_for_extension

log = structlog.get_logger()

router = APIRouter(tags=["uploads"])


class UploadResponse(BaseModel):
    # Named `asset_id` for the callers that already parse this shape. It is a
    # `documents.id`.
    asset_id: str
    document_id: str
    media_type: str
    status: str
    message: str


@router.post("", response_model=UploadResponse)
async def upload_asset(
    project_id: str = Query(...),
    media_type: str | None = Query(None),
    material_kind: str = Query("own"),
    title: str | None = Query(None),
    source_url: str | None = Query(None),
    file: UploadFile = File(...),
    auth: dict = Depends(get_current_org),
):
    """Upload a media asset to a project."""
    if material_kind not in ("own", "competitor", "market"):
        raise HTTPException(status_code=400, detail=f"Invalid material_kind: {material_kind}")

    resolved = media_type_for_extension(extension_of(file.filename))
    if media_type and resolved and media_type != resolved:
        # Loud, and the extension wins. The declared type used to be the only
        # input to the dispatch, so a mislabelled file was routed to a processor
        # that could not read it and the failure was stored as extracted text.
        log.warning(
            "upload_media_type_mismatch",
            filename=file.filename,
            declared=media_type,
            resolved=resolved,
            detail="dispatching on the extension; the declared media_type is ignored",
        )

    doc = await store_upload(
        project_id=project_id,
        org_id=auth["org_id"],
        file=file,
        material_kind=material_kind,
        source_url=source_url,
        title=title,
    )
    return UploadResponse(
        asset_id=doc["id"],
        document_id=doc["id"],
        media_type=doc["media_type"],
        status="processing",
        message=f"Uploaded and queued for extraction ({doc['file_size_bytes'] / 1024:.0f} KB)",
    )


@router.get("")
async def list_assets(project_id: str = Query(...), auth: dict = Depends(get_current_org)):
    """List all uploads for a project."""
    admin = get_supabase_admin()
    return (
        admin.table("documents")
        .select("*")
        .eq("project_id", project_id)
        .eq("organization_id", auth["org_id"])
        .order("created_at", desc=True)
        .execute()
    ).data


@router.get("/{asset_id}")
async def get_asset(asset_id: str, auth: dict = Depends(get_current_org)):
    """Get upload details."""
    admin = get_supabase_admin()
    result = (
        admin.table("documents")
        .select("*")
        .eq("id", asset_id)
        .eq("organization_id", auth["org_id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Asset not found")
    return result.data[0]


@router.delete("/{asset_id}")
async def delete_asset(asset_id: str, auth: dict = Depends(get_current_org)):
    """Delete an upload and reclaim storage."""
    return delete_upload(asset_id, auth["org_id"])
