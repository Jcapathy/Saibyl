# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# run_messaging_doc(doc_id, simulation_id, org_id) -> None
# GENERIC_FAILURE_MESSAGE
# ─────────────────────────────────────────────────────────
"""Build one messaging document, in the background, and never leak a traceback.

The row is created and charged by the route, so this worker's only job is to
fill it in or to say honestly that it could not.

**The failure message is founder-readable, always.** The clearance worker
writes `f"[{name}] {type(exc).__name__}: {exc}"` into a column the UI renders,
which is how a founder ends up reading `KeyError: 'organization_id'` in
monospace on a page they paid for. That is a logged defect in this repo's own
pre-launch register, so it is not copied here: the exception goes to the log
with its type and message, and the founder gets a sentence. The two audiences
want different things and only one of them can act on a stack trace.
"""
from __future__ import annotations

from datetime import UTC, datetime

import structlog

from app.core.database import get_supabase_admin
from app.services.gtm.messaging_doc import build_messaging_doc

log = structlog.get_logger()

# What a founder reads when the build dies. It says what happened, what it
# cost them, and what to do — the three things a failure notice owes someone
# who has already paid.
GENERIC_FAILURE_MESSAGE = (
    "We could not finish building your messaging document. Your run and its "
    "objections are safe — this was the write-up step only. Try building it "
    "again; if it keeps failing, tell us and we will look."
)


async def run_messaging_doc(doc_id: str, simulation_id: str, org_id: str) -> None:
    admin = get_supabase_admin()

    def _fail(message: str) -> None:
        admin.table("messaging_docs").update({
            "status": "failed",
            "error_message": message,
        }).eq("id", doc_id).execute()

    admin.table("messaging_docs").update({"status": "building"}).eq("id", doc_id).execute()

    try:
        doc = await build_messaging_doc(simulation_id, org_id)
    except ValueError as exc:
        # The one failure with something useful to say: the run carries no
        # measured objections, so there is nothing to build a document from.
        # `build_messaging_doc` raises this with a founder-readable sentence
        # already, so it is passed through rather than replaced.
        log.warning(
            "messaging_doc_refused",
            doc_id=doc_id,
            simulation_id=simulation_id,
            reason=str(exc),
        )
        _fail(str(exc))
        return
    except Exception as exc:  # noqa: BLE001 — the boundary; nothing above catches
        log.error(
            "messaging_doc_failed",
            doc_id=doc_id,
            simulation_id=simulation_id,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        _fail(GENERIC_FAILURE_MESSAGE)
        return

    admin.table("messaging_docs").update({
        # One JSONB column rather than a column per section: the worksheet is
        # read whole and its shape is owned by the Pydantic model, so
        # splitting it across columns would put the schema in two places and
        # let them disagree.
        "document": doc.model_dump(mode="json"),
        "status": "complete",
        "built_from_objections": doc.built_from_objections,
        "completed_at": datetime.now(UTC).isoformat(),
    }).eq("id", doc_id).execute()

    log.info(
        "messaging_doc_complete",
        doc_id=doc_id,
        simulation_id=simulation_id,
        objections=len(doc.objections),
        placeholders=doc.placeholders_to_fill,
    )
