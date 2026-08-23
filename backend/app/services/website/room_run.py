# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# eligible_simulation(project_id, organization_id) -> dict | None
# ineligibility_reason(project_id, organization_id) -> str
# launch_room_run(*, revision_row, snapshot_row, organization_id,
#                 created_by=None) -> dict
# page_text(html) -> str
# page_title(html) -> str
# ─────────────────────────────────────────────────────────
"""Run the room against the new page (PRD_V3 §4d, the prove leg).

The founder has a revised page. The claim that matters is not "the critics
score it higher" — it is "the same people who tore the old page apart read
this one and stopped raising what they raised." That claim already has
machinery: the inoculation loop (migration 021). A re-simulation is an
ordinary run with a parent, its agents are copies of the parent's rows, and
the before/after is two artifacts built by one builder. This module composes
the revised page as one pre-positioned asset and hands it to that machinery
unchanged — `create_resimulation` is called, never reimplemented.

KNOWN COMPROMISES — the honest slice, and the right future shape
----------------------------------------------------------------
1. **The page is stored against one objection.** `inoculation_assets.
   objection_key` is NOT NULL by schema, because a drafted asset answers one
   objection. A whole page answers all of them. The page is therefore filed
   under the parent run's most load-bearing objection. The measured deltas
   are unaffected — `measure_inoculation` compares every objection in either
   run regardless of targeting — but per-objection *attribution* (`asset_ids`,
   `converted_agent_usernames` on each delta) names only that top objection.
   Right shape: a nullable objection_key, or a `targets_all` flag, in a
   future migration.
2. **The asset kind is `disclosure`.** The DB CHECK constraint admits seven
   drafted kinds and none of them is "the page itself". `disclosure` is the
   generic published-material kind and the least wrong label; agents see the
   page text either way. Right shape: widen the CHECK and `ASSET_TYPES` with
   a `page` kind.
3. **Agents read the page's opening, not the whole page.** `asset_prompt_
   block` carries `ASSET_BODY_IN_PROMPT` (700) characters of an asset body
   into every action prompt, deliberately — an asset in every prompt is the
   run's largest cost line. The stored body is the full stripped page text
   (capped at `PAGE_TEXT_CAP`), so the artifact is honest; the swarm reacts
   to the headline, subhead and lead, which is also what a real skimmer
   reads. Right shape: a page-kind asset with a page-sized prompt window,
   priced accordingly.
4. **"Same seed" means the audience is copied, not re-rolled.** There is no
   RNG seed to pass: `create_resimulation` copies the parent's agent rows
   verbatim (same usernames, same profiles, same cohort flags), which is the
   stronger guarantee and the one the loop's whole claim rests on.

Charging is deliberately absent here. The inoculation path charges the
re-run at `POST /api/simulations/{id}/start` — `check_credit_budget` with
`reuse_agents` (no generation charge) plus the per-asset action surcharge —
and creating the child is free on that path too. This module rides that
exactly. The drafting fee (`check_inoculation_draft_budget`) does not apply:
composing the page into an asset makes no model call.
"""
from __future__ import annotations

import html as html_lib
import re
from typing import Any

import structlog

from app.core.database import get_supabase_admin

logger = structlog.get_logger()

# Characters of stripped page text stored as the asset body. Bounds the row
# and every artifact that carries it; the agent prompt window (700 chars) is
# far below this either way.
PAGE_TEXT_CAP = 12_000

# How many of the project's newest finished runs are examined for one the
# machinery can repeat. Bounded on purpose: each candidate costs two lookups,
# and a project whose last five finished runs all lack a saved audience or
# measured objections has a data problem this scan should surface, not absorb.
_ELIGIBLE_SCAN_LIMIT = 5

# The documents bucket — the same one `services/website/store.py` writes.
# Used only when that module does not (yet) expose `read_stored`.
_BUCKET = "project-media"

# What the composed asset is filed as. See compromise #2 above.
_PAGE_ASSET_TYPE = "disclosure"

# ---------------------------------------------------------------------------
# Founder sentences — shared with the router, scanned by the vocabulary test
# ---------------------------------------------------------------------------

NO_FINISHED_RUN_REASON = (
    "This workspace doesn't have a finished audience run yet, so there's "
    "nothing to re-run against the new page. Run the room once first — the "
    "re-run is what proves the new page moved it."
)

NOT_REPEATABLE_REASON = (
    "Your finished runs can't be repeated as-is: the room needs its saved "
    "people and their measured objections to line up a before and after. Run "
    "the audience once more, then bring them the new page."
)

NO_READABLE_TEXT_ERROR = (
    "The revised page has no readable text, so there is nothing to show the "
    "room."
)

NO_STORED_COPY_ERROR = (
    "That revised page has no stored copy yet, so there is nothing to show "
    "the room."
)


# ---------------------------------------------------------------------------
# HTML → text, deterministically
# ---------------------------------------------------------------------------

_COMMENTS = re.compile(r"<!--.*?-->", re.DOTALL)
_DROP_BLOCKS = re.compile(
    r"<(script|style|noscript|template|svg)\b.*?</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
# Only well-formed markup, and the same shape `style_guide._TAG` uses — the
# two are the codebase's two HTML-to-text strips and they must not disagree
# about what a tag is.
#
# `<[^>]+>` treats any literal "<" as a tag opening and deletes everything up
# to the next ">" anywhere later. A browser does not: HTML only starts a tag
# when a name follows the "<", so "Setup takes <5 minutes" renders as written
# and then a "Learn more >" further down the page ended the phantom tag,
# taking every sentence in between out of the text the room is shown. That
# text is a stored artifact the before/after cites, and an empty one raises
# NO_READABLE_TEXT_ERROR.
_TAG = re.compile(r"</?[a-zA-Z][^>]*>|<[!?][^>]*>")
_H1 = re.compile(r"<h1\b[^>]*>(.*?)</h1\s*>", re.IGNORECASE | re.DOTALL)


def page_text(html: str) -> str:
    """The page as a reader would quote it: no markup, no code, one line.

    Deterministic and dependency-free on purpose — this text becomes a stored
    artifact the before/after cites, and a parser upgrade that re-extracts it
    differently would change the experiment between two runs.
    """
    text = _COMMENTS.sub(" ", html)
    text = _DROP_BLOCKS.sub(" ", text)
    text = _TAG.sub(" ", text)
    text = html_lib.unescape(text)
    return " ".join(text.split())[:PAGE_TEXT_CAP]


def page_title(html: str) -> str:
    """The page's own h1, or "" when it has none.

    The h1 is what the page leads with, which makes it the honest asset
    title — the buyer clicks the page's claim, not a label we invent for it.
    """
    match = _H1.search(_COMMENTS.sub(" ", html))
    if not match:
        return ""
    title = html_lib.unescape(_TAG.sub(" ", match.group(1)))
    return " ".join(title.split())[:200]


# ---------------------------------------------------------------------------
# Eligibility — the machinery's real preconditions, checked up front
# ---------------------------------------------------------------------------

def _has_rows(table: str, column: str, simulation_id: str) -> bool:
    rows = (
        get_supabase_admin()
        .table(table)
        .select(column)
        .eq("simulation_id", simulation_id)
        .limit(1)
        .execute()
    ).data
    return bool(rows)


def eligible_simulation(project_id: str, organization_id: str) -> dict | None:
    """The project's newest finished run the machinery can actually repeat.

    Three preconditions, all real rather than assumed:

    - **status `complete`** — `create_resimulation` refuses anything else,
      because the before/after needs the parent's measured objections.
    - **saved agents** — the child's audience is a copy of the parent's
      `simulation_agents` rows. `create_resimulation` raises on their absence
      only *after* inserting the child, which would strand an orphan row, so
      it is checked here first.
    - **measured objections** — `inoculation_assets.objection_key` is NOT
      NULL, so the page cannot be filed against a run that clustered none;
      and a run with no objections has nothing for the re-run to line up.

    A re-simulation is itself a valid parent — the most recent finished run
    is the room as the founder last saw it, whatever its ancestry.
    """
    sims = (
        get_supabase_admin()
        .table("simulations")
        .select("id, name, status, created_at, project_id")
        .eq("project_id", project_id)
        .eq("organization_id", organization_id)
        .eq("status", "complete")
        .order("created_at", desc=True)
        .limit(_ELIGIBLE_SCAN_LIMIT)
        .execute()
    ).data or []

    for sim in sims:
        if not _has_rows("simulation_agents", "id", sim["id"]):
            logger.info(
                "website_room_candidate_skipped",
                simulation_id=sim["id"],
                reason="no saved agents to copy",
            )
            continue
        if not _has_rows("canonical_objections", "objection_key", sim["id"]):
            logger.info(
                "website_room_candidate_skipped",
                simulation_id=sim["id"],
                reason="no measured objections to line up",
            )
            continue
        return sim
    return None


def ineligibility_reason(project_id: str, organization_id: str) -> str:
    """Why `eligible_simulation` returned None, as one founder sentence."""
    any_complete = (
        get_supabase_admin()
        .table("simulations")
        .select("id")
        .eq("project_id", project_id)
        .eq("organization_id", organization_id)
        .eq("status", "complete")
        .limit(1)
        .execute()
    ).data
    return NOT_REPEATABLE_REASON if any_complete else NO_FINISHED_RUN_REASON


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------

def _revision_html(revision_row: dict[str, Any]) -> str:
    """The revised page's HTML, from wherever this revision carries it.

    C-2's gauntlet worker either hands the text along on the row
    (`revision_text`) or leaves a storage ref (`revision_html`, per PRD_V3
    §4d's `page_revisions` shape). The storage read prefers the store
    module's `read_stored(path) -> bytes` helper and falls back to a direct
    download from the same bucket the store writes, so this works on either
    side of that helper landing.
    """
    inline = str(revision_row.get("revision_text") or "").strip()
    if inline:
        return inline

    # `html_path` first: it is the column migration 037 declares and the one
    # `revision_tasks.py` writes. `revision_html` is PRD_V3 §4d's name for the
    # same storage ref and is kept as a fallback, but no row carries it.
    path = str(
        revision_row.get("html_path") or revision_row.get("revision_html") or ""
    ).strip()
    if not path:
        raise ValueError(NO_STORED_COPY_ERROR)

    from app.services.website import store

    reader = getattr(store, "read_stored", None)
    raw = (
        reader(path)
        if reader is not None
        else get_supabase_admin().storage.from_(_BUCKET).download(path)
    )
    return raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)


def _top_objection(simulation_id: str) -> dict[str, Any] | None:
    """The parent run's most load-bearing objection — the page's filing key."""
    rows = (
        get_supabase_admin()
        .table("canonical_objections")
        .select("objection_key, label, load_bearing_score")
        .eq("simulation_id", simulation_id)
        .order("load_bearing_score", desc=True)
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


async def launch_room_run(
    *,
    revision_row: dict[str, Any],
    snapshot_row: dict[str, Any],
    organization_id: str,
    created_by: str | None = None,
) -> dict[str, Any]:
    """Compose the revised page as one asset and clone the room around it.

    Everything after the asset insert is the existing machinery verbatim:
    `create_resimulation` clones the parent with copied agents and the asset
    pre-positioned, the child runs and is charged through the ordinary
    simulation start path, and the before/after lands in
    `inoculation_results` where the existing result routes read it.
    """
    from app.services.intelligence.inoculation import create_resimulation

    parent = eligible_simulation(snapshot_row["project_id"], organization_id)
    if parent is None:
        raise ValueError(
            ineligibility_reason(snapshot_row["project_id"], organization_id)
        )

    html = _revision_html(revision_row)
    body = page_text(html)
    if not body:
        raise ValueError(NO_READABLE_TEXT_ERROR)
    title = page_title(html) or "The new page"

    # Guaranteed by eligibility, re-read rather than trusted: the filing key
    # must exist at insert time, not at scan time.
    objection = _top_objection(parent["id"])
    if objection is None:
        raise ValueError(NOT_REPEATABLE_REASON)

    asset = (
        get_supabase_admin()
        .table("inoculation_assets")
        .insert({
            "simulation_id": parent["id"],
            "organization_id": organization_id,
            "objection_key": objection["objection_key"],
            "objection_label": objection.get("label") or objection["objection_key"],
            "asset_type": _PAGE_ASSET_TYPE,
            "title": title,
            "body": body,
            # Recorded before the run, the house rule: an unstated hypothesis
            # is one that is always retroactively correct.
            "hypothesis": (
                "The revised page answers the room at the source. The same "
                "audience reading this copy should raise its strongest "
                "objection less than it did against the original page."
            ),
            "status": "draft",
            "created_by": created_by,
        })
        .execute()
    ).data[0]

    child = create_resimulation(
        parent["id"],
        organization_id,
        [asset["id"]],
        created_by=created_by,
        name=f"{parent['name']} — the new page",
    )

    logger.info(
        "website_room_run_launched",
        parent_simulation_id=parent["id"],
        child_simulation_id=child["id"],
        revision_id=revision_row.get("id"),
        snapshot_id=snapshot_row.get("id"),
        asset_id=asset["id"],
        body_chars=len(body),
    )

    child_id = child["id"]
    return {
        "simulation_id": child_id,
        "parent_simulation_id": parent["id"],
        "asset_id": asset["id"],
        "revision_id": revision_row.get("id"),
        "status": child.get("status") or "ready",
        # The existing surfaces. Starting is where the re-run is priced and
        # charged; results build automatically when it completes.
        "start": f"/api/simulations/{child_id}/start",
        "watch": f"/api/simulations/{child_id}/status",
        "result": f"/api/inoculation/{child_id}/result",
    }
