"""Cron entrypoint: ask founders whether the room was right.

Run daily by the `saibyl-followups` cron service in `render.yaml`. Daily rather
than fortnightly on purpose — the due window is a range, so a day missed to a
deploy or an outage is caught the next morning instead of skipping that founder
permanently.

Safe to run by hand at any time. `followup_sends` has a unique constraint on
(simulation_id, stage) and the row is claimed before the send, so a second run
sends nothing.

    python -m scripts.send_followups            # send
    python -m scripts.send_followups --dry-run  # count who is due, send nothing

Exits non-zero only when the job itself could not run — an unconfigured mail
service, or a failure reaching the database. **Individual send failures exit
zero**, because a bad address on one founder is not a reason for Render to mark
the whole job failed and page somebody; those land in the report and on the row.
"""
from __future__ import annotations

import asyncio
import sys

import structlog

from app.services.engine.followup import send_followups

logger = structlog.get_logger()


async def _main() -> int:
    dry_run = "--dry-run" in sys.argv
    report = await send_followups(dry_run=dry_run)

    logger.info(
        "followup_job_finished",
        dry_run=dry_run,
        considered=report.considered,
        sent=report.sent,
        already_asked=report.skipped_already_asked,
        failed=report.failed,
    )
    print(f"follow-ups: {report.sentence}{' (dry run)' if dry_run else ''}")
    for error in report.errors[:20]:
        print(f"  ! {error}")

    # The only fatal case: the job could not do its work at all.
    if report.errors and report.considered == 0 and report.sent == 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
