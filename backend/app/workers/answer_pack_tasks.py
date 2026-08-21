# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# run_answer_pack(pack_id, simulation_id, org_id) -> None
# GENERIC_FAILURE_MESSAGE
# ─────────────────────────────────────────────────────────
"""Build one objection matrix, in the background, and never leak a traceback.

The pack row is created and charged by the route, so this worker's only job
is to fill it in or to say honestly that it could not.

**The failure message is founder-readable, always.** The neighbouring
clearance worker writes `f"[{name}] {type(exc).__name__}: {exc}"` into a
column the UI renders, which is how a founder ends up reading
`KeyError: 'organization_id'` in monospace on a page they paid for. That is a
logged defect in this repo's own pre-launch register, so it is not copied
here: the exception goes to the log with its type and message, and the founder
gets a sentence. The two audiences want different things and only one of them
can act on a stack trace.
"""
from __future__ import annotations

from datetime import UTC, datetime

import structlog
from pydantic import ValidationError

from app.core.database import get_supabase_admin
from app.services.gtm.answer_pack import build_answer_pack

log = structlog.get_logger()

# What a founder reads when the build dies. It says what happened, what it
# cost them, and what to do — the three things a failure notice owes someone
# who has already paid.
GENERIC_FAILURE_MESSAGE = (
    "We could not finish building your answers. Your run and its objections "
    "are safe — this was the write-up step only. Try building it again; if it "
    "keeps failing, tell us and we will look."
)


async def run_answer_pack(pack_id: str, simulation_id: str, org_id: str) -> None:
    admin = get_supabase_admin()

    def _fail(message: str) -> None:
        admin.table("answer_packs").update({
            "status": "failed",
            "error_message": message,
        }).eq("id", pack_id).execute()

    admin.table("answer_packs").update({"status": "building"}).eq("id", pack_id).execute()

    try:
        pack = await build_answer_pack(simulation_id, org_id)
    except ValidationError as exc:
        # `ValidationError` subclasses `ValueError`, so this must be caught
        # first or a model that emits malformed JSON is treated as a
        # deliberate refusal and its pydantic error is shown to the founder.
        # Observed in production on the sibling outbound worker.
        log.error(
            "answer_pack_unparseable",
            pack_id=pack_id,
            simulation_id=simulation_id,
            error=str(exc)[:400],
        )
        _fail(GENERIC_FAILURE_MESSAGE)
        return
    except ValueError as exc:
        # The one failure with something useful to say: the run carries no
        # measured objections, so there is nothing to build answers from.
        # `build_answer_pack` raises this with a founder-readable sentence
        # already, so it is passed through rather than replaced.
        log.warning(
            "answer_pack_refused",
            pack_id=pack_id,
            simulation_id=simulation_id,
            reason=str(exc),
        )
        _fail(str(exc))
        return
    except Exception as exc:  # noqa: BLE001 — the boundary; nothing above catches
        log.error(
            "answer_pack_failed",
            pack_id=pack_id,
            simulation_id=simulation_id,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        _fail(GENERIC_FAILURE_MESSAGE)
        return

    admin.table("answer_packs").update({
        "status": "complete",
        "rows": [row.model_dump() for row in pack.rows],
        "battlecards": [card.model_dump() for card in pack.battlecards],
        "notes": pack.notes,
        "built_from_objections": pack.built_from_objections,
        "completed_at": datetime.now(UTC).isoformat(),
    }).eq("id", pack_id).execute()

    log.info(
        "answer_pack_complete",
        pack_id=pack_id,
        simulation_id=simulation_id,
        rows=len(pack.rows),
        battlecards=len(pack.battlecards),
    )
