# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# sweep_once(now=None) -> dict[str, int]      [async]
# start_reaper() -> None                      [async, background task]
# STUCK, SWEEP_INTERVAL_SECONDS
# ─────────────────────────────────────────────────────────
"""Nothing stays half-finished forever.

Every worker in this codebase writes a non-terminal status, does its work, and
writes a terminal one. That is correct until the process stops between the two
— and it does, routinely:

- **A deploy.** Render restarts the service, and every in-flight job dies
  mid-write. Observed while testing this very release: three reports were
  killed at `generating` with `section_count` already set and zero characters
  of markdown, and they will sit there forever.
- **A job that cannot be cancelled.** `asyncio.wait_for` cancels at an
  `await`, and Playwright's own teardown can block that cancellation. A
  website check sat at `capturing` for eleven minutes with a 150-second
  deadline that never landed. The deadline is still right; it is just not
  sufficient on its own.

`gtm/discovery` states the limit plainly in its own docstring — "if the API
process dies mid-run, the run row stays `running`. There is no worker to reap
it" — and names the query that finds them. This is that worker.

**What it does not do.** It does not resume anything: the work is gone and
pretending otherwise would be worse. It closes the row with a sentence a
founder can act on, which is this codebase's standing rule — never a spinner
with no ending.

**Refunds are narrow on purpose.** A row is refunded only where the state
itself proves nothing was spent: `capturing` means no page was ever read, so
no critic ran and no model was called. A job that died during its critics
consumed real compute and is not refunded. A rule that quietly sometimes pays
is worse than one that says plainly when it does.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog

from app.core.database import get_supabase_admin
from app.services.billing.agent_pricing import refund_credits

log = structlog.get_logger()

SWEEP_INTERVAL_SECONDS = 300


@dataclass(frozen=True)
class StuckRule:
    """One table's non-terminal states and how long they may legitimately last.

    The deadlines are generous — comfortably longer than the slowest honest
    run of each kind — because closing a job that was still working is worse
    than leaving a dead one a few minutes longer. A founder who sees a run
    killed at minute nine that would have finished at minute ten has lost
    something real; one whose dead row is closed at minute forty has only
    waited.
    """

    table: str
    states: tuple[str, ...]
    minutes: int
    message: str
    # Refund only where the state itself proves no model was called.
    refund_states: tuple[str, ...] = ()
    # Where this table keeps its founder-readable failure sentence.
    #
    # Six tables call it `error_message`; `gtm_discovery_runs` calls it `error`.
    # Naming a column a table does not have makes PostgREST reject the whole
    # update — which is exactly how `reports` was silently skipped on every
    # sweep for days. This is a schema fact per table, not a flag somebody
    # maintains by hand: a rule cannot be written without answering it.
    error_column: str = "error_message"

    # There was a `writes_message` flag here, because `reports` had no
    # `error_message` column and naming one that does not exist makes PostgREST
    # reject the entire update — silently, on every sweep. `reports` gained the
    # column on 2026-08-22, so every rule writes its sentence and the flag was
    # dead. It is not coming back: a hand-maintained boolean is the wrong guard
    # for a schema fact. The right one is already in `sweep_once`, which counts
    # and logs failed updates at error level, so the next missing column is
    # loud on the first sweep instead of invisible forever.


STUCK: tuple[StuckRule, ...] = (
    # The run itself, and the omission that proved the point. The first
    # version of this list covered every artifact built *from* a run and not
    # the run, which is the one `gtm/discovery`'s docstring actually names —
    # "completed_at IS NULL AND status = 'running'". A Ledgerline run sat at
    # `analyzing` for twenty-seven minutes while its neighbours were closed.
    #
    # **`ready` is deliberately absent.** It is a resting state, not a
    # half-finished one: a prepared run waits there for the founder to press
    # start, and reaping it would destroy work nobody had abandoned. That
    # distinction is the whole reason these states are listed rather than
    # inferred as "not terminal".
    #
    # Ninety minutes because a large run is genuinely long: agents, rounds and
    # arenas multiply, and the analysis pass that follows is model-heavy.
    StuckRule(
        "simulations", ("queued", "preparing", "running", "analyzing"), 90,
        "This run stopped before it finished. Anything it had already measured "
        "is saved — start a new run when you're ready.",
    ),
    # Forty-five minutes, not twenty, and the arithmetic is the argument.
    #
    # At twenty this rule was **shorter than the worker's own bound**, so it
    # refunded checks that were still legitimately working. `capture._bounded`
    # gives each capture `_QUEUE_WAIT_S` = 330s of queue plus
    # `_overall_deadline(45)` = 300s of work, and a check that names a site the
    # founder admires runs two of them: 2 x 630s = 1,260s = 21 minutes still at
    # `capturing`, before the critic panel, the screenshot uploads or the
    # design-gallery pass have started. The founder was handed the complete
    # 1,750-credit critique *and* a full refund of it — and the slowest pages
    # are exactly the heavy commercial ones render.yaml names as the case the
    # module exists to serve.
    #
    # The deadline is generous on purpose (see StuckRule): closing a job that
    # was still working is the expensive mistake, and 45 leaves the same margin
    # over the worker's ceiling that `page_revisions` has over its own.
    StuckRule(
        "website_snapshots", ("queued", "capturing", "judging"), 45,
        "This check stopped before it finished. Nothing was left half-saved — "
        "start it again when you're ready.",
        refund_states=("queued", "capturing"),
    ),
    StuckRule(
        # `generating`, not `running`. The worker has always written
        # `generating` (revision_tasks.py) and this rule has always watched
        # `running`, a status nothing writes — so a wedged revision sat at
        # `generating` forever: no failure sentence, **no refund of 5,000
        # credits**, and a spinner the founder could not clear. The most
        # expensive artifact in the product was the one the reaper could not
        # see. `test_every_non_terminal_status_a_worker_writes_is_reapable`
        # pins the rules against the workers so this cannot drift again.
        # 45 was shorter than the work. Do the arithmetic once, here, so the
        # next person does not have to: a revision runs up to 3 rounds, each
        # one a `capture_html` that may queue 330s for the two-slot browser and
        # then work for 300s, on top of up to 2 `capture_website` calls for the
        # page and its reference. That is ~52 minutes of legitimate work
        # against a 45-minute rule, so the reaper was closing revisions that
        # were still running — and the worker then wrote `complete` over the
        # closed row, because its compare-and-set was missing too.
        #
        # 80 covers the worst case with headroom. A founder whose revision is
        # genuinely wedged waits longer; one whose revision is merely slow gets
        # the artifact they paid 5,000 credits for.
        "page_revisions", ("queued", "generating"), 80,
        "This revision stopped before it finished. Your original check is "
        "safe; start the revision again when you're ready.",
        # Still `queued` only. `generating` means vision calls were made and
        # paid for, and this list's rule is that a refund needs the state
        # itself to prove no model ran. Reaping the row is the fix; refunding
        # spent work would be a different decision.
        refund_states=("queued",),
    ),
    StuckRule(
        "reports", ("queued", "generating"), 40,
        # The gap this comment used to describe is closed: `reports` gained an
        # `error_message` column on 2026-08-22, so the sentence is written
        # rather than merely recorded here. It mattered — two of three reports
        # that day failed, and a founder saw the word "failed" and nothing else.
        "This write-up stopped before it finished. Your run and its findings "
        "are safe — generate it again from the run.",
    ),
    StuckRule(
        "answer_packs", ("queued", "building"), 30,
        "We could not finish building your answers. Your run and its "
        "objections are safe — try building it again.",
        refund_states=("queued",),
    ),
    StuckRule(
        "messaging_docs", ("queued", "building"), 30,
        "We could not finish building your messaging document. Your run and "
        "its objections are safe — try building it again.",
        refund_states=("queued",),
    ),
    StuckRule(
        "outbound_sequences", ("queued", "building"), 30,
        "We could not finish writing your outbound sequences. Your run and "
        "its objections are safe — try building them again.",
        refund_states=("queued",),
    ),
    StuckRule(
        "capital_shortlists", ("queued", "building"), 20,
        "We could not finish building your shortlist. Try again when you're "
        "ready.",
        refund_states=("queued",),
    ),
    # The two most expensive charge-at-create tables in the product, and until
    # now neither had a rule at all.
    #
    # A COMPREHENSIVE clearance deducts 6,000 credits (`api/clearance.py`)
    # before the worker is spawned — three times the entire free-tier grant —
    # and `workers/clearance_tasks.py` then parks the row at `running`. A deploy
    # kills it and the row sits there forever: no sentence, no refund, no
    # ending. The guard test above could not see it, because a table with **no
    # rule at all** was silently exempt from the scan; both halves were fixed
    # together.
    #
    # `queued` refunds because the worker never started — the row is created
    # `queued` by the API and only `run_clearance` writes `running`, so the
    # state itself proves the USPTO was never called. `running` does not.
    StuckRule(
        "clearance_runs", ("queued", "running"), 45,
        "This search stopped before it finished. Nothing was left half-saved — "
        "run it again when you're ready.",
        refund_states=("queued",),
    ),
    # `gtm_discovery_runs` is the case this module's own docstring names: "if
    # the API process dies mid-run, the run row stays `running`. There is no
    # worker to reap it." There still was not one. It is created `running` by
    # `services/gtm/store.create_run` after up to 1,254 credits are deducted,
    # and its status is written from `services/`, not `workers/`, which is why
    # the worker scan never saw it either.
    #
    # No refund state: `running` is the only non-terminal status and it means
    # the queries were already going out. A partial run's money is reconciled by
    # `discovery.reconcile_run` through `refund_discovery_credits`, which claims
    # the row — a second, blind refund from here would pay twice.
    #
    # `error`, not `error_message`: this is the one table that spells it that
    # way (migration 027), and naming the wrong column would disable the rule on
    # every sweep.
    StuckRule(
        "gtm_discovery_runs", ("running",), 30,
        "This search stopped before it finished. Any companies it had already "
        "found are saved — start a new search when you're ready.",
        error_column="error",
    ),
)


async def sweep_once(now: datetime | None = None) -> dict[str, int]:
    """Close every row that has been mid-flight past its deadline.

    Returns per-table counts. Never raises: a maintenance pass that takes the
    process down with it is worse than the rows it was meant to clean.
    """
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    admin = get_supabase_admin()
    closed: dict[str, int] = {}
    failures: dict[str, int] = {}

    for rule in STUCK:
        cutoff = (moment - timedelta(minutes=rule.minutes)).isoformat()
        try:
            rows = (
                admin.table(rule.table)
                # `*` rather than a column list, and this is not laziness.
                # Naming `credits_charged` made the whole rule fail on
                # `reports`, which has no such column — PostgREST rejects the
                # select, the handler below logs it, and that table is skipped
                # on every sweep forever. Three orphaned reports sat there
                # while the website rows beside them were being closed
                # correctly. These rows are small and capped at 200.
                .select("*")
                .in_("status", list(rule.states))
                .lt("created_at", cutoff)
                .limit(200)
                .execute()
            ).data or []
        except Exception:  # noqa: BLE001
            failures[rule.table] = failures.get(rule.table, 0) + 1
            log.exception("reaper_read_failed", table=rule.table)
            continue

        for row in rows:
            # Read before the write. The refund decision turns on the state the
            # row was found in, and reading it back afterwards would ask the
            # question of a row this loop has already changed.
            was = str(row.get("status") or "")
            org_id = row.get("organization_id")
            charged = int(row.get("credits_charged") or 0)

            payload: dict[str, object] = {
                "status": "failed",
                rule.error_column: rule.message,
            }

            try:
                updated = (
                    admin.table(rule.table)
                    .update(payload)
                    .eq("id", row["id"])
                    .eq("status", was)
                    .execute()
                )
            except Exception:  # noqa: BLE001
                failures[rule.table] = failures.get(rule.table, 0) + 1
                log.exception(
                    "reaper_close_failed", table=rule.table, row_id=row.get("id")
                )
                continue

            # The `.eq("status", was)` guard above is a compare-and-set, and its
            # result has to be read or the guard protects only the row.
            #
            # Zero rows means the worker moved this row on between the SELECT
            # and the UPDATE — which is a real window, not a theoretical one:
            # the read takes up to 200 rows and the writes then go out one
            # network round-trip at a time, while the worker's own status write
            # happens at an `await` in the same loop. Discarding the result
            # counted that row as closed, logged it as a normal close, and — the
            # expensive part — **paid the refund anyway**, on a check the
            # founder actually received. Nothing on the row records that a
            # refund was paid, so a later sweep could pay again.
            if not (updated.data or []):
                log.info(
                    "reaper_close_lost_race",
                    table=rule.table,
                    row_id=row.get("id"),
                    was=was,
                    detail="the worker finished between the read and the write; "
                           "it wins, and nothing is refunded",
                )
                continue

            closed[rule.table] = closed.get(rule.table, 0) + 1
            log.warning(
                "reaper_closed_stuck_row",
                table=rule.table,
                row_id=row.get("id"),
                was=was,
                age_minutes=rule.minutes,
            )

            if was in rule.refund_states:
                refund_credits(
                    org_id, charged, reason=f"reaper:{rule.table}:{was}"
                )

    if closed:
        log.warning("reaper_sweep_closed_rows", closed=closed)
    if failures:
        # Loud, and separate from the per-row exceptions above.
        #
        # Twice now a rule has been broken by a column the table did not have,
        # and both times the per-row `log.exception` was indistinguishable
        # from ordinary noise — a rule failing on every sweep forever looked
        # exactly like a table with nothing to clean. A sweep that could not
        # do its job must say so as a fact about the sweep, not as a stack
        # trace somebody has to go looking for.
        log.error(
            "reaper_sweep_had_failures",
            failures=failures,
            detail="one or more rules could not complete; a rule that fails "
                   "every sweep leaves those rows stuck forever",
        )
    return closed


async def start_reaper() -> None:
    """Sweep at startup, then on an interval.

    **At startup first, deliberately.** A deploy is the single most common way
    work is orphaned, and the process that comes up is the one best placed to
    notice what the process that went down left behind.
    """
    log.info("reaper_started", interval_s=SWEEP_INTERVAL_SECONDS)
    while True:
        try:
            await sweep_once()
        except asyncio.CancelledError:
            log.info("reaper_stopped")
            raise
        except Exception:  # noqa: BLE001
            log.exception("reaper_sweep_failed")
        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
