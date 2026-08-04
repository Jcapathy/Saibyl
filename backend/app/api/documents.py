"""The one upload surface.

Every kind of material a client sends — PRD, deck, landing page, slide images,
a customer spreadsheet, a CRM export, a demo video, a linked article — lands in
`documents` and is dispatched by media type through
`services/ingestion/pipeline.py`. `gather_material` reads `documents`, so every
one of them now reaches ICP synthesis. Before this, only PDF/DOCX/text did; see
the pipeline module for what the other path did instead.

`/api/uploads` is the same surface under its original path and writes here too.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from app.core.auth import get_current_org
from app.core.database import get_supabase_admin
from app.services.billing.storage_billing import check_storage_quota, update_org_storage_usage
from app.services.ingestion.media_types import (
    ALL_EXTENSIONS,
    extension_of,
    max_upload_bytes,
    media_type_for_extension,
)
from app.workers.asset_tasks import run_ingest_document

log = structlog.get_logger()


async def _safe_task(coro, name: str):
    try:
        await coro
    except Exception:
        log.exception("background_task_failed", task=name)

router = APIRouter(tags=["documents"])


# ---------------------------------------------------------------------------
# Shared upload path — used by this router and by `api/uploads.py`
# ---------------------------------------------------------------------------

async def store_upload(
    *,
    project_id: str,
    org_id: str,
    file: UploadFile,
    material_kind: str = "own",
    source_url: str | None = None,
    title: str | None = None,
) -> dict:
    """Validate, store and queue one upload. Returns the `documents` row.

    One function rather than one per route: the two routes previously kept two
    extension allowlists and two size policies, and only one of them checked the
    organisation's storage quota — so the same file was accepted or rejected,
    billed or unbilled, depending on which URL it arrived at.
    """
    admin = get_supabase_admin()

    ext = extension_of(file.filename)
    if ext not in ALL_EXTENSIONS:
        raise HTTPException(
            status_code=400, detail=f"File type '{ext or file.filename}' not allowed"
        )

    # Cannot be None while `ALL_EXTENSIONS` is derived from the same table this
    # reads. Checked rather than defaulted so a future edit that breaks the
    # correspondence fails here, instead of filing an unreadable file as a
    # document that extracts nothing.
    media_type = media_type_for_extension(ext)
    if media_type is None:  # pragma: no cover - unreachable while the table is consistent
        raise HTTPException(status_code=400, detail=f"No processor for '{ext}'")

    project = (
        admin.table("projects")
        .select("id")
        .eq("id", project_id)
        .eq("organization_id", org_id)
        .execute()
    )
    if not project.data:
        raise HTTPException(status_code=404, detail="Project not found")

    file_bytes = await file.read()
    file_size = len(file_bytes)

    limit = max_upload_bytes(media_type)
    if file_size > limit:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max {limit // (1024 * 1024)} MB for {media_type}",
        )

    quota = check_storage_quota(org_id, file_size)
    if not quota.allowed:
        raise HTTPException(status_code=402, detail=quota.message)

    import re as _re
    import uuid as _uuid

    safe_name = _re.sub(r"[^a-zA-Z0-9._-]", "_", file.filename or "document")[:100]
    doc_uuid = str(_uuid.uuid4())[:8]
    storage_path = f"{org_id}/{project_id}/{doc_uuid}_{safe_name}"
    admin.storage.from_("project-media").upload(storage_path, file_bytes)

    doc = (
        admin.table("documents")
        .insert({
            "project_id": project_id,
            "organization_id": org_id,
            "filename": title or file.filename,
            "file_type": ext,
            "media_type": media_type,
            "source_url": source_url,
            "storage_path": storage_path,
            "file_size_bytes": file_size,
            "material_kind": material_kind,
            "processing_status": "pending",
            "created_at": datetime.now(UTC).isoformat(),
        })
        .execute()
    ).data[0]

    # Storage metering and the asset counter are both denormalised counters
    # updated after the upload has already succeeded, and both follow the same
    # rule: loud and recoverable, never a 500 that tells the client its upload
    # failed and invites a re-upload. `increment_storage` lives in migration 016
    # and, unlike the asset-count RPCs, its signature is in the migrations — but
    # 025 is the record of what "the application calls an RPC no migration
    # defines" costs, so this path does not assume it resolves.
    try:
        update_org_storage_usage(org_id, file_size)
    except Exception:
        log.exception(
            "storage_usage_increment_failed",
            organization_id=org_id,
            document_id=doc["id"],
            bytes=file_size,
            note="document row exists; organizations.storage_bytes_used is now under-counted",
        )

    # Increment project asset count.
    #
    # `projects.asset_count` is a denormalised counter, and the upload has
    # already succeeded by this point: the object is in storage and the row is
    # in `documents`. Letting an RPC failure become a 500 would tell the client
    # its upload failed and invite a re-upload, producing a duplicate document
    # for a wrong badge count. Logged at exception level with the ids needed to
    # reconcile — loud and recoverable, not swallowed.
    #
    # This is now the only site that increments. The media path used to call the
    # same RPC from `ingestion/asset_processor.py` **without `.execute()`**, so
    # the request was built and never sent and media uploads never counted.
    try:
        admin.rpc("increment_asset_count", {"p_project_id": project_id}).execute()
    except Exception:
        log.exception(
            "asset_count_increment_failed",
            project_id=project_id,
            document_id=doc["id"],
            note="document row exists; projects.asset_count is now under-counted",
        )

    asyncio.create_task(_safe_task(run_ingest_document(doc["id"]), "ingest_document"))
    log.info(
        "document_ingest_queued",
        document_id=doc["id"],
        project_id=project_id,
        media_type=media_type,
        material_kind=material_kind,
        bytes=file_size,
    )
    return doc


def delete_upload(document_id: str, org_id: str) -> dict:
    """Delete one document, its stored object and its extracted text."""
    admin = get_supabase_admin()

    doc = (
        admin.table("documents")
        .select("id, storage_path, processed_text_path, project_id, file_size_bytes")
        .eq("id", document_id)
        .eq("organization_id", org_id)
        .execute()
    )
    if not doc.data:
        raise HTTPException(status_code=404, detail="Document not found")
    row = doc.data[0]

    paths = [row["storage_path"]]
    if row.get("processed_text_path"):
        paths.append(row["processed_text_path"])
    admin.storage.from_("project-media").remove(paths)

    admin.table("documents").delete().eq("id", document_id).execute()

    reclaimed = row.get("file_size_bytes") or 0
    if reclaimed:
        try:
            update_org_storage_usage(org_id, -reclaimed)
        except Exception:
            log.exception(
                "storage_usage_decrement_failed",
                organization_id=org_id,
                document_id=document_id,
                bytes=reclaimed,
                note="document deleted; organizations.storage_bytes_used is now over-counted",
            )

    # Decrement project asset count. Same reasoning as the upload path in
    # reverse: the storage object and the row are already gone, so a 500 here
    # would report a failed delete for a delete that happened, and the client's
    # retry would 404.
    try:
        admin.rpc("decrement_asset_count", {"p_project_id": row["project_id"]}).execute()
    except Exception:
        log.exception(
            "asset_count_decrement_failed",
            project_id=row["project_id"],
            document_id=document_id,
            note="document row deleted; projects.asset_count is now over-counted",
        )

    return {"detail": "Document deleted", "storage_reclaimed_bytes": reclaimed}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/upload")
async def upload_document(
    project_id: str = Query(...),
    material_kind: Literal["own", "competitor", "market"] = Query("own"),
    source_url: str | None = Query(None),
    file: UploadFile = File(...),
    auth: dict = Depends(get_current_org),
):
    """Upload material of any supported kind and trigger extraction.

    `material_kind` is the adversarial cohort's grounding, not a tag. A
    competitor may be named in a simulation only from a document uploaded here
    as `competitor` — PRD §4 permits incumbent-aligned agents grounded in
    material the user uploaded and forbids them grounded in model memory, and
    that distinction is unenforceable unless it is recorded at upload.

    Ingestion proposes a kind of its own into `material_kind_suggested`. It is
    never written to `material_kind`, and no confidence promotes it:
    DECISIONS_V2 §7, and the reasoning in `services/ingestion/classifier.py`.
    """
    log.info(
        "upload_document",
        project_id=project_id,
        filename=file.filename,
        org_id=auth["org_id"],
    )
    return await store_upload(
        project_id=project_id,
        org_id=auth["org_id"],
        file=file,
        material_kind=material_kind,
        source_url=source_url,
    )


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


@router.get("/{id}/text")
async def get_document_text(id: str, auth: dict = Depends(get_current_org)):
    """The text extraction ICP synthesis will actually read.

    Exposed because "the file uploaded successfully" and "the file contributed
    anything" were indistinguishable from outside the system — which is how a
    `.pptx` deck whose extraction returned an error string looked, in the UI,
    exactly like a processed deck.
    """
    admin = get_supabase_admin()
    result = (
        admin.table("documents")
        .select(
            "id, filename, media_type, processing_status, processed_text_path, "
            "extracted_char_count, material_kind, material_kind_suggested, "
            "material_kind_confidence, error_message"
        )
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found")
    row = result.data[0]

    text = ""
    if row.get("processed_text_path"):
        raw = admin.storage.from_("project-media").download(row["processed_text_path"])
        text = raw.decode("utf-8", errors="replace")
    return {**row, "extracted_text": text}


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


class DocumentUpdate(BaseModel):
    """What may be corrected on a document after upload.

    `material_kind` is **required**, not `str | None`. An optional field would
    make a body that omits it a 200 that changed nothing, and the caller cannot
    tell that apart from a confirmed decision — which is the one thing this
    field must never be ambiguous about.
    """

    material_kind: Literal["own", "competitor", "market"]


@router.patch("/{id}")
async def update_document(
    id: str,
    body: DocumentUpdate,
    auth: dict = Depends(get_current_org),
):
    """Correct a document's material kind.

    Until this existed, `material_kind` was settable only as a query parameter
    at upload time and there was no way to change it afterwards. Two
    consequences, both of them live:

    - Every document uploaded before the control existed carries NULL, and
      `gather_material` reads NULL as `own`. **Competitor grounding was
      unreachable for every one of those projects** — not degraded, unreachable:
      an adversarial archetype may name a competitor only from a document marked
      `competitor` (PRD §4, DECISIONS_V2 §7), and no such document could exist.
    - A founder who mislabelled a file had to delete and re-upload it, which
      also re-runs ingestion and re-bills the storage.

    **The kind is set only from an explicit request.** Ingestion writes its own
    opinion to `material_kind_suggested` / `material_kind_confidence` and this
    route does not read either of them, at any confidence. The guardrail is that
    a human decided a document is competitor material; a classifier agreeing
    with itself is not that decision, and promoting a suggestion here would make
    the two indistinguishable everywhere downstream — see
    `services/ingestion/classifier.py`.

    Logged with the old and the new value because this changes what the *next*
    synthesis grounds on: a competitor label appearing or disappearing changes
    whether a named rival can be spoken in published copy, and that has to be
    reconstructible from the logs after the fact.
    """
    admin = get_supabase_admin()

    # Read scoped to the org, then write scoped to the org. The read is what
    # produces the 404 and the `from` value; the `eq` on the update is not
    # redundant with it, because dropping it would leave a cross-tenant write
    # one refactor away from being reintroduced.
    current = (
        admin.table("documents")
        .select("id, material_kind, project_id")
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
        .execute()
    )
    if not current.data:
        raise HTTPException(status_code=404, detail="Document not found")
    row = current.data[0]

    # NULL is read as `own` everywhere downstream, so it is reported as `own`
    # here too rather than as a second value meaning the same thing.
    previous = row.get("material_kind") or "own"

    updated = (
        admin.table("documents")
        .update({"material_kind": body.material_kind})
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
        .execute()
    )
    if not updated.data:  # pragma: no cover - the row was read one statement ago
        raise HTTPException(status_code=404, detail="Document not found")

    log.info(
        "document_material_kind_updated",
        document_id=id,
        project_id=row.get("project_id"),
        organization_id=auth["org_id"],
        material_kind_from=previous,
        material_kind_to=body.material_kind,
        detail="changes what the next ICP synthesis grounds on",
    )
    return updated.data[0]


@router.delete("/{id}")
async def delete_document(id: str, auth: dict = Depends(get_current_org)):
    """Delete a document and its storage files."""
    log.info("delete_document", document_id=id)
    return delete_upload(id, auth["org_id"])
