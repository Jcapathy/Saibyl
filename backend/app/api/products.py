"""The staged rail, per product.

A "product" is a `projects` row. The word changed because the reader changed —
a founder has a product; a consultant has projects, and the noun decides who the
page thinks it is talking to. Nothing was renamed in the database, because a
vocabulary decision is not a schema decision and conflating them would have
turned a copy change into a migration.

This router is **additive**. Every route that existed before it still works and
still resolves the same data; nothing here replaces `/api/projects`. That is
deliberate: if the rail turns out to be the wrong shape, the fix is a navigation
change rather than a revert.

Route order: `/{id}` is declared last, after every static path. A static path
shadowed by a parameterised one has shipped twice in this codebase and both
times reached Postgres as an invalid UUID cast — a 500 that reads as a server
fault rather than a routing bug.
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_org
from app.core.database import get_supabase_admin
from app.services.stages import build_product_state, build_product_states

log = structlog.get_logger()

router = APIRouter(tags=["products"])


def _fetch_products(org_id: str) -> list[dict]:
    admin = get_supabase_admin()
    result = (
        admin.table("projects")
        .select("id, name, description, created_at, updated_at")
        .eq("organization_id", org_id)
        .neq("status", "archived")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


@router.get("")
async def list_products(auth: dict = Depends(get_current_org)):
    """Every product with its rail, its moment, and what needs attention.

    Returned as `{items, total}` rather than a bare array — the envelope every
    list endpoint in this API uses, because a bare array left a user with 50
    rows unable to reach page 2.
    """
    org_id = auth["org_id"]
    log.info("list_products", org_id=org_id)
    products = _fetch_products(org_id)
    states = build_product_states(org_id, products)
    return {"items": [s.model_dump() for s in states], "total": len(states)}


@router.get("/{id}")
async def get_product(id: str, auth: dict = Depends(get_current_org)):
    """One product's rail."""
    org_id = auth["org_id"]
    log.info("get_product", product_id=id, org_id=org_id)
    admin = get_supabase_admin()
    result = (
        admin.table("projects")
        .select("id, name, description, created_at, updated_at")
        .eq("id", id)
        .eq("organization_id", org_id)
        .execute()
    )
    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Product not found")
    return build_product_state(org_id, rows[0]).model_dump()
