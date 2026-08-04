"""The Marketing lens's variants — the copy under test, and the objective.

Variants are configured before a run starts and are immutable once it has. The
whole claim of a matched-swarm test is that the arenas differed only in their
copy; editing a variant after the fact would leave a scoreboard describing an
experiment that was never run, and the artifact has no way to know.
"""
from __future__ import annotations

from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import get_current_org
from app.core.database import get_supabase_admin
from app.services.billing.agent_pricing import MAX_RUNNABLE_VARIANTS, tier_caps

log = structlog.get_logger()

router = APIRouter(tags=["variants"])

Objective = Literal[
    "clicks", "foot_traffic", "product_sale", "service_sale", "signup", "awareness"
]

# Statuses a run can still be configured in. Once it is running or complete the
# variants are the record of what was executed.
_EDITABLE_STATUSES = {"draft", "ready"}

# Keys are assigned by position rather than chosen. A marketer naming their own
# keys produces "control"/"v2"/"final_FINAL", and the key is stamped on every
# event — it has to be short, stable and ordered.
_KEYS = "abcdefgh"

MAX_LABEL = 80
MAX_CONTENT = 4_000


class VariantInput(BaseModel):
    label: str = Field(default="", max_length=MAX_LABEL)
    content: str = Field(min_length=1, max_length=MAX_CONTENT)


class SetVariantsBody(BaseModel):
    """The full set, replacing whatever is there.

    A whole-set replace rather than per-variant CRUD: the keys are positional,
    so deleting the second of four variants has to renumber the rest, and an
    endpoint that renumbers rows one call at a time can leave a run half-keyed.
    """

    objective: Objective | None = None
    variants: list[VariantInput] = Field(default_factory=list, max_length=8)


def _load_simulation(simulation_id: str, org_id: str) -> dict:
    sim = (
        get_supabase_admin()
        .table("simulations")
        .select(
            "id, status, organization_id, objective, agent_count, max_rounds, "
            "platforms"
        )
        .eq("id", simulation_id)
        .eq("organization_id", org_id)
        .execute()
    )
    if not sim.data:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return sim.data[0]


@router.get("/objectives")
async def list_objectives(_auth: dict = Depends(get_current_org)):
    """The objectives a Marketing run can be scored on, with what each measures.

    Served rather than hardcoded in the client so the objective list, the intents
    each one counts, and the copy describing them cannot drift apart across the
    configurator, the scoreboard and the report.
    """
    from app.services.intelligence.variant_scoreboard import OBJECTIVE_INTENTS

    labels = {
        "clicks": ("Clicks / traffic", "Would they click through?"),
        "foot_traffic": ("Foot traffic", "Would they visit in person?"),
        "product_sale": ("Product sale", "Would they buy?"),
        "service_sale": ("Service sale", "Would they enquire?"),
        "signup": ("Signup / trial", "Would they start a trial?"),
        "awareness": ("Awareness / brand", "Would they pass it on?"),
    }
    return {
        "objectives": [
            {
                "value": key,
                "label": labels[key][0],
                "question": labels[key][1],
                "counts_intents": list(intents),
            }
            for key, intents in OBJECTIVE_INTENTS.items()
        ]
    }


@router.get("/{simulation_id}")
async def get_variants(simulation_id: str, auth: dict = Depends(get_current_org)):
    """This run's configured variants, in display order."""
    sim = _load_simulation(simulation_id, auth["org_id"])
    rows = (
        get_supabase_admin()
        .table("simulation_variants")
        .select("id, variant_key, label, content, position")
        .eq("simulation_id", simulation_id)
        .order("position")
        .execute()
    ).data or []

    return {
        "simulation_id": simulation_id,
        "objective": sim.get("objective"),
        "variants": rows,
        "editable": sim.get("status") in _EDITABLE_STATUSES,
        "max_variants": MAX_RUNNABLE_VARIANTS,
    }


@router.put("/{simulation_id}")
async def set_variants(
    simulation_id: str,
    body: SetVariantsBody,
    auth: dict = Depends(get_current_org),
):
    """Replace this run's variants and set its objective.

    Refuses once the run has started. The scoreboard's claim is that the arenas
    differed only in their copy — editing a variant afterwards would leave the
    artifact describing an experiment that never ran, and nothing downstream
    could detect it.
    """
    org_id = auth["org_id"]
    sim = _load_simulation(simulation_id, org_id)
    status = sim.get("status")

    if status not in _EDITABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(
                f"This run is {status}. Variants are fixed once a run starts — "
                f"the comparison's whole claim is that the arenas differed only "
                f"in their copy. Clone the run to test different variants."
            ),
        )

    count = len(body.variants)
    if count == 1:
        raise HTTPException(
            status_code=400,
            detail=(
                "One variant is not a comparison. Configure two or more, or "
                "none at all to run an ordinary single-arena simulation."
            ),
        )
    if count > MAX_RUNNABLE_VARIANTS:
        raise HTTPException(
            status_code=400,
            detail=f"At most {MAX_RUNNABLE_VARIANTS} variants can be run.",
        )

    caps = tier_caps((auth.get("org") or {}).get("plan"))
    if count > caps.max_variants:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Your plan allows {caps.max_variants} variants; this run has "
                f"{count}. Every variant is a full arena — the swarm reacts to "
                f"each one — so the run costs proportionally more."
            ),
        )

    admin = get_supabase_admin()

    # Whole-set replace. Positional keys mean a partial update can leave the run
    # renumbered halfway.
    admin.table("simulation_variants").delete().eq(
        "simulation_id", simulation_id
    ).execute()

    rows = [
        {
            "simulation_id": simulation_id,
            "organization_id": org_id,
            "variant_key": _KEYS[i],
            "label": variant.label.strip(),
            "content": variant.content.strip(),
            "position": i,
        }
        for i, variant in enumerate(body.variants)
    ]
    if rows:
        admin.table("simulation_variants").insert(rows).execute()

    admin.table("simulations").update({
        "objective": body.objective,
        # Kept in step so the quote and the engine agree on the arena count.
        # `estimate_simulation_cost` charges agent_count x rounds x variants, and
        # a run whose `variants` column disagreed with its variant rows would be
        # quoted for a different experiment than the one that executes.
        "variants": max(1, count),
    }).eq("id", simulation_id).execute()

    log.info(
        "variants_configured",
        simulation_id=simulation_id,
        org_id=org_id,
        variants=count,
        objective=body.objective,
    )

    return {
        "simulation_id": simulation_id,
        "objective": body.objective,
        "variants": rows,
        "editable": True,
        "max_variants": MAX_RUNNABLE_VARIANTS,
    }
