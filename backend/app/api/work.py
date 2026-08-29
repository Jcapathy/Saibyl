# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# GET /work        -> {"items": [WorkItem, ...]}
# WorkItem, SOURCES
# ─────────────────────────────────────────────────────────
"""Everything a founder has made, in one list.

**The gap this closes.** Every module stores its output durably and with a
timestamp, and none of it was findable in one place. The founder who raised it
had eight artifacts — four website checks, three gallery entries, one page
rewrite — and the Reports section showed **zero**, because `reports` is written
only by simulation runs and the route is literally
`/app/simulations/:id/report`. A report was a child of a run, not a record of
work.

So the rows existed; they were addressed by *where you were standing* rather
than by *what you made*. Close the tab and the only way back to a check was
remembering which stage page produced it.

**Read-only over what already exists.** No new table, no migration, no change to
how anything is produced. Every source below is queried by
`organization_id`, newest first, and the shape they share —
`id, organization_id, project_id, status, created_at, credits_charged` — is why
this is a union rather than a rewrite.

**Two things are deliberately NOT here:**

- `design_gallery` — the platform's own byproduct of a website check, not
  something the founder asked for. `website_tasks` says so in its own words:
  "the critique is the deliverable and the gallery is the platform's own
  byproduct". Listing it as work would inflate the list with things nobody made.
- `subject_briefs` — an internal stage artifact with no price and no viewer.

**Every item carries an `href` that actually opens it.** A list you cannot act
on is a worse answer than no list: it tells the founder the thing exists and
still makes them hunt for it. Where a module has no page of its own — a website
check renders inside the audience stage — the link carries the id as a query
parameter and the page opens it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog
from fastapi import APIRouter, Depends

from app.core.auth import get_current_org
from app.core.database import get_supabase_admin

logger = structlog.get_logger()

router = APIRouter(tags=["work"])

#: How many artifacts one response carries. A founder with a long history gets
#: the newest; paging is a later problem and an unbounded query is not.
LIMIT_PER_SOURCE = 100


@dataclass(frozen=True)
class SourceSpec:
    """One artifact table, and how to read a founder-facing row out of it."""

    table: str
    kind: str
    #: What the founder calls this thing. Never the table name.
    label: str
    #: Columns to select. Kept explicit so a schema change surfaces here rather
    #: than silently widening the payload.
    columns: str
    #: Builds (title, href) from a row.
    render: Any


def _run(row: dict) -> tuple[str, str]:
    name = row.get("name") or "Untitled run"
    return name, f"/app/simulations/{row['id']}/report"


def _check(row: dict) -> tuple[str, str]:
    url = row.get("url") or "a page"
    # The check has no page of its own; it renders inside the audience stage.
    # The id rides as `?check=` and `AudienceStagePage` opens it.
    project = row.get("project_id")
    return url, f"/app/products/{project}/audience?check={row['id']}"


def _revision(row: dict) -> tuple[str, str]:
    project = row.get("project_id")
    snapshot = row.get("snapshot_id")
    return (
        "Rewrite of a checked page",
        f"/app/products/{project}/audience?check={snapshot}",
    )


def _clearance(row: dict) -> tuple[str, str]:
    tier = (row.get("tier") or "").title() or "Clearance"
    return f"{tier} clearance search", "/app/validate"


def _discovery(row: dict) -> tuple[str, str]:
    return "Buyer discovery", "/app/prospects"


SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        table="simulations",
        kind="run",
        label="Run",
        columns="id, project_id, name, status, created_at, completed_at",
        render=_run,
    ),
    SourceSpec(
        table="website_snapshots",
        kind="website_check",
        label="Website check",
        columns="id, project_id, url, status, created_at, completed_at, credits_charged",
        render=_check,
    ),
    SourceSpec(
        table="page_revisions",
        kind="page_revision",
        label="Page rewrite",
        columns=(
            "id, project_id, snapshot_id, status, created_at, completed_at, "
            "credits_charged"
        ),
        render=_revision,
    ),
    SourceSpec(
        table="clearance_runs",
        kind="clearance",
        label="Patent and trademark search",
        columns="id, project_id, tier, status, created_at, completed_at, credits_charged",
        render=_clearance,
    ),
    SourceSpec(
        table="gtm_discovery_runs",
        kind="discovery",
        label="Buyer discovery",
        columns="id, project_id, status, created_at, completed_at, credits_charged",
        render=_discovery,
    ),
)


@router.get("")
async def list_work(auth: dict = Depends(get_current_org)) -> dict:
    """Every artifact this organisation has produced, newest first.

    A source that fails is **logged and skipped**, not fatal. One unreadable
    table must not empty the whole list — a founder looking for last week's
    check should still find it when an unrelated module is having a bad day.
    """
    admin = get_supabase_admin()
    org_id = str(auth["org"]["id"])
    items: list[dict] = []

    for source in SOURCES:
        try:
            rows = (
                admin.table(source.table)
                .select(source.columns)
                .eq("organization_id", org_id)
                .order("created_at", desc=True)
                .limit(LIMIT_PER_SOURCE)
                .execute()
                .data
            ) or []
        except Exception:
            logger.warning("work_source_failed", table=source.table, exc_info=True)
            continue

        for row in rows:
            title, href = source.render(row)
            items.append({
                "id": str(row["id"]),
                "kind": source.kind,
                "label": source.label,
                "title": title,
                "href": href,
                "status": row.get("status"),
                "created_at": row.get("created_at"),
                "completed_at": row.get("completed_at"),
                "credits": row.get("credits_charged"),
                "project_id": row.get("project_id"),
            })

    # Sorted here rather than per source: the point of the list is one
    # chronology across every kind of work, which no single query can give.
    items.sort(key=lambda i: i.get("created_at") or "", reverse=True)

    logger.info("work_listed", organization_id=org_id, items=len(items))
    return {"items": items}
