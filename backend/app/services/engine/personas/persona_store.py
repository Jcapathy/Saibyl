# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# save_org_pack(org_id, pack, source_icp_profile_id) -> str   (pack id)
# load_org_packs(org_id) -> list[PersonaPack]
# load_org_pack(org_id, pack_id) -> PersonaPack | None
# list_org_pack_rows(org_id) -> list[dict]
# get_org_pack_row(org_id, pack_id) -> dict | None
# rename_org_pack(org_id, pack_id, name) -> dict | None
# delete_org_pack(org_id, pack_id) -> bool
# simulation_ids_using_pack(org_id, pack_id) -> list[str]
# PackIdConflictError
# ─────────────────────────────────────────────────────────
"""The org-level persona pack library (`persona_packs`, migration 026).

Why this table exists, and why it is *not* where compiled ICPs live
--------------------------------------------------------------------
`icp_profiles` keeps the editable profile and the pack it compiles to in one
row, on purpose: an edit and the pack the next run uses cannot then drift apart,
and a re-simulation's claim that "the audience did not change" stays true.
Nothing here weakens that. A compiled ICP pack is still resolved out of
`icp_profiles` by its `icp_` prefix.

What this adds is a **snapshot**. A founder who synthesizes an audience worth
reusing can promote it: the pack is copied into an org-owned row with its own
slug, and from then on the two are independent. Editing the source ICP
recompiles that profile's own pack and leaves the library entry alone — a run
configured last month must not change audience because somebody corrected a job
title today. Drift is surfaced rather than prevented: `source_synced_at` is
compared against `icp_profiles.updated_at`, so the product can say "the ICP this
came from has changed" and re-promoting stays a deliberate act.

Tenancy
-------
Every read and write in this module filters on `organization_id`, and
`(organization_id, pack_id)` is the table's uniqueness constraint. A pack id is
a slug; two organizations will both want `smb-buyers` and both may have it. The
consequence is that **a pack id alone is not an identity** — see
`pack_loader.get_pack`, which is where that boundary is enforced for reads.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import structlog

from app.services.engine.personas.pack_loader import (
    ICP_PACK_PREFIX,
    PackLookupError,
    PersonaPack,
    is_builtin_pack_id,
)

logger = structlog.get_logger()

TABLE = "persona_packs"

# How many `-2`, `-3` … suffixes to try before giving up. A founder with 25
# same-named promotions has a naming problem the store should not paper over.
_MAX_SLUG_ATTEMPTS = 25

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Reserved because `get_pack` routes this prefix to `icp_profiles`. A library
# row that claimed it would be written and then never resolvable — the
# absence-indistinguishable-from-miss shape this codebase keeps removing.
_RESERVED_PREFIXES = (ICP_PACK_PREFIX,)


class PackIdConflictError(ValueError):
    """This organization already has a different pack under that id."""


def _admin():
    from app.core.database import get_supabase_admin

    return get_supabase_admin()


def _table_is_missing(exc: Exception) -> bool:
    """True only for "relation `persona_packs` does not exist".

    Narrow on purpose. Migration 026 is applied by hand, so there is a window in
    which the code is serving and the table is not there. Without this the
    window is not a degraded library — it is a hard failure on *every*
    `get_pack` for a custom pack, because the library is checked first.

    This is not a swallowed exception: it matches one condition, it names that
    condition in the log at ERROR, and every other failure still propagates as
    `PackLookupError`.
    """
    text = str(exc).lower()
    return TABLE in text and ("does not exist" in text or "pgrst205" in text)


def _read(op: str, org_id: str, build) -> list[dict[str, Any]] | None:
    """Run a scoped read. `None` means the table is not there yet."""
    try:
        return build(_admin().table(TABLE)).execute().data or []
    except Exception as exc:
        if _table_is_missing(exc):
            logger.error(
                "persona_pack_library_table_missing",
                op=op,
                org_id=org_id,
                detail=(
                    "migration 026 has not been applied. The org pack library "
                    "reads as empty until it is; built-in and custom packs are "
                    "unaffected."
                ),
            )
            return None
        logger.error("persona_pack_read_failed", op=op, org_id=org_id, error=str(exc))
        raise PackLookupError(f"could not read {TABLE} ({op})") from exc


# ---------------------------------------------------------------------------
# Slugs
# ---------------------------------------------------------------------------

def _slugify(value: str) -> str:
    slug = _SLUG_RE.sub("-", (value or "").lower()).strip("-")[:60].strip("-")
    return slug or "persona-pack"


def _base_id(pack: PersonaPack) -> str:
    """The id a promoted pack should claim, before uniquifying within the org.

    A compiled ICP pack arrives as `icp_<uuid-hex>` — an id that means "look me
    up in `icp_profiles`". Carrying it into the library would produce a row that
    can never be read back, so promotion re-slugs from the pack's name. A pack
    that already has a plain, non-built-in id keeps it.
    """
    candidate = (pack.id or "").strip()
    if (
        not candidate
        or candidate.startswith(_RESERVED_PREFIXES)
        or is_builtin_pack_id(candidate)
    ):
        candidate = _slugify(pack.name)
    if is_builtin_pack_id(candidate):
        # The name slugified onto a built-in's id. The built-in must win — it is
        # a shared global — so the library entry takes an adjacent id rather
        # than a shadowing one it would never be served under.
        candidate = f"{candidate}-lib"
    return candidate


def _taken_ids(org_id: str) -> set[str]:
    rows = _read("taken_ids", org_id, lambda t: t.select("pack_id").eq("organization_id", org_id))
    return {r["pack_id"] for r in rows or []}


def _free_id(org_id: str, base: str) -> str:
    taken = _taken_ids(org_id)
    if base not in taken:
        return base
    for n in range(2, _MAX_SLUG_ATTEMPTS + 1):
        candidate = f"{base}-{n}"
        if candidate not in taken:
            logger.info("org_pack_id_uniquified", org_id=org_id, base=base, pack_id=candidate)
            return candidate
    raise PackIdConflictError(
        f"organization already has {_MAX_SLUG_ATTEMPTS} packs named like '{base}'; "
        f"rename the pack before promoting it"
    )


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def save_org_pack(
    org_id: str,
    pack: PersonaPack,
    source_icp_profile_id: str | None,
    *,
    created_by: str | None = None,
) -> str:
    """Save `pack` into the organization's library. Returns the stored pack id.

    Re-promoting the same ICP profile **refreshes the existing row in place** and
    keeps its pack id, rather than accumulating near-duplicates the founder
    cannot tell apart. That is a deliberate user action, which is the line this
    module draws: an explicit re-promote may move a library pack, an edit to the
    source ICP never does.

    A hand-made pack (`source_icp_profile_id is None`) whose id is already taken
    raises `PackIdConflictError` instead of quietly becoming `…-2`. There is no
    provenance to match it against, so "the same pack again" and "a different
    pack with a clashing name" are indistinguishable here, and guessing is what
    would lose someone's work.

    The stored `pack_data['id']` is always rewritten to the stored `pack_id`.
    Letting them differ would be two sources of truth for one value, and the one
    the engine reads is not the one the API lists.
    """
    now = datetime.now(UTC).isoformat()
    payload_common = {
        "name": pack.name[:200],
        "description": (pack.description or "")[:2000],
        "category": pack.category or "library",
        "source_icp_profile_id": source_icp_profile_id,
        "source_synced_at": now if source_icp_profile_id else None,
        "updated_at": now,
    }

    existing = _existing_for_source(org_id, source_icp_profile_id) if source_icp_profile_id else None

    if existing:
        pack_id = existing["pack_id"]
        stored = pack.model_dump(mode="json")
        stored["id"] = pack_id
        _write(
            "refresh",
            org_id,
            lambda t: t.update({**payload_common, "pack_data": stored})
            .eq("id", existing["id"])
            .eq("organization_id", org_id),
        )
        logger.info(
            "org_pack_refreshed",
            org_id=org_id,
            pack_id=pack_id,
            source_icp_profile_id=source_icp_profile_id,
        )
        return pack_id

    base = _base_id(pack)
    if source_icp_profile_id:
        pack_id = _free_id(org_id, base)
    else:
        if base in _taken_ids(org_id):
            raise PackIdConflictError(f"a pack with id '{base}' already exists in this organization")
        pack_id = base

    stored = pack.model_dump(mode="json")
    stored["id"] = pack_id
    _write(
        "insert",
        org_id,
        lambda t: t.insert({
            **payload_common,
            "organization_id": org_id,
            "pack_id": pack_id,
            "pack_data": stored,
            "created_by": created_by,
            "created_at": now,
        }),
    )
    logger.info(
        "org_pack_saved",
        org_id=org_id,
        pack_id=pack_id,
        source_icp_profile_id=source_icp_profile_id,
        archetypes=len(pack.archetypes),
    )
    return pack_id


def _write(op: str, org_id: str, build) -> list[dict[str, Any]]:
    """Run a scoped write. Unlike `_read`, a missing table is fatal.

    A promote that logs a warning and returns a pack id for a row that was never
    stored is worse than a 500: the founder is told it worked.
    """
    try:
        return build(_admin().table(TABLE)).execute().data or []
    except Exception as exc:
        logger.error("persona_pack_write_failed", op=op, org_id=org_id, error=str(exc))
        raise PackLookupError(f"could not write {TABLE} ({op})") from exc


def _existing_for_source(org_id: str, source_icp_profile_id: str) -> dict[str, Any] | None:
    rows = _read(
        "existing_for_source",
        org_id,
        lambda t: t.select("id, pack_id")
        .eq("organization_id", org_id)
        .eq("source_icp_profile_id", source_icp_profile_id)
        .limit(1),
    )
    return rows[0] if rows else None


def rename_org_pack(org_id: str, pack_id: str, name: str) -> dict[str, Any] | None:
    """Rename a library pack. The **id is deliberately not touched.**

    `simulations.persona_pack_ids` stores these slugs, and there is no foreign
    key that could follow a rename. Changing the id on rename would leave every
    stored reference pointing at nothing, and `run_prepare_agents` reads a
    missing pack as "skip it" — a run that silently loses an audience. A display
    name is a display name; the id is the identity.
    """
    clean = (name or "").strip()[:200]
    if not clean:
        raise ValueError("name must not be empty")

    rows = _write(
        "rename",
        org_id,
        lambda t: t.update({"name": clean, "updated_at": datetime.now(UTC).isoformat()})
        .eq("organization_id", org_id)
        .eq("pack_id", pack_id),
    )
    if not rows:
        return None

    # `pack_data.name` is what the engine puts in the agent-generation prompt
    # ("Pack: {pack.name}"), so leaving it behind would make the library show one
    # name and the agents be built from another.
    row = rows[0]
    stored = dict(row.get("pack_data") or {})
    if stored.get("name") != clean:
        stored["name"] = clean
        _write(
            "rename_pack_data",
            org_id,
            lambda t: t.update({"pack_data": stored})
            .eq("organization_id", org_id)
            .eq("pack_id", pack_id),
        )
        row["pack_data"] = stored
    return row


def delete_org_pack(org_id: str, pack_id: str) -> bool:
    """Delete a library pack. Returns False when there was nothing to delete.

    Past simulations keep working, on the same reasoning `api/icp.py`
    `delete_profile` records for ICP profiles: agents are materialised at prepare
    time, so a completed run holds its own agent rows and does not re-read the
    pack. What is lost is the ability to configure a *new* run against this
    audience.

    The difference worth stating is that `simulations.persona_pack_ids` is a
    jsonb array of slugs with no foreign key, so there is no `ON DELETE SET
    NULL` to record the loss. `simulation_ids_using_pack` exists so the API can
    show the founder what they are unlinking instead of discovering it later.
    """
    rows = _write(
        "delete",
        org_id,
        lambda t: t.delete().eq("organization_id", org_id).eq("pack_id", pack_id),
    )
    deleted = bool(rows)
    logger.info("org_pack_deleted", org_id=org_id, pack_id=pack_id, existed=deleted)
    return deleted


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def _parse(row: dict[str, Any], org_id: str) -> PersonaPack | None:
    try:
        pack = PersonaPack.model_validate(row["pack_data"])
    except Exception as exc:
        logger.error(
            "org_pack_parse_failed",
            org_id=org_id,
            pack_id=row.get("pack_id"),
            error=str(exc),
        )
        return None

    stored_id = row.get("pack_id")
    if stored_id and pack.id != stored_id:
        # The row's id is authoritative — it is what the UNIQUE constraint
        # covers and what `simulations.persona_pack_ids` stores. A mismatch means
        # something wrote around `save_org_pack`, so it is reported rather than
        # quietly reconciled.
        logger.error(
            "org_pack_id_mismatch",
            org_id=org_id,
            row_pack_id=stored_id,
            pack_data_id=pack.id,
            detail="pack_data.id disagrees with the row's pack_id; the row wins",
        )
        pack = pack.model_copy(update={"id": stored_id})

    if is_builtin_pack_id(pack.id):
        # Belt and braces with `save_org_pack`'s `-lib` rewrite: a shadowing row
        # could only arrive by a direct write, and it must never be served,
        # because `_pack_cache` is shared by every org this worker serves.
        logger.error(
            "org_pack_shadows_builtin",
            org_id=org_id,
            pack_id=pack.id,
            detail="a library pack claims a built-in pack's id; it is not served",
        )
        return None
    return pack


def load_org_packs(org_id: str) -> list[PersonaPack]:
    """Every library pack this organization owns."""
    rows = _read(
        "load_org_packs",
        org_id,
        lambda t: t.select("pack_id, pack_data")
        .eq("organization_id", org_id)
        .order("created_at", desc=True),
    )
    packs = [_parse(row, org_id) for row in rows or []]
    return [p for p in packs if p is not None]


def load_org_pack(org_id: str, pack_id: str) -> PersonaPack | None:
    """One library pack, by its actual key: `(organization_id, pack_id)`."""
    rows = _read(
        "load_org_pack",
        org_id,
        lambda t: t.select("pack_id, pack_data")
        .eq("organization_id", org_id)
        .eq("pack_id", pack_id)
        .limit(1),
    )
    if not rows:
        return None
    return _parse(rows[0], org_id)


_ROW_FIELDS = (
    "id, pack_id, name, description, category, source_icp_profile_id, "
    "source_synced_at, created_by, created_at, updated_at"
)


def list_org_pack_rows(org_id: str) -> list[dict[str, Any]]:
    """Library metadata for the API — counts and labels, not the pack body.

    `pack_data` is read (the counts come from it) and then dropped: a library
    listing that ships every archetype of every pack is a page-weight problem
    the first time an org has thirty of them.
    """
    rows = _read(
        "list_org_pack_rows",
        org_id,
        lambda t: t.select(f"{_ROW_FIELDS}, pack_data")
        .eq("organization_id", org_id)
        .order("created_at", desc=True),
    )
    out = []
    for row in rows or []:
        entry = _with_counts(row)
        entry.pop("pack_data", None)
        out.append(entry)
    return out


def get_org_pack_row(org_id: str, pack_id: str) -> dict[str, Any] | None:
    rows = _read(
        "get_org_pack_row",
        org_id,
        lambda t: t.select(f"{_ROW_FIELDS}, pack_data")
        .eq("organization_id", org_id)
        .eq("pack_id", pack_id)
        .limit(1),
    )
    return _with_counts(rows[0]) if rows else None


def _with_counts(row: dict[str, Any]) -> dict[str, Any]:
    archetypes = (row.get("pack_data") or {}).get("archetypes") or []
    out = dict(row)
    out["archetype_count"] = len(archetypes)
    out["archetype_labels"] = [a.get("label", "") for a in archetypes]
    out["adversarial_count"] = sum(1 for a in archetypes if a.get("is_adversarial"))
    return out


def attach_staleness(org_id: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stamp `source_stale` on each row, in one query for the whole set.

    Has the ICP a pack was promoted from been edited since the snapshot? `None`
    when there is nothing to compare against — no source, or a source that has
    since been deleted. That is deliberately not `False`: "this pack has no
    provenance" and "this pack is up to date with its provenance" are different
    answers, and collapsing them would put a reassuring badge on a pack nobody
    can trace.

    Batched because the library listing renders every pack an org owns, and a
    per-row lookup is a query per pack on a page load.
    """
    profile_ids = sorted({
        r["source_icp_profile_id"]
        for r in rows
        if r.get("source_icp_profile_id") and r.get("source_synced_at")
    })
    updated: dict[str, str] = {}
    if profile_ids:
        try:
            result = (
                _admin()
                .table("icp_profiles")
                .select("id, updated_at")
                .eq("organization_id", org_id)
                .in_("id", profile_ids)
                .execute()
            )
        except Exception as exc:
            logger.error("org_pack_staleness_check_failed", org_id=org_id, error=str(exc))
            raise PackLookupError("could not read icp_profiles for staleness") from exc
        updated = {r["id"]: r["updated_at"] for r in result.data or []}

    for row in rows:
        profile_id = row.get("source_icp_profile_id")
        synced = row.get("source_synced_at")
        source_updated = updated.get(profile_id) if profile_id else None
        row["source_stale"] = (
            None
            if not (synced and source_updated)
            else _as_dt(source_updated) > _as_dt(synced)
        )
    return rows


def _as_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def promotions_of_profile(org_id: str, profile_id: str) -> list[dict[str, Any]]:
    """Library packs promoted out of one ICP profile, with their staleness.

    Read by the ICP editor: an edit recompiles the profile's own pack and leaves
    these alone, and the founder has to be able to see that.
    """
    rows = _read(
        "promotions_of_profile",
        org_id,
        lambda t: t.select(f"{_ROW_FIELDS}, pack_data")
        .eq("organization_id", org_id)
        .eq("source_icp_profile_id", profile_id)
        .order("created_at", desc=True),
    )
    out = []
    for row in rows or []:
        entry = _with_counts(row)
        entry.pop("pack_data", None)
        out.append(entry)
    return attach_staleness(org_id, out)


def simulation_ids_using_pack(org_id: str, pack_id: str) -> list[str]:
    """Simulations in this org whose `persona_pack_ids` contain `pack_id`.

    `persona_pack_ids` is jsonb (verified against production), so this is a
    containment query rather than an array overlap. Used to tell the founder
    what a delete detaches — deleting is still allowed, because the runs
    themselves keep working.
    """
    try:
        result = (
            _admin()
            .table("simulations")
            .select("id")
            .eq("organization_id", org_id)
            .contains("persona_pack_ids", [pack_id])
            .execute()
        )
    except Exception as exc:
        logger.error("pack_usage_lookup_failed", org_id=org_id, pack_id=pack_id, error=str(exc))
        raise PackLookupError("could not read simulations for pack usage") from exc
    return [row["id"] for row in result.data or []]
