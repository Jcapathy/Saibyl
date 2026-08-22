# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# GET  /firms                       the bank, stale records withheld and named
# GET  /firms/{firm_id}             one firm; 409 when past its verification date
# POST /shortlist                   build one, charging credits
# GET  /shortlist/{shortlist_id}
# GET  /shortlist/by-project/{project_id}
# load_bank(*, now, ...) -> BankPage      the reader that enforces freshness
# ─────────────────────────────────────────────────────────
"""Access to capital, as an ordinary paid artifact.

Charging follows the rule every other paid surface in this codebase uses:
**charged at create, never at completion.** Deducting on success would let one
shortlist's worth of credits start ten concurrent builds. The route refuses
before it charges, in this order: the project must belong to this org, any run
named must belong to it too, the bank must actually hold a record that is still
current, and the balance must cover the price. Charging first and discovering
there is nothing to match against second is how a product takes money for an
empty document.

**The freshness rule is enforced by the reader, here.** `load_bank` is the only
way a firm record reaches a response, and it partitions on `stale_after` before
returning — so a decayed record is named as withheld and never rendered as
current. `GET /firms/{id}` answers 409 rather than 200 for the same reason: a
record we hold but will not stand behind is a different answer from a record we
do not have, and collapsing the two into a 404 would hide that we have it.

**This module reads and recommends. It does not send.** There is no outreach
path here and no contact export. The founder makes contact through the firm's
own published route, which is the only route this package stores. The moment
Saibyl sends on a founder's behalf, deliverability, consent and reputation
become Saibyl's — see `docs/CAPITAL_MODULE.md`, "What this is not".
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.auth import get_current_org, require_can_spend
from app.core.database import get_supabase_admin
from app.services.billing.agent_pricing import (
    capital_shortlist_credits,
    deduct_credits,
    get_credit_balance,
)
from app.services.capital.matching import (
    FounderContext,
    MeasuredObjection,
    build_shortlist,
    normalise_key,
    partition_by_freshness,
)
from app.services.capital.schema import FamilyOffice, StaleRecord

log = structlog.get_logger()

router = APIRouter(tags=["capital"])

# The bank is curated, not crawled — fifty well-evidenced firms beats five
# thousand thin ones, and that is the founder's decision on record. At that size
# the sector and stage filters run in Python after the read rather than as
# PostgREST array operators, which keeps one implementation of the stage-key
# normalisation (`pre-seed` == `pre seed` == `preseed`) instead of two that can
# disagree. Revisit when the bank outgrows a single page, not before.
MAX_BANK_ROWS = 500

# How many objections the match reads, most load-bearing first. The tail past
# this is single-agent noise; the bridge only ever uses the strongest one that
# actually bridges.
MAX_OBJECTIONS = 10

GENERIC_FAILURE_MESSAGE = (
    "We could not build your shortlist. Nothing was matched and the run has "
    "been marked failed."
)


class BankPage(BaseModel):
    """What the reader returns: what may be asserted, and what was held back."""

    firms: list[FamilyOffice] = Field(default_factory=list)
    withheld_stale: list[StaleRecord] = Field(default_factory=list)
    # Rows that no longer satisfy the schema — a personal detail that reached
    # the table through some path this package does not own, a record whose
    # source_url was cleared. Counted and logged, never served.
    unreadable: int = 0
    as_of: datetime


def _parse(row: dict[str, Any]) -> FamilyOffice | None:
    """One stored row as a record, or None.

    **The gate runs on read as well as on write.** A row is validated by the
    same model that refused to write an unlawful one, so a record that reached
    the table another way — a manual `INSERT`, a restored backup, a future
    ingestion path — still cannot be served with a personal detail in it. A
    reader that trusts its own table is a reader that serves whatever got past
    the writer.
    """
    try:
        return FamilyOffice.model_validate(row)
    except ValueError as exc:
        log.error("capital_firm_row_unreadable", firm_id=row.get("id"), error=str(exc))
        return None


def load_bank(
    *,
    now: datetime,
    sector: str | None = None,
    stage: str | None = None,
    firm_type: str | None = None,
    limit: int = MAX_BANK_ROWS,
) -> BankPage:
    """Read the bank, withholding anything past its verification date."""
    admin = get_supabase_admin()
    query = admin.table("family_offices").select("*")
    if firm_type:
        query = query.eq("firm_type", firm_type)
    rows = (query.order("firm_name").limit(limit).execute()).data or []

    parsed: list[FamilyOffice] = []
    unreadable = 0
    for row in rows:
        firm = _parse(row)
        if firm is None:
            unreadable += 1
            continue
        if sector and not any(
            normalise_key(sector) in normalise_key(s)
            or normalise_key(s) in normalise_key(sector)
            for s in firm.sectors
        ):
            continue
        if stage and firm.stages and normalise_key(stage) not in {
            normalise_key(s) for s in firm.stages
        }:
            # Kept out of the *list* view, but never out of a shortlist: the
            # shortlist reports it as a refusal instead, which is the whole
            # point of the refusal path. A caller building a shortlist passes
            # no stage filter here for exactly that reason.
            continue
        parsed.append(firm)

    fresh, withheld = partition_by_freshness(parsed, now)
    return BankPage(firms=fresh, withheld_stale=withheld, unreadable=unreadable, as_of=now)


@router.get("/firms")
async def list_firms(
    sector: str | None = Query(default=None),
    stage: str | None = Query(default=None),
    firm_type: str | None = Query(default=None),
    auth: dict = Depends(get_current_org),
) -> BankPage:
    """The bank as it stands right now, with every record's retrieval date.

    `withheld_stale` is part of the answer, not an error channel. A founder who
    is told "we hold four more records and they are past their verification
    date" can go and check them; a founder handed a shorter list learns nothing
    and reads the shorter list as the whole market.
    """
    page = load_bank(
        now=datetime.now(UTC), sector=sector, stage=stage, firm_type=firm_type
    )
    log.info(
        "capital_bank_listed",
        org_id=auth["org_id"],
        firms=len(page.firms),
        withheld_stale=len(page.withheld_stale),
        unreadable=page.unreadable,
    )
    return page


@router.get("/firms/{firm_id}")
async def get_firm(firm_id: str, auth: dict = Depends(get_current_org)) -> FamilyOffice:
    """One firm, or an explicit refusal to stand behind a decayed record."""
    admin = get_supabase_admin()
    result = (
        admin.table("family_offices").select("*").eq("id", firm_id).execute()
    )
    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="We do not have a record for that firm.")

    firm = _parse(rows[0])
    if firm is None:
        # Loud, and not a 404: the row exists and cannot be served, which is a
        # data-integrity fault somebody has to see rather than a missing record.
        raise HTTPException(
            status_code=409,
            detail="That record cannot be shown. It has been flagged for review.",
        )

    now = datetime.now(UTC)
    if firm.is_stale(now):
        raise HTTPException(
            status_code=409,
            detail=(
                f"We hold a record for {firm.firm_name}, but it was retrieved on "
                f"{firm.retrieved_at.date().isoformat()} and passed its "
                f"verification date on {firm.stale_after.date().isoformat()}. We "
                f"will not show it as current. Check the firm's own page until "
                f"it is re-verified."
            ),
        )
    return firm


class ShortlistBody(BaseModel):
    project_id: str
    sector: str
    stage: str
    check_size_needed: int | None = None
    geography: str | None = None
    # The founder's own words. Ignored when `simulation_id` names a run whose
    # ICP already holds a product summary — measured beats supplied.
    material: str = ""
    # The run whose measured objections build the objection bridge. Optional:
    # a founder can get a sector-and-stage shortlist before they have run a
    # room, and the notes say what the shortlist was missing.
    simulation_id: str | None = None


def _load_objections(simulation_id: str, org_id: str) -> list[MeasuredObjection]:
    admin = get_supabase_admin()
    rows = (
        admin.table("canonical_objections")
        .select("objection_key, label, quotes, load_bearing_score")
        .eq("simulation_id", simulation_id)
        .eq("organization_id", org_id)
        .order("load_bearing_score", desc=True)
        .limit(MAX_OBJECTIONS)
        .execute()
    ).data or []

    objections: list[MeasuredObjection] = []
    for row in rows:
        raw = row.get("quotes") or []
        quote = ""
        if isinstance(raw, list) and raw:
            first = raw[0]
            quote = str(first.get("text") if isinstance(first, dict) else first or "")
        try:
            objections.append(MeasuredObjection(
                objection_key=str(row.get("objection_key") or ""),
                label=str(row.get("label") or ""),
                quote=quote.strip(),
                load_bearing_score=float(row.get("load_bearing_score") or 0.0),
            ))
        except ValueError as exc:
            # A buyer quote carrying a personal detail is dropped rather than
            # quoted into a stored shortlist. The objection is still measured;
            # it just cannot be used as a bridge, which is the safe direction.
            log.info("capital_objection_dropped", error=str(exc))
    return objections


def _product_summary(simulation_id: str, org_id: str) -> str:
    admin = get_supabase_admin()
    sim = (
        admin.table("simulations")
        .select("icp_profile_id")
        .eq("id", simulation_id)
        .eq("organization_id", org_id)
        .single()
        .execute()
    ).data or {}
    if not sim.get("icp_profile_id"):
        return ""
    icp = (
        admin.table("icp_profiles")
        .select("product_summary")
        .eq("id", sim["icp_profile_id"])
        .single()
        .execute()
    ).data or {}
    return str(icp.get("product_summary") or "")


@router.post("/shortlist")
async def create_shortlist(body: ShortlistBody, auth: dict = Depends(require_can_spend)):
    """Build the shortlist for one product, charging at create."""
    admin = get_supabase_admin()
    org_id = auth["org_id"]

    project = (
        admin.table("projects")
        .select("id, name")
        .eq("id", body.project_id)
        .eq("organization_id", org_id)
        .single()
        .execute()
    )
    if not project.data:
        raise HTTPException(status_code=404, detail="We could not find that project.")

    material = body.material
    objections: list[MeasuredObjection] = []
    if body.simulation_id:
        sim = (
            admin.table("simulations")
            .select("id")
            .eq("id", body.simulation_id)
            .eq("organization_id", org_id)
            .single()
            .execute()
        )
        if not sim.data:
            raise HTTPException(status_code=404, detail="We could not find that run.")
        objections = _load_objections(body.simulation_id, org_id)
        material = _product_summary(body.simulation_id, org_id) or material

    try:
        context = FounderContext(
            product_name=str(project.data.get("name") or ""),
            sector=body.sector,
            stage=body.stage,
            material=material,
            check_size_needed=body.check_size_needed,
            geography=body.geography,
            objections=objections,
        )
    except ValueError as exc:
        # Refused whole rather than trimmed, for `privacy.py`'s reason: the
        # sentences in `material` are copied into a stored shortlist, so an
        # address in a pasted footer would become an address in our database.
        raise HTTPException(
            status_code=422,
            detail=(
                "Your product description contains an email address or phone "
                "number. Saibyl does not store personal contact details, so "
                "please remove it and try again."
            ),
        ) from exc

    now = datetime.now(UTC)
    # No stage filter: a firm that does not invest at this stage must reach the
    # matcher so it can be reported as a refusal instead of vanishing.
    bank = load_bank(now=now, sector=None, stage=None)
    if not bank.firms:
        raise HTTPException(
            status_code=409,
            detail=(
                "There is no current family-office record to match against. "
                f"{len(bank.withheld_stale)} record(s) are past their "
                f"verification date and we will not match against those."
            ),
        )

    credits = capital_shortlist_credits()
    balance, _granted, _plan = get_credit_balance(org_id)
    if balance < credits:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Not enough credits. Building your shortlist needs {credits:,}; "
                f"you have {balance:,}."
            ),
        )

    deduct_credits(org_id, credits)

    row = (
        admin.table("capital_shortlists")
        .insert({
            "project_id": body.project_id,
            "organization_id": org_id,
            "simulation_id": body.simulation_id,
            "status": "building",
            "sector": body.sector,
            "stage": body.stage,
            "check_size_needed": body.check_size_needed,
            "credits_charged": credits,
            "as_of": now.isoformat(),
            "created_at": now.isoformat(),
        })
        .execute()
    ).data[0]

    try:
        shortlist = build_shortlist(context, bank.firms, now=now)
    except Exception as exc:
        # The row carries `credits_charged`, so a charge with no artifact is
        # reconcilable rather than invisible. The founder sees a sentence, not
        # a spinner with no ending.
        log.error("capital_shortlist_failed", shortlist_id=row["id"], error=str(exc))
        admin.table("capital_shortlists").update({
            "status": "failed",
            "error_message": GENERIC_FAILURE_MESSAGE,
        }).eq("id", row["id"]).execute()
        raise HTTPException(status_code=500, detail=GENERIC_FAILURE_MESSAGE) from exc

    payload = shortlist.model_dump(mode="json")
    completed = (
        admin.table("capital_shortlists")
        .update({
            "status": "complete",
            "matches": payload["matches"],
            "refusals": payload["refusals"],
            "withheld_stale": payload["withheld_stale"],
            "notes": payload["notes"],
            "firms_considered": shortlist.considered,
            "matches_count": len(shortlist.matches),
            "refusals_count": len(shortlist.refusals),
            "completed_at": datetime.now(UTC).isoformat(),
        })
        .eq("id", row["id"])
        .eq("organization_id", org_id)
        .execute()
    )
    log.info(
        "capital_shortlist_created",
        shortlist_id=row["id"],
        org_id=org_id,
        project_id=body.project_id,
        matches=len(shortlist.matches),
        refusals=len(shortlist.refusals),
        withheld_stale=len(shortlist.withheld_stale),
        credits=credits,
    )
    return (completed.data or [row])[0]


@router.get("/shortlist/by-project/{project_id}")
async def shortlist_for_project(project_id: str, auth: dict = Depends(get_current_org)):
    """The newest shortlist for this project, or 404."""
    admin = get_supabase_admin()
    result = (
        admin.table("capital_shortlists")
        .select("*")
        .eq("project_id", project_id)
        .eq("organization_id", auth["org_id"])
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=404, detail="No shortlist has been built for this project."
        )
    return result.data[0]


@router.get("/shortlist/{shortlist_id}")
async def get_shortlist(shortlist_id: str, auth: dict = Depends(get_current_org)):
    admin = get_supabase_admin()
    result = (
        admin.table("capital_shortlists")
        .select("*")
        .eq("id", shortlist_id)
        .eq("organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="We could not find that shortlist.")
    return result.data
