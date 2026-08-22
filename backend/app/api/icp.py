from __future__ import annotations

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.auth import get_current_org, require_can_destroy, require_can_spend
from app.core.database import get_supabase_admin
from app.services.engine.personas.icp_schema import ICPProfile

log = structlog.get_logger()

router = APIRouter(tags=["icp"])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class SynthesizeBody(BaseModel):
    project_id: str
    # Platforms the run will simulate. Used to route archetypes to the places
    # they actually argue about tools, so an ICP synthesized for a LinkedIn run
    # does not put every buyer on Hacker News.
    platforms: list[str] = Field(default_factory=list)
    # Whether to include the incumbent-aligned cohort at all (PRD §4).
    adversarial: bool = True
    # Share of the swarm that cohort takes. The ceiling is 0.5 and is enforced
    # in the database as well: past half the swarm the headline valence becomes
    # a function of the share the user chose, and it will still read as a
    # measurement of the market.
    adversarial_share: float = Field(default=0.0, ge=0.0, le=0.5)
    name: str | None = None


class UpdateProfileBody(BaseModel):
    """A founder's correction to a synthesized ICP.

    Synthesis proposes and the founder disposes (DECISIONS §3), so the whole
    profile is replaceable. It is re-validated against `ICPProfile` and
    recompiled into a pack on write — a profile the engine cannot compile is
    rejected here rather than at the start of a paid run.
    """

    profile: dict
    name: str | None = None
    platforms: list[str] = Field(default_factory=list)
    adversarial_share: float = Field(default=0.0, ge=0.0, le=0.5)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _verify_project(project_id: str, org_id: str) -> None:
    admin = get_supabase_admin()
    project = (
        admin.table("projects")
        .select("id")
        .eq("id", project_id)
        .eq("organization_id", org_id)
        .execute()
    )
    if not project.data:
        raise HTTPException(status_code=404, detail="Project not found")


def _fetch_profile(profile_id: str, org_id: str) -> dict:
    admin = get_supabase_admin()
    row = (
        admin.table("icp_profiles")
        .select("*")
        .eq("id", profile_id)
        .eq("organization_id", org_id)
        .execute()
    )
    if not row.data:
        raise HTTPException(status_code=404, detail="ICP profile not found")
    return row.data[0]


def _with_promotions(row: dict, org_id: str) -> dict:
    """Attach the library packs promoted out of this profile.

    A promoted pack is a **snapshot** (`persona_packs`, migration 026). Editing
    the profile recompiles this row's own `pack_data` — the pack `get_pack`
    serves for the `icp_` prefix — and deliberately does not touch the library
    entries: a run configured last month against a library pack must not change
    audience because a job title was corrected today, which is the same
    reproducibility guarantee `icp_profiles.pack_data` exists to give.

    That decision is only honest if the drift is visible, so each entry carries
    `source_stale`. Re-promoting (`POST /api/packs/promote`) refreshes the
    snapshot in place and keeps its pack id. Without this, the founder would have
    no way to tell that the pack in their library no longer matches the ICP they
    just edited — a divergence with no error attached to it.
    """
    from app.services.engine.personas import persona_store

    row = dict(row)
    row["promoted_packs"] = persona_store.promotions_of_profile(org_id, row["id"])
    return row


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/synthesize")
async def synthesize(body: SynthesizeBody, auth: dict = Depends(require_can_spend)):
    """Derive an ICP from the project's uploaded material.

    Runs inline rather than as a background task. It is a single main-model call
    of a few seconds, the founder is waiting on the result to start configuring
    a run, and every background job in this codebase is still an
    `asyncio.create_task` with no durability — so detaching this would trade a
    short wait for a class of silent failure.
    """
    from app.services.billing.agent_pricing import check_synthesis_budget, deduct_credits
    from app.services.engine.personas.icp_synthesizer import synthesize_icp

    log.info(
        "icp_synthesize",
        project_id=body.project_id,
        org_id=auth["org_id"],
        adversarial=body.adversarial,
    )
    _verify_project(body.project_id, auth["org_id"])

    # Charged before the call, like a run: the compute is spent whether or not
    # the result is kept, and a synthesis that fails after the model has already
    # been paid for is still a synthesis the org consumed.
    budget = check_synthesis_budget(auth["org_id"])
    if not budget.allowed:
        raise HTTPException(status_code=402, detail=budget.message)

    try:
        row = await synthesize_icp(
            body.project_id,
            auth["org_id"],
            adversarial=body.adversarial,
            platforms=body.platforms,
            adversarial_share=body.adversarial_share,
            created_by=auth["user"]["id"],
            name=body.name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    deduct_credits(auth["org_id"], budget.credits_required)
    return row


@router.get("")
async def list_profiles(
    project_id: str = Query(...),
    auth: dict = Depends(get_current_org),
):
    """List ICP profiles for a project, newest first."""
    log.info("list_icp_profiles", project_id=project_id, org_id=auth["org_id"])
    admin = get_supabase_admin()
    result = (
        admin.table("icp_profiles")
        .select("*")
        .eq("project_id", project_id)
        .eq("organization_id", auth["org_id"])
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


@router.get("/estimate")
async def estimate(auth: dict = Depends(get_current_org)):
    """What one synthesis costs, before committing to it."""
    from app.services.billing.agent_pricing import check_synthesis_budget

    return check_synthesis_budget(auth["org_id"]).model_dump()


@router.get("/{id}")
async def get_profile(id: str, auth: dict = Depends(get_current_org)):
    """Get one ICP profile, with any library packs promoted out of it."""
    log.info("get_icp_profile", profile_id=id)
    return _with_promotions(_fetch_profile(id, auth["org_id"]), auth["org_id"])


@router.patch("/{id}")
async def update_profile(
    id: str,
    body: UpdateProfileBody,
    auth: dict = Depends(get_current_org),
):
    """Replace a synthesized profile with the founder's corrected version.

    "Synthesis proposes, the founder disposes" (DECISIONS §3) is this endpoint.

    The pack is recompiled here, on write. Recompiling on read would make a
    re-simulation's audience depend on when the pack was read, and the
    inoculation loop's entire claim is that the audience did not change between
    the two runs.

    **What an edit does not do is change a promoted library pack.** Those are
    snapshots taken at promotion time and are left alone; the response carries
    `promoted_packs`, each with `source_stale`, so the founder is told which of
    their library entries no longer match and can re-promote deliberately. The
    alternative — cascading the recompile into the library — would silently
    change the audience of every future run configured against those packs.
    """
    from app.services.engine.personas.icp_synthesizer import compile_pack

    log.info("update_icp_profile", profile_id=id, org_id=auth["org_id"])
    existing = _fetch_profile(id, auth["org_id"])

    try:
        profile = ICPProfile.model_validate(body.profile)
    except ValueError as exc:
        # Includes the adversarial grounding rule: an edit that names a
        # competitor with no source document is rejected the same way a
        # synthesis that did would have been.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if body.name:
        profile.name = body.name[:120]

    pack = compile_pack(
        profile,
        existing["pack_id"],
        body.platforms,
        body.adversarial_share,
    )

    admin = get_supabase_admin()
    updated = (
        admin.table("icp_profiles")
        .update({
            "name": profile.name,
            "product_summary": profile.product_summary,
            "profile": profile.model_dump(mode="json"),
            "pack_data": pack.model_dump(mode="json"),
            "competitors": [c.model_dump(mode="json") for c in profile.competitors],
            "edited_by_user": True,
            # Saving an edit is a stronger confirmation than pressing confirm:
            # the founder read it, disagreed with part of it, and said what it
            # should be instead. See the confirm endpoint for why agreement and
            # silence had to stop sharing one column.
            "confirmed_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        })
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
        .execute()
    )
    if not updated.data:
        # `_fetch_profile` above found it, so zero updated rows means it was
        # deleted between the two statements. `updated.data[0]` would have been
        # an IndexError and a 500 on what is a plain 404.
        raise HTTPException(status_code=404, detail="ICP profile not found")
    return _with_promotions(updated.data[0], auth["org_id"])


@router.post("/{id}/confirm")
async def confirm_profile(id: str, auth: dict = Depends(get_current_org)):
    """Record that the founder read this audience and agreed with it.

    Why this is not `edited_by_user`. DECISIONS §3 settled that synthesis
    proposes and the founder corrects *only what looks wrong*, so the intended
    and most common path is a founder who reads the audience, agrees with all of
    it, and changes nothing. Under `edited_by_user` that founder reads as
    unconfirmed forever — and stage 4 would tell them their buyer list is built
    from a guess when they had in fact confirmed it. Agreement and silence are
    different answers and one column cannot carry both.

    Idempotent by intention rather than by accident: confirming twice moves the
    timestamp forward, which is the truthful reading of "when did they last say
    this was right".
    """
    log.info("confirm_icp_profile", profile_id=id, org_id=auth["org_id"])
    _fetch_profile(id, auth["org_id"])

    admin = get_supabase_admin()
    updated = (
        admin.table("icp_profiles")
        .update({"confirmed_at": datetime.now(UTC).isoformat()})
        .eq("id", id)
        .eq("organization_id", auth["org_id"])
        .execute()
    )
    if not updated.data:
        # `_fetch_profile` found it a statement ago, so zero rows means it was
        # deleted in between — a 404, not a 500 on an IndexError.
        raise HTTPException(status_code=404, detail="ICP profile not found")
    return _with_promotions(updated.data[0], auth["org_id"])


@router.delete("/{id}")
async def delete_profile(id: str, auth: dict = Depends(require_can_destroy)):
    """Delete an ICP profile.

    Simulations that used it keep running: `simulations.icp_profile_id` is
    ON DELETE SET NULL, and their agents were materialised at prepare time. What
    is lost is the ability to re-simulate against the same audience, which is
    why the inoculation loop copies agents rather than re-deriving them.

    Library packs promoted out of this profile **survive**, by the same
    reasoning: they are snapshots, and `persona_packs.source_icp_profile_id` is
    ON DELETE SET NULL (026). Deleting the profile costs the provenance link,
    not the pack — an org that promoted an audience and then tidied up its ICP
    profiles would otherwise lose the reusable library the promotion existed to
    build. The affected pack ids come back in the response so the loss of
    provenance is stated rather than discovered.
    """
    from app.services.engine.personas import persona_store

    log.info("delete_icp_profile", profile_id=id, org_id=auth["org_id"])
    _fetch_profile(id, auth["org_id"])
    orphaned = [
        p["pack_id"] for p in persona_store.promotions_of_profile(auth["org_id"], id)
    ]
    admin = get_supabase_admin()
    admin.table("icp_profiles").delete().eq("id", id).eq(
        "organization_id", auth["org_id"]
    ).execute()
    return {
        "status": "deleted",
        "id": id,
        # Still in the library and still runnable; they no longer know where
        # they came from.
        "orphaned_pack_ids": orphaned,
    }
