# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# create_run(...) -> dict            finish_run(run_id, status, **fields) -> dict
# get_run(run_id, org_id) -> dict    list_runs(org_id, ...) -> (items, total)
# insert_candidates(run, candidates) -> int
# list_candidates(org_id, ...) -> (items, total)
# get_candidate(candidate_id, org_id) -> dict | None
# delete_candidate(candidate_id, org_id) -> dict | None
# purge_organization(org_id) -> dict
# ─────────────────────────────────────────────────────────
"""Every read and write for go-to-market discovery. Migration 027.

All database access for this feature lives here so that the deletion path is
one function rather than a habit. `delete_candidate` and `purge_organization`
issue `DELETE`; there is no `deleted_at` column on `gtm_candidates` or
`gtm_contacts` to set, which is the only reliable way to keep a soft delete
from being introduced later "for undo". A person exercising an erasure right is
not asking to be hidden.

`gtm_discovery_runs` survives a purge, stamped with `purged_at`. It holds
queries, counts and spend — no personal data — and it is the billing record
that reconciles against `llm_usage`. Deleting it to satisfy a data request
would destroy the audit trail for money without removing anything about a
person.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog

from app.core.database import get_supabase_admin
from app.services.gtm.schema import Candidate, DiscoveryQuery

log = structlog.get_logger()

RUN_STATUSES = ("running", "completed", "partial", "failed")

# Candidate columns a list view needs. Evidence and contacts are deliberately
# excluded: a 200-row list carrying every quote and every named person is both
# slow and a needless exposure of personal data to a screen that does not show
# it. `get_candidate` returns them.
_LIST_COLUMNS = (
    "id,discovery_run_id,project_id,company_name,domain,one_liner,"
    "employee_count_range,industry,hq_location,incumbent_tooling,"
    "archetype_id,archetype_label,angle,match_score,source_url,source_title,"
    "retrieved_at,contact_count,created_at"
)


def create_run(
    *,
    project_id: str,
    org_id: str,
    icp_profile_id: str | None,
    queries: list[DiscoveryQuery],
    contacts_enabled: bool,
    credits_charged: int,
    estimated_cost_usd: float,
    created_by: str | None,
) -> dict[str, Any]:
    """Open a discovery run. Credits are already charged by the caller."""
    admin = get_supabase_admin()
    row = {
        "project_id": project_id,
        "organization_id": org_id,
        "icp_profile_id": icp_profile_id,
        "status": "running",
        "queries": [q.model_dump(mode="json") for q in queries],
        "query_count": len(queries),
        "contacts_enabled": contacts_enabled,
        "credits_charged": credits_charged,
        "estimated_cost_usd": estimated_cost_usd,
        "created_by": created_by,
    }
    inserted = admin.table("gtm_discovery_runs").insert(row).execute()
    if not inserted.data:
        raise RuntimeError("failed to create gtm_discovery_runs row")
    return inserted.data[0]


def finish_run(run_id: str, status: str, **fields: Any) -> dict[str, Any]:
    """Close a run with a terminal status and its measured counters."""
    if status not in RUN_STATUSES:
        raise ValueError(f"unknown discovery run status: {status}")
    admin = get_supabase_admin()
    payload = {"status": status, "completed_at": datetime.now(UTC).isoformat(), **fields}
    updated = admin.table("gtm_discovery_runs").update(payload).eq("id", run_id).execute()
    if not updated.data:
        # The run existed when it was created; zero rows means it was deleted
        # mid-flight. Loud, because a run that finished and cannot record that
        # it finished stays "running" forever to every reader.
        log.error("gtm_run_finish_no_row", run_id=run_id, status=status)
        return {}
    return updated.data[0]


def get_run(run_id: str, org_id: str) -> dict[str, Any] | None:
    admin = get_supabase_admin()
    result = (
        admin.table("gtm_discovery_runs")
        .select("*")
        .eq("id", run_id)
        .eq("organization_id", org_id)
        .execute()
    )
    return (result.data or [None])[0]


def list_runs(
    org_id: str,
    *,
    project_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    admin = get_supabase_admin()
    query = (
        admin.table("gtm_discovery_runs")
        .select("*", count="exact")
        .eq("organization_id", org_id)
    )
    if project_id:
        query = query.eq("project_id", project_id)
    result = (
        query.order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return result.data or [], int(result.count or 0)


def insert_candidates(run: dict[str, Any], candidates: list[Candidate]) -> int:
    """Persist a batch of verified candidates and their contacts.

    Written per query as each query completes rather than once at the end, so a
    discovery that is cut short keeps what it had already found. That is what
    makes `partial` a real outcome instead of a label on an empty list.
    """
    if not candidates:
        return 0

    admin = get_supabase_admin()

    # Ids are minted here rather than read back off the insert. Pairing
    # contacts to candidates by the order PostgREST happens to return would be
    # an assumption about a component's behaviour that nothing checks — and the
    # failure mode is a named person filed against the wrong company, which is
    # both a data-protection problem and invisible until somebody notices the
    # name does not belong there.
    ids = [str(uuid4()) for _ in candidates]

    rows = [{
        "id": candidate_id,
        "discovery_run_id": run["id"],
        "project_id": run["project_id"],
        "organization_id": run["organization_id"],
        "company_name": c.company_name,
        "domain": c.domain,
        "one_liner": c.one_liner,
        "employee_count_range": c.employee_count_range,
        "industry": c.industry,
        "hq_location": c.hq_location,
        "incumbent_tooling": c.incumbent_tooling,
        "archetype_id": c.archetype_id,
        "archetype_label": c.archetype_label,
        "angle": c.angle,
        "query": c.query,
        "match_reasons": c.match_reasons,
        "match_score": c.match_score,
        "score_components": c.score_components,
        "source_url": c.source_url,
        "source_title": c.source_title,
        "retrieved_at": c.retrieved_at.isoformat(),
        "evidence": [item.model_dump(mode="json") for item in c.evidence],
        "contact_count": len(c.contacts),
    } for candidate_id, c in zip(ids, candidates, strict=True)]

    inserted = admin.table("gtm_candidates").insert(rows).execute()
    stored = inserted.data or []
    if len(stored) != len(candidates):
        log.error(
            "gtm_candidate_insert_short",
            expected=len(candidates),
            inserted=len(stored),
            run_id=run["id"],
        )

    contact_rows: list[dict[str, Any]] = []
    for candidate_id, candidate in zip(ids, candidates, strict=True):
        for contact in candidate.contacts:
            contact_rows.append({
                "candidate_id": candidate_id,
                "organization_id": run["organization_id"],
                "full_name": contact.full_name,
                "role_title": contact.role_title,
                "employer": contact.employer,
                "public_profile_url": contact.public_profile_url,
                "source_url": contact.source_url,
                "retrieved_at": contact.retrieved_at.isoformat(),
            })
    if contact_rows:
        admin.table("gtm_contacts").insert(contact_rows).execute()

    return len(stored)


def list_candidates(
    org_id: str,
    *,
    project_id: str | None = None,
    discovery_run_id: str | None = None,
    archetype_id: str | None = None,
    min_score: float | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Filtered, paged candidates. Returns (items, total).

    `total` is the count *before* paging, which is what makes page 2 reachable.
    `GET /simulations` returning a bare array meant a user with 50 rows could
    never get past the first page, and that is the defect this signature exists
    to not repeat.
    """
    admin = get_supabase_admin()
    query = (
        admin.table("gtm_candidates")
        .select(_LIST_COLUMNS, count="exact")
        .eq("organization_id", org_id)
    )
    if project_id:
        query = query.eq("project_id", project_id)
    if discovery_run_id:
        query = query.eq("discovery_run_id", discovery_run_id)
    if archetype_id:
        query = query.eq("archetype_id", archetype_id)
    if min_score is not None:
        query = query.gte("match_score", min_score)
    if search:
        # PostgREST `ilike` needs its own wildcards, and a comma inside the
        # pattern would be read as a filter separator.
        cleaned = search.replace(",", " ").replace("*", "").strip()
        if cleaned:
            query = query.ilike("company_name", f"%{cleaned}%")

    result = (
        query.order("match_score", desc=True)
        .order("company_name")
        .range(offset, offset + limit - 1)
        .execute()
    )
    return result.data or [], int(result.count or 0)


def get_candidate(candidate_id: str, org_id: str) -> dict[str, Any] | None:
    """One candidate with its evidence and any contacts."""
    admin = get_supabase_admin()
    result = (
        admin.table("gtm_candidates")
        .select("*")
        .eq("id", candidate_id)
        .eq("organization_id", org_id)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return None

    candidate = dict(rows[0])
    contacts = (
        admin.table("gtm_contacts")
        .select("*")
        .eq("candidate_id", candidate_id)
        .eq("organization_id", org_id)
        .order("full_name")
        .execute()
    )
    candidate["contacts"] = contacts.data or []
    return candidate


def delete_candidate(candidate_id: str, org_id: str) -> dict[str, Any] | None:
    """Delete one candidate and every contact attached to it.

    Rows, not flags. Returns what was removed so the caller can state it, or
    None when nothing matched — which is a 404 at the API, not a silent success.
    """
    admin = get_supabase_admin()
    existing = (
        admin.table("gtm_candidates")
        .select("id,company_name,contact_count")
        .eq("id", candidate_id)
        .eq("organization_id", org_id)
        .execute()
    )
    rows = existing.data or []
    if not rows:
        return None

    # Deleted explicitly as well as by the ON DELETE CASCADE, so the count is
    # measured rather than assumed and so this path does not depend on a
    # constraint continuing to exist.
    contacts = (
        admin.table("gtm_contacts")
        .delete(count="exact")
        .eq("candidate_id", candidate_id)
        .eq("organization_id", org_id)
        .execute()
    )
    admin.table("gtm_candidates").delete().eq("id", candidate_id).eq(
        "organization_id", org_id
    ).execute()

    removed = {
        "id": candidate_id,
        "company_name": rows[0].get("company_name"),
        "contacts_deleted": int(contacts.count or 0),
    }
    log.info("gtm_candidate_deleted", org_id=org_id, **removed)
    return removed


def purge_organization(org_id: str) -> dict[str, int]:
    """Delete every candidate and contact this org holds.

    The answer to "delete everything you have compiled about people for us".
    Discovery runs survive, stamped `purged_at`: they carry queries, counts and
    spend, which is the billing record that reconciles against `llm_usage`, and
    none of it is personal data.
    """
    admin = get_supabase_admin()
    contacts = (
        admin.table("gtm_contacts")
        .delete(count="exact")
        .eq("organization_id", org_id)
        .execute()
    )
    candidates = (
        admin.table("gtm_candidates")
        .delete(count="exact")
        .eq("organization_id", org_id)
        .execute()
    )
    admin.table("gtm_discovery_runs").update(
        {"purged_at": datetime.now(UTC).isoformat()}
    ).eq("organization_id", org_id).is_("purged_at", "null").execute()

    result = {
        "candidates_deleted": int(candidates.count or 0),
        "contacts_deleted": int(contacts.count or 0),
    }
    log.info("gtm_organization_purged", org_id=org_id, **result)
    return result
