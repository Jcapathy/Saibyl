# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# run_outbound_sequences(sequence_id, simulation_id, org_id) -> None
# GENERIC_FAILURE_MESSAGE
# ─────────────────────────────────────────────────────────
"""Write one run's outbound sequences in the background, and never leak a traceback.

The row is created and charged by the route, so this worker's only job is to
fill it in or to say honestly that it could not.

**The failure message is founder-readable, always.** The clearance worker
writes `f"[{name}] {type(exc).__name__}: {exc}"` into a column the UI renders,
which is how a founder ends up reading `KeyError: 'organization_id'` in
monospace on a page they paid for. That is a logged defect in this repo's own
pre-launch register, so it is not copied here: the exception goes to the log
with its type and message, and the founder gets a sentence. The two audiences
want different things and only one of them can act on a stack trace.

**Nothing here sends anything.** The worker writes copy into a row. There is no
mail transport, no LinkedIn client and no dialler in this module or the service
it calls, and no personal contact record is read or written at any point — see
`services/gtm/outbound.py` and `services/gtm/privacy.py` for why that boundary
is where it is.
"""
from __future__ import annotations

from datetime import UTC, datetime

import structlog
from pydantic import ValidationError

from app.core.database import get_supabase_admin
from app.services.gtm.outbound import build_outbound_sequences

log = structlog.get_logger()

# What a founder reads when the build dies. It says what happened, what it cost
# them, and what to do — the three things a failure notice owes someone who has
# already paid.
GENERIC_FAILURE_MESSAGE = (
    "We could not finish writing your outbound sequences. Your run and its "
    "objections are safe — this was the write-up step only. Try building them "
    "again; if it keeps failing, tell us and we will look."
)


async def run_outbound_sequences(sequence_id: str, simulation_id: str, org_id: str) -> None:
    admin = get_supabase_admin()

    def _fail(message: str) -> None:
        admin.table("outbound_sequences").update({
            "status": "failed",
            "error_message": message,
        }).eq("id", sequence_id).execute()

    admin.table("outbound_sequences").update(
        {"status": "building"}
    ).eq("id", sequence_id).execute()

    try:
        built = await build_outbound_sequences(simulation_id, org_id)
    except ValidationError as exc:
        # **`ValidationError` subclasses `ValueError`**, so without this branch
        # a model that emits malformed JSON is treated as a deliberate refusal
        # and its pydantic error is written verbatim into a column a founder
        # reads. That happened in production: a Chartwell sequence failed with
        # "1 validation error for _Generated / Invalid JSON: expected `,` or
        # `}` at line 16 column 375" shown to the customer.
        #
        # It must be caught BEFORE the ValueError branch below, because
        # `except` clauses are tried in order and the subclass would otherwise
        # never be reached.
        log.error(
            "outbound_unparseable",
            sequence_id=sequence_id,
            simulation_id=simulation_id,
            error=str(exc)[:400],
        )
        _fail(GENERIC_FAILURE_MESSAGE)
        return
    except ValueError as exc:
        # The refusals with something useful to say: the run carries no measured
        # objections, or no buyer profile to write to. `build_outbound_sequences`
        # raises these with a founder-readable sentence already, so it is passed
        # through rather than replaced.
        log.warning(
            "outbound_refused",
            sequence_id=sequence_id,
            simulation_id=simulation_id,
            reason=str(exc),
        )
        _fail(str(exc))
        return
    except Exception as exc:  # noqa: BLE001 — the boundary; nothing above catches
        log.error(
            "outbound_failed",
            sequence_id=sequence_id,
            simulation_id=simulation_id,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        _fail(GENERIC_FAILURE_MESSAGE)
        return

    admin.table("outbound_sequences").update({
        "status": "complete",
        "sequences": [sequence.model_dump() for sequence in built.sequences],
        "notes": built.notes,
        "built_from_objections": built.built_from_objections,
        "winning_variant_key": built.winning_variant_key,
        "winning_message": built.winning_message,
        "completed_at": datetime.now(UTC).isoformat(),
    }).eq("id", sequence_id).execute()

    log.info(
        "outbound_complete",
        sequence_id=sequence_id,
        simulation_id=simulation_id,
        sequences=len(built.sequences),
        steps=sum(len(s.steps) for s in built.sequences),
    )
