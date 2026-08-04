from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.core.auth import get_current_org
from app.core.database import get_supabase_admin
from app.workers.simulation_tasks import run_process_document

log = structlog.get_logger()


async def _safe_task(coro, name: str):
    try:
        await coro
    except Exception:
        log.exception("background_task_failed", task=name)

router = APIRouter(tags=["documents"])


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/upload")
async def upload_document(
    project_id: str = Query(...),
    material_kind: Literal["own", "competitor", "market"] = Query("own"),
    file: UploadFile = File(...),
    auth: dict = Depends(get_current_org),
):
    """Upload a document, store in Supabase Storage, and trigger processing.

    `material_kind` is the adversarial cohort's grounding, not a tag. A
    competitor may be named in a simulation only from a document uploaded here
    as `competitor` — PRD §4 permits incumbent-aligned agents grounded in
    material the user uploaded and forbids them grounded in model memory, and
    that distinction is unenforceable unless it is recorded at upload.
    """
    allowed_extensions = {"pdf", "txt", "doc", "docx", "csv", "json", "md", "html", "pptx", "xlsx"}
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if file.filename else ""
    if ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail="File type not allowed")

    log.info("upload_document", project_id=project_id, filename=file.filename, org_id=auth["org_id"])
    admin = get_supabase_admin()

    # Verify project belongs to org
    project = (
        admin.table("projects")
        .select("id")
        .eq("id", project_id)
        .eq("organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not project.data:
        raise HTTPException(status_code=404, detail="Project not found")

    # Upload file to Supabase Storage
    file_bytes = await file.read()
    import re as _re
    import uuid as _uuid
    safe_name = _re.sub(r"[^a-zA-Z0-9._-]", "_", file.filename or "document")[:100]
    doc_uuid = str(_uuid.uuid4())[:8]
    storage_path = f"{auth['org_id']}/{project_id}/{doc_uuid}_{safe_name}"
    admin.storage.from_("project-media").upload(storage_path, file_bytes)

    # Derive file_type from extension (documents table requires file_type NOT NULL)
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if file.filename else "txt"

    # Create document record
    doc = (
        admin.table("documents")
        .insert({
            "project_id": project_id,
            "organization_id": auth["org_id"],
            "filename": file.filename,
            "file_type": ext,
            "storage_path": storage_path,
            "file_size_bytes": len(file_bytes),
            "material_kind": material_kind,
            "processing_status": "pending",
            "created_at": datetime.now(UTC).isoformat(),
        })
        .execute()
    ).data[0]

    # Increment project asset count.
    #
    # `projects.asset_count` is a denormalised counter, and the upload has
    # already succeeded by this point: the object is in storage and the row is
    # in `documents`. Letting an RPC failure become a 500 would tell the client
    # its upload failed and invite a re-upload, producing a duplicate document
    # for a wrong badge count. Logged at exception level with the ids needed to
    # reconcile — loud and recoverable, not swallowed.
    try:
        admin.rpc("increment_asset_count", {"p_project_id": project_id}).execute()
    except Exception:
        log.exception(
            "asset_count_increment_failed",
            project_id=project_id,
            document_id=doc["id"],
            note="document row exists; projects.asset_count is now under-counted",
        )

    # Trigger async processing
    asyncio.create_task(_safe_task(run_process_document(doc["id"]), "process_document"))
    log.info("document_processing_queued", document_id=doc["id"])

    return doc


@router.get("")
async def list_documents(project_id: str = Query(...), auth: dict = Depends(get_current_org)):
    """List documents for a project."""
    log.info("list_documents", project_id=project_id, org_id=auth["org_id"])
    admin = get_supabase_admin()
    result = (
        admin.table("documents")
        .select("*")
        .eq("project_id", project_id)
        .eq("organization_id", auth["org_id"])
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


@router.get("/{id}")
async def get_document(id: str, auth: dict = Depends(get_current_org)):
    """Get document details."""
    log.info("get_document", document_id=id)
    admin = get_supabase_admin()
    result = (
        admin.table("documents")
        .select("*")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found")
    return result.data


@router.delete("/{id}")
async def delete_document(id: str, auth: dict = Depends(get_current_org)):
    """Delete a document and its storage file."""
    log.info("delete_document", document_id=id)
    admin = get_supabase_admin()

    # Fetch document to get storage path and project
    doc = (
        admin.table("documents")
        .select("id, storage_path, project_id")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not doc.data:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete from storage
    admin.storage.from_("project-media").remove([doc.data["storage_path"]])

    # Delete database record
    admin.table("documents").delete().eq("id", id).execute()

    # Decrement project asset count. Same reasoning as the upload path in
    # reverse: the storage object and the row are already gone, so a 500 here
    # would report a failed delete for a delete that happened, and the client's
    # retry would 404.
    try:
        admin.rpc(
            "decrement_asset_count", {"p_project_id": doc.data["project_id"]}
        ).execute()
    except Exception:
        log.exception(
            "asset_count_decrement_failed",
            project_id=doc.data["project_id"],
            document_id=id,
            note="document row deleted; projects.asset_count is now over-counted",
        )

    return {"detail": "Document deleted"}
