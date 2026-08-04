from __future__ import annotations

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.auth import get_current_org
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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/synthesize")
async def synthesize(body: SynthesizeBody, auth: dict = Depends(get_current_org)):
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
    """Get one ICP profile."""
    log.info("get_icp_profile", profile_id=id)
    return _fetch_profile(id, auth["org_id"])


@router.patch("/{id}")
async def update_profile(
    id: str,
    body: UpdateProfileBody,
    auth: dict = Depends(get_current_org),
):
    """Replace a synthesized profile with the founder's corrected version.

    The pack is recompiled here, on write. Recompiling on read would make a
    re-simulation's audience depend on when the pack was read, and the
    inoculation loop's entire claim is that the audience did not change between
    the two runs.
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
    return updated.data[0]


@router.delete("/{id}")
async def delete_profile(id: str, auth: dict = Depends(get_current_org)):
    """Delete an ICP profile.

    Simulations that used it keep running: `simulations.icp_profile_id` is
    ON DELETE SET NULL, and their agents were materialised at prepare time. What
    is lost is the ability to re-simulate against the same audience, which is
    why the inoculation loop copies agents rather than re-deriving them.
    """
    log.info("delete_icp_profile", profile_id=id, org_id=auth["org_id"])
    _fetch_profile(id, auth["org_id"])
    admin = get_supabase_admin()
    admin.table("icp_profiles").delete().eq("id", id).eq(
        "organization_id", auth["org_id"]
    ).execute()
    return {"status": "deleted", "id": id}
