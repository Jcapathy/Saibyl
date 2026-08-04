"""The org-level persona pack library.

Mounted at `/api/packs`. Distinct from `/api/persona-packs`, which lists the 16
built-ins plus an org's LLM-generated custom packs and is the *picker*; this is
the founder's own curated shelf and the only place a promoted ICP pack lives.

Route order matters here. `POST /promote` is registered before `GET /{pack_id}`
and so on — `GET /simulations/founder-stages` behind `GET /simulations/{id}` and
`GET /markets/keys` behind `GET /markets/{market_id}` have both shipped in this
repo, and `tests/test_api_guards.py` now scans the whole app for the pattern.
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import get_current_org
from app.core.database import get_supabase_admin
from app.services.engine.personas import persona_store
from app.services.engine.personas.pack_loader import PackLookupError, PersonaPack

log = structlog.get_logger()

router = APIRouter(tags=["persona-pack-library"])


class PromoteBody(BaseModel):
    """Promote a compiled ICP pack into the org library.

    The pack is taken from `icp_profiles.pack_data` rather than supplied by the
    client: the client does not get to choose what it is promoting, and the row
    is already the validated, compiled artifact the engine runs.
    """

    icp_profile_id: str
    # Display name for the library entry. Defaults to the profile's own name.
    name: str | None = Field(default=None, max_length=200)


class RenameBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)


def _decorate(org_id: str, row: dict) -> dict:
    """Attach the staleness flag the ICP editor and library both need."""
    return persona_store.attach_staleness(org_id, [row])[0]


# ---------------------------------------------------------------------------
# Static routes first
# ---------------------------------------------------------------------------

@router.get("")
async def list_packs(auth: dict = Depends(get_current_org)):
    """The organization's promoted pack library, newest first."""
    log.info("list_org_packs", org_id=auth["org_id"])
    org_id = auth["org_id"]
    return persona_store.attach_staleness(org_id, persona_store.list_org_pack_rows(org_id))


@router.post("/promote", status_code=201)
async def promote(body: PromoteBody, auth: dict = Depends(get_current_org)):
    """Copy an ICP profile's compiled pack into the library.

    A **snapshot**, not a reference. Editing the source ICP afterwards recompiles
    that profile's own pack (`PATCH /api/icp/{id}`) and leaves this entry
    untouched, so a run configured against a library pack keeps the audience it
    was configured with. `source_stale` reports when the source has moved;
    re-posting here refreshes the snapshot in place, keeping the same pack id so
    nothing that already references it breaks.
    """
    org_id = auth["org_id"]
    admin = get_supabase_admin()
    profile = (
        admin.table("icp_profiles")
        .select("id, name, pack_data")
        .eq("id", body.icp_profile_id)
        .eq("organization_id", org_id)
        .execute()
    )
    if not profile.data:
        raise HTTPException(status_code=404, detail="ICP profile not found")

    row = profile.data[0]
    try:
        pack = PersonaPack.model_validate(row["pack_data"])
    except ValueError as exc:
        # The compiled pack in the row does not validate. That is a corrupt
        # profile, not a bad request — surfaced rather than promoted, because a
        # library entry the engine cannot parse is a run that silently omits an
        # audience.
        log.error("promote_pack_invalid", profile_id=body.icp_profile_id, error=str(exc))
        raise HTTPException(
            status_code=422,
            detail="This ICP profile's compiled pack is not valid; re-synthesize it.",
        ) from exc

    if body.name:
        pack = pack.model_copy(update={"name": body.name.strip()[:200]})
    elif row.get("name"):
        pack = pack.model_copy(update={"name": str(row["name"])[:200]})

    try:
        pack_id = persona_store.save_org_pack(
            org_id,
            pack,
            body.icp_profile_id,
            created_by=auth["user"]["id"],
        )
    except persona_store.PackIdConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PackLookupError as exc:
        raise HTTPException(status_code=503, detail="Pack library unavailable") from exc

    stored = persona_store.get_org_pack_row(org_id, pack_id)
    if stored is None:
        # The write reported success and the read-back found nothing. Never
        # return a pack id for a row that is not there — the founder would
        # configure a run against it.
        log.error("promoted_pack_not_readable", org_id=org_id, pack_id=pack_id)
        raise HTTPException(status_code=500, detail="Pack was written but could not be read back")
    return _decorate(org_id, stored)


# ---------------------------------------------------------------------------
# Parameterised routes
# ---------------------------------------------------------------------------

@router.get("/{pack_id}")
async def get_pack_entry(pack_id: str, auth: dict = Depends(get_current_org)):
    """One library pack, with its full body and its usage."""
    org_id = auth["org_id"]
    row = persona_store.get_org_pack_row(org_id, pack_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Persona pack not found")
    row = _decorate(org_id, row)
    row["simulation_ids"] = persona_store.simulation_ids_using_pack(org_id, pack_id)
    return row


@router.patch("/{pack_id}")
async def rename_pack(pack_id: str, body: RenameBody, auth: dict = Depends(get_current_org)):
    """Rename a library pack. The pack id is not changed — see the store.

    `simulations.persona_pack_ids` holds these slugs with no foreign key, so a
    renamed id would leave stored references pointing at nothing and
    `run_prepare_agents` reads a missing pack as "skip it".
    """
    log.info("rename_org_pack", org_id=auth["org_id"], pack_id=pack_id)
    row = persona_store.rename_org_pack(auth["org_id"], pack_id, body.name)
    if row is None:
        raise HTTPException(status_code=404, detail="Persona pack not found")
    stored = persona_store.get_org_pack_row(auth["org_id"], pack_id)
    return _decorate(auth["org_id"], stored) if stored else row


@router.delete("/{pack_id}")
async def delete_pack(pack_id: str, auth: dict = Depends(get_current_org)):
    """Delete a library pack.

    Simulations that used it keep their history: agents are materialised at
    prepare time, so a completed run holds its own agent rows and never re-reads
    the pack. This mirrors `api/icp.py:delete_profile`, with one difference worth
    returning to the caller — `persona_pack_ids` is a jsonb array of slugs with
    no foreign key, so there is no `ON DELETE SET NULL` recording the break. The
    affected simulation ids come back in the response instead.
    """
    org_id = auth["org_id"]
    affected = persona_store.simulation_ids_using_pack(org_id, pack_id)
    if not persona_store.delete_org_pack(org_id, pack_id):
        raise HTTPException(status_code=404, detail="Persona pack not found")
    log.info("org_pack_delete", org_id=org_id, pack_id=pack_id, affected=len(affected))
    return {
        "status": "deleted",
        "pack_id": pack_id,
        # Their reports and agents are intact; they can no longer be re-run
        # against this audience.
        "detached_simulation_ids": affected,
    }
