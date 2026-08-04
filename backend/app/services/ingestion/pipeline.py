# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# ingest_document(document_id: str) -> IngestResult
# extracted_text_path(storage_path: str) -> str
# EXTRACTED_TEXT_BUCKET
# ─────────────────────────────────────────────────────────
"""One ingest path for every kind of upload, feeding one table.

## What this replaces

There were two upload systems that never met.

| | Live | Orphaned |
|---|---|---|
| API | `/api/documents` → `documents` | `/api/uploads` → `project_assets` |
| Processing | `engine/document_processor.py` | `ingestion/{vision,video,spreadsheet,article}` |
| Reaches ICP synthesis | yes | no |

`gather_material` reads `documents`. So a client who uploaded a deck as images,
a customer spreadsheet, a CRM export, a demo video or a linked article
contributed **nothing** to their own ICP — the file uploaded, the processor ran,
the text was written to storage, and the audience was synthesized as if none of
it had been sent. Nothing errored. V1_AUDIT item 39 lists `/api/uploads`, all
five processors and `project_assets` as having no caller at all.

The fix is one upload surface, not two tables kept in sync. `documents` carries
a `media_type`, this module dispatches on it, and both API routes write here.
Keeping both tables and teaching `gather_material` to read both would have left
two schemas, two status vocabularies and two places to remember — the "two
sources of truth" class in HANDOFF §2a, which this repo keeps re-shipping.

## Where the extracted text lives

In storage, at `processed_text_path`, with only `extracted_char_count` on the
row. Two reasons, both load-bearing:

* `GET /api/documents` selects `*`. A `TEXT` column holding a 50MB PDF's text
  would be shipped to the browser on every list.
* `gather_material` budgets characters across sources. With the count on the
  row it can decide what to include **before** downloading anything, so a
  document that loses the budget costs nothing to skip.

Re-extracting per synthesis was the alternative, and it is not viable once
images and video are in scope: an image's text exists only after a vision call
and a video's only after Whisper plus ten vision calls. Re-deriving that on
every ICP synthesis would re-bill the founder for material they already
uploaded.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from app.core.database import get_supabase_admin
from app.services.ingestion.article_processor import process_article
from app.services.ingestion.classifier import suggest_material_kind
from app.services.ingestion.media_types import media_type_for_extension
from app.services.ingestion.presentation_processor import process_presentation
from app.services.ingestion.spreadsheet_processor import process_spreadsheet
from app.services.ingestion.video_processor import process_video
from app.services.ingestion.vision_processor import process_image

logger = structlog.get_logger()

EXTRACTED_TEXT_BUCKET = "project-media"

# Guards the row against an extractor that "succeeded" and returned nothing.
# A `complete` document with no text is the exact shape of the defect this work
# exists to remove — the source contributes zero characters and reports health.
_MIN_USEFUL_CHARS = 1


@dataclass(frozen=True)
class IngestResult:
    document_id: str
    media_type: str
    chars: int
    suggested_kind: str | None
    suggested_confidence: float | None


def extracted_text_path(storage_path: str) -> str:
    """Where the extracted text for a stored object lives."""
    return storage_path.rsplit(".", 1)[0] + "_extracted.txt"


async def _extract(
    media_type: str,
    file_bytes: bytes,
    doc: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Dispatch to the processor that can read this media type.

    No `else: pass` and no default branch. An unroutable media type raises, the
    document goes to `failed` with the reason on the row, and the founder is
    told — rather than the file being quietly filed as read.
    """
    filename = doc.get("filename") or "upload"

    if media_type == "document":
        # Imported here rather than at module scope: `document_processor` pulls
        # in PyMuPDF, and this module is imported by the API layer on every
        # request path that touches uploads.
        from app.services.engine.document_processor import _extract_text

        text, encoding, page_count = _extract_text(file_bytes, doc.get("file_type") or "txt")
        return text, {"encoding": encoding, "page_count": page_count, "file_size": len(file_bytes)}

    if media_type == "presentation":
        result = await process_presentation(file_bytes, filename)
    elif media_type == "image":
        result = await process_image(file_bytes, filename)
    elif media_type == "video":
        result = await process_video(file_bytes, filename)
    elif media_type == "spreadsheet":
        result = await process_spreadsheet(file_bytes, filename)
    elif media_type == "news_article":
        result = await process_article(
            source_url=doc.get("source_url"),
            html_content=file_bytes.decode("utf-8", errors="replace") if file_bytes else None,
        )
    else:
        raise ValueError(f"No processor for media type {media_type!r}")

    return result.get("extracted_text", ""), dict(result.get("metadata") or {})


def _resolve_media_type(doc: dict[str, Any]) -> str:
    """The stored media type, or one derived from the extension.

    Rows written before `documents.media_type` existed have NULL here, and they
    are all plain documents — but deriving rather than assuming keeps a legacy
    `.xlsx` readable, and an extension nobody mapped raises instead of being
    filed as a document.
    """
    stored = (doc.get("media_type") or "").strip()
    if stored:
        return stored

    derived = media_type_for_extension(doc.get("file_type"))
    if derived is None:
        raise ValueError(
            f"Unsupported file type {doc.get('file_type')!r} — no processor can read it"
        )
    logger.info(
        "document_media_type_derived",
        document_id=doc.get("id"),
        file_type=doc.get("file_type"),
        media_type=derived,
        detail="row predates documents.media_type",
    )
    return derived


async def ingest_document(document_id: str) -> IngestResult:
    """Extract one uploaded document's text, persist it, and classify it.

    Terminal states are `complete` (text is in storage and the character count
    is on the row) or `failed` (the reason is on the row). There is no third
    state in which the row looks processed and holds nothing.
    """
    admin = get_supabase_admin()

    doc = (
        admin.table("documents")
        .select("*")
        .eq("id", str(document_id))
        .single()
        .execute()
    ).data
    if not doc:
        raise ValueError(f"Document {document_id} not found")

    admin.table("documents").update(
        {"processing_status": "processing"}
    ).eq("id", str(document_id)).execute()

    try:
        media_type = _resolve_media_type(doc)
        file_bytes = admin.storage.from_(EXTRACTED_TEXT_BUCKET).download(doc["storage_path"])
        text, metadata = await _extract(media_type, file_bytes, doc)

        if len(text.strip()) < _MIN_USEFUL_CHARS:
            raise ValueError(
                f"{media_type} extraction produced no text — nothing to contribute "
                "to the audience this project's ICP is derived from"
            )

        text_path = extracted_text_path(doc["storage_path"])
        admin.storage.from_(EXTRACTED_TEXT_BUCKET).upload(
            text_path,
            text.encode("utf-8"),
            {"content-type": "text/plain", "upsert": "true"},
        )

        # A *proposal*, written to its own columns. It never touches
        # `material_kind`, and no confidence promotes it — see
        # `ingestion/classifier.py` and DECISIONS_V2 §7. An auto-classification
        # that could set `material_kind = 'competitor'` would let a cheap model
        # license a named competitor comparison a founder could publish.
        suggestion = await suggest_material_kind(
            text, filename=doc.get("filename") or "upload", media_type=media_type
        )

        admin.table("documents").update({
            "processing_status": "complete",
            "media_type": media_type,
            "processed_text_path": text_path,
            "extracted_char_count": len(text),
            "extraction_metadata": metadata,
            "material_kind_suggested": suggestion.kind if suggestion else None,
            "material_kind_confidence": suggestion.confidence if suggestion else None,
            "error_message": None,
        }).eq("id", str(document_id)).execute()

        logger.info(
            "document_ingested",
            document_id=str(document_id),
            project_id=doc.get("project_id"),
            media_type=media_type,
            chars=len(text),
            suggested_material_kind=suggestion.kind if suggestion else None,
            material_kind=doc.get("material_kind"),
        )
        return IngestResult(
            document_id=str(document_id),
            media_type=media_type,
            chars=len(text),
            suggested_kind=suggestion.kind if suggestion else None,
            suggested_confidence=suggestion.confidence if suggestion else None,
        )

    except Exception as exc:
        admin.table("documents").update({
            "processing_status": "failed",
            "error_message": str(exc)[:500],
        }).eq("id", str(document_id)).execute()
        logger.error(
            "document_ingest_failed",
            document_id=str(document_id),
            project_id=doc.get("project_id"),
            file_type=doc.get("file_type"),
            media_type=doc.get("media_type"),
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise
