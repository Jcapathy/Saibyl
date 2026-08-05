"""Assemble one product's rail from what is actually stored.

Read the package docstring first — it carries the rule this module implements.

Two things about the shape of the answer are deliberate and easy to undo by
accident:

**`runnable` has three values, not two.** `ready` and `degraded` both mean the
stage will run; they differ in whether an input it wants is missing. Collapsing
them loses the product's whole argument, which is that skipping a step is
allowed and *priced* — the founder is told what the answer will be missing
before any credits move. `blocked` is reserved for the one case where running is
meaningless rather than merely weaker, and it always carries the action that
unblocks it. There is no fourth value for "disabled", because there is no
disabled: never a grey button.

**A stage always states either what it inherited or what is missing.** Never
neither. `_check_invariants` enforces it here rather than trusting five call
sites to remember, because a stage that silently inherits nothing is
indistinguishable on screen from a stage that had nothing to inherit, and the
founder cannot tell whether stage 4 knew about stage 1.

Every number below is read from a row. Where a row is absent the field is
absent — `None`, not `0`. A zero that means "we did not look" is the defect
class this codebase produces most often.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import structlog
from pydantic import BaseModel, Field

from app.core.database import get_supabase_admin
from app.services.engine.founder_stages import FOUNDER_STAGES

log = structlog.get_logger()

StageId = Literal["audience", "reactions", "answers", "buyers", "messages"]

STAGE_ORDER: tuple[StageId, ...] = (
    "audience",
    "reactions",
    "answers",
    "buyers",
    "messages",
)

STAGE_LABELS: dict[StageId, str] = {
    "audience": "Audience",
    "reactions": "Reactions",
    "answers": "Answers",
    "buyers": "Buyers",
    "messages": "Messages",
}

# What the stage is for, in the founder's words. Shown under the stage name.
# Deliberately not the internal question — nobody arriving here has heard the
# phrase "ideal customer profile" and nothing on the rail requires them to.
STAGE_BLURBS: dict[StageId, str] = {
    "audience": "who reacts to this",
    "reactions": "what they said, and what they object to",
    "answers": "what to say back, and whether it worked",
    "buyers": "real companies that match",
    "messages": "which version wins",
}

# How long a candidate list is current for. Not a guess: a discovery run reads
# public company pages, and the reason to refresh is that the pages changed.
# Seven days is the shortest interval at which saying "this is stale" is more
# useful than noisy, and it is stated here so it can be argued with rather than
# discovered in a conditional.
CANDIDATE_LIST_STALE_AFTER = timedelta(days=7)

# What "finished" is spelled as in the database.
#
# **It is `complete`, not `completed`.** The ingestion pipeline writes
# `"complete"` and `run_simulation` writes `"complete"`; on 2026-08-05
# production held 27 documents and 52 simulations spelled that way. Every row
# spelled `completed` was seeded by hand for testing.
#
# This module first shipped comparing against `"completed"` and was wrong on
# every real row: a founder who had uploaded and processed a deck was told
# "Nothing to read yet", and a product with a finished run was told nothing had
# run. It passed its own tests and its own screenshots, because the seed data
# was written from the same wrong assumption as the code — which is the reason
# a live run is part of the gate and a green suite is not.
#
# Both spellings are accepted rather than one corrected, because the database
# genuinely contains both and a reader that insists on either is wrong about
# some rows. `tests/test_stage_state.py` pins the real values.
DOCUMENT_READ = frozenset({"complete", "completed"})
DOCUMENT_IN_FLIGHT = frozenset({"pending", "processing"})
DOCUMENT_FAILED = frozenset({"failed"})
RUN_FINISHED = frozenset({"complete", "completed"})
RUN_IN_FLIGHT = frozenset({"pending", "running", "ready"})
DISCOVERY_FINISHED = frozenset({"completed"})  # gtm_discovery_runs really is this


# ---------------------------------------------------------------------------
# The shapes the client renders
# ---------------------------------------------------------------------------

class InheritedLine(BaseModel):
    """What a stage received from an earlier one, as a line you can click.

    "Audience — 6 buyer types, confirmed 4 Aug." The link is what stops a
    founder wondering whether stage 4 knew about stage 1.
    """

    label: str
    href: str


class Action(BaseModel):
    """The button. A missing input either has one or it is not blocking."""

    label: str
    href: str


class MissingInput(BaseModel):
    """An input a stage did not get, and what its absence costs the answer.

    `consequence` is the load-bearing field and it is written in full sentences
    for the founder, not summarised into a status. It is shown before any
    credits move.
    """

    headline: str
    consequence: str
    action: Action | None = None


class AttentionLine(BaseModel):
    """Something the system genuinely knows about this product.

    Never invented to fill the card. A product with nothing to report returns an
    empty list, and the client says so and offers the next stage.
    """

    kind: str
    text: str
    href: str | None = None
    # `high` sorts above `low` on the card. Two levels, because three would be a
    # ranking nobody could explain.
    weight: Literal["high", "low"] = "low"


class StageState(BaseModel):
    id: StageId
    number: int
    label: str
    blurb: str
    href: str

    runnable: Literal["ready", "degraded", "blocked"]

    # What this stage has already produced, in words. None means it has produced
    # nothing yet — which is different from having produced an empty result, and
    # the two must not render the same.
    produced: str | None = None

    inherited: list[InheritedLine] = Field(default_factory=list)
    missing: list[MissingInput] = Field(default_factory=list)


class Moment(BaseModel):
    """Axis B — where the company is. Asked per run, defaulting to last time."""

    id: str
    label: str
    # `last_run` when this is what the previous run used, `default` when nothing
    # has run yet. The client says which, rather than presenting a guess as a
    # memory.
    source: Literal["last_run", "default"]


class ProductState(BaseModel):
    id: str
    name: str
    description: str | None = None

    moment: Moment
    stages: list[StageState]
    # Stages whose every wanted input is present. `degraded` does not count —
    # the phrase on the card is "have what they need".
    stages_ready: int
    attention: list[AttentionLine] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Reading what is stored
# ---------------------------------------------------------------------------

def _iso_to_dt(value: Any) -> datetime | None:
    """Parse a stored timestamp, or None. Never raises on bad data.

    A malformed timestamp is logged and treated as absent rather than crashing
    the whole card — but it is *logged*, because a parse that silently yields
    None is how a lookup miss and a legitimate absence come to share one value.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        log.warning("stage_state_unparseable_timestamp", value=str(value)[:64])
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _short_date(value: Any) -> str | None:
    """`4 Aug`. None when there is no date, so the caller can omit the clause."""
    parsed = _iso_to_dt(value)
    if parsed is None:
        return None
    return f"{parsed.day} {parsed.strftime('%b')}"


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"


class _OrgData:
    """Every row the rail needs for one organization, fetched once.

    Assembled per request rather than cached: the whole point of the card is
    that it reflects what is true now, and a stale "run finished" line is worse
    than no line. The queries are all indexed lookups on `organization_id`.
    """

    def __init__(self, org_id: str, project_ids: list[str]):
        self.org_id = org_id
        self.project_ids = project_ids

        admin = get_supabase_admin()
        empty: list[dict] = []

        def rows(table: str, columns: str, key: str = "project_id") -> list[dict]:
            if not project_ids:
                return empty
            result = (
                admin.table(table)
                .select(columns)
                .eq("organization_id", org_id)
                .in_(key, project_ids)
                .execute()
            )
            return result.data or []

        self.documents = rows(
            "documents", "id, project_id, processing_status, material_kind"
        )
        self.profiles = rows(
            "icp_profiles",
            "id, project_id, name, confirmed_at, updated_at, created_at, profile",
        )
        self.simulations = rows(
            "simulations",
            "id, project_id, name, status, variants, founder_stage, "
            "parent_simulation_id, created_at, completed_at",
        )
        self.discovery_runs = rows(
            "gtm_discovery_runs",
            "id, project_id, status, candidates_found, created_at",
        )

        sim_ids = [s["id"] for s in self.simulations]

        def by_sim(table: str, columns: str, key: str = "simulation_id") -> list[dict]:
            if not sim_ids:
                return empty
            result = (
                admin.table(table)
                .select(columns)
                .eq("organization_id", org_id)
                .in_(key, sim_ids)
                .execute()
            )
            return result.data or []

        self.objections = by_sim("canonical_objections", "id, simulation_id")
        self.assets = by_sim("inoculation_assets", "id, simulation_id, status")
        self.inoculation_results = by_sim(
            "inoculation_results",
            "parent_simulation_id, assets_tested, assets_effective",
            key="parent_simulation_id",
        )
        # Only the scoreboard sub-object, not the whole artifact. The artifact is
        # large and the card needs two of its fields; `->` is a PostgREST JSON
        # path and returns null when the key is absent, which is the honest
        # answer for a single-arena run.
        self.analyses = by_sim(
            "simulation_analysis", "simulation_id, artifact->scoreboard"
        )

    # -- indexes ---------------------------------------------------------

    def group(self, rows: list[dict], key: str) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            value = row.get(key)
            if value:
                out[str(value)].append(row)
        return out


# ---------------------------------------------------------------------------
# The rail
# ---------------------------------------------------------------------------

def _archetype_count(profile_row: dict) -> int | None:
    """How many buyer types the audience carries, or None if unreadable.

    None rather than 0 when the profile body is missing or the wrong shape: a
    zero here would render as "0 buyer types", which is a measurement, and we
    did not measure anything.
    """
    body = profile_row.get("profile")
    if not isinstance(body, dict):
        return None
    archetypes = body.get("archetypes")
    if not isinstance(archetypes, list):
        return None
    return len(archetypes)


def _audience_summary(profile_row: dict | None) -> str | None:
    """`6 buyer types, confirmed 4 Aug` — omitting any clause we cannot support."""
    if profile_row is None:
        return None
    count = _archetype_count(profile_row)
    head = _plural(count, "buyer type") if count is not None else "Worked out"
    confirmed = _short_date(profile_row.get("confirmed_at"))
    if confirmed:
        return f"{head}, confirmed {confirmed}"
    return f"{head}, not confirmed yet"


def _build_audience(
    product_id: str,
    docs: list[dict],
    profile: dict | None,
) -> StageState:
    href = f"/app/products/{product_id}/audience"
    processed = [d for d in docs if d.get("processing_status") in DOCUMENT_READ]

    inherited: list[InheritedLine] = []
    missing: list[MissingInput] = []

    if processed:
        inherited.append(
            InheritedLine(
                label=f"Your material — {_plural(len(processed), 'file')} read",
                href=f"/app/products/{product_id}/audience#material",
            )
        )
        runnable: Literal["ready", "degraded", "blocked"] = "ready"
    else:
        # Not a judgement call: `synthesize_icp` raises on empty material. A
        # "run anyway" button here would be a button that always fails.
        pending = [
            d for d in docs if d.get("processing_status") in DOCUMENT_IN_FLIGHT
        ]
        runnable = "blocked"
        missing.append(
            MissingInput(
                headline=(
                    "Your files are still being read"
                    if pending
                    else "Nothing to read yet"
                ),
                consequence=(
                    "We work out who buys this by reading what you have written. "
                    "As soon as the first file is read, this can run."
                    if pending
                    else "We work out who buys this by reading what you have "
                    "written — a deck, a landing page, a PRD, a pricing page. "
                    "Without one of those there is nothing to read, and we would "
                    "be guessing at your buyer instead of deriving them."
                ),
                action=Action(
                    label="Upload something",
                    href=f"/app/products/{product_id}/audience#upload",
                ),
            )
        )

    return StageState(
        id="audience",
        number=1,
        label=STAGE_LABELS["audience"],
        blurb=STAGE_BLURBS["audience"],
        href=href,
        runnable=runnable,
        produced=_audience_summary(profile),
        inherited=inherited,
        missing=missing,
    )


def _build_reactions(
    product_id: str,
    docs: list[dict],
    profile: dict | None,
    finished_runs: list[dict],
    objection_counts: dict[str, int],
) -> StageState:
    href = f"/app/products/{product_id}/reactions"
    processed = [d for d in docs if d.get("processing_status") in DOCUMENT_READ]

    inherited: list[InheritedLine] = []
    missing: list[MissingInput] = []

    if profile is not None:
        summary = _audience_summary(profile)
        inherited.append(
            InheritedLine(
                label=f"Audience — {summary}" if summary else "Audience",
                href=f"/app/products/{product_id}/audience",
            )
        )
    else:
        missing.append(
            MissingInput(
                headline="No audience worked out yet",
                consequence=(
                    "We'll use a general business audience. You'll get the "
                    "objections any B2B product gets, not the ones yours will get."
                ),
                action=Action(
                    label="Work out who buys this",
                    href=f"/app/products/{product_id}/audience",
                ),
            )
        )

    if processed:
        inherited.append(
            InheritedLine(
                label=f"Your material — {_plural(len(processed), 'file')}",
                href=f"/app/products/{product_id}/audience#material",
            )
        )
    else:
        missing.append(
            MissingInput(
                headline="Nothing uploaded",
                consequence=(
                    "Agents will only see your one-line description. Upload the "
                    "deck and they argue about the product instead."
                ),
                action=Action(
                    label="Upload your material",
                    href=f"/app/products/{product_id}/audience#upload",
                ),
            )
        )

    produced: str | None = None
    if finished_runs:
        latest = finished_runs[0]
        found = objection_counts.get(latest["id"])
        when = _short_date(latest.get("completed_at") or latest.get("created_at"))
        if found is not None:
            produced = _plural(found, "objection") + " found"
        else:
            # The run finished but nothing has been clustered out of it. Saying
            # "0 objections" would be a finding; this is the absence of one.
            produced = "Run finished, objections not worked out yet"
        if when:
            produced = f"{produced} · {when}"

    return StageState(
        id="reactions",
        number=2,
        label=STAGE_LABELS["reactions"],
        blurb=STAGE_BLURBS["reactions"],
        href=href,
        runnable="ready" if not missing else "degraded",
        produced=produced,
        inherited=inherited,
        missing=missing,
    )


def _build_answers(
    product_id: str,
    finished_runs: list[dict],
    objection_counts: dict[str, int],
    asset_counts: dict[str, int],
    results_by_parent: dict[str, list[dict]],
) -> StageState:
    href = f"/app/products/{product_id}/answers"

    with_objections = [
        run for run in finished_runs if objection_counts.get(run["id"], 0) > 0
    ]

    inherited: list[InheritedLine] = []
    missing: list[MissingInput] = []

    if with_objections:
        source = with_objections[0]
        count = objection_counts[source["id"]]
        when = _short_date(source.get("completed_at") or source.get("created_at"))
        label = f"Objections — {count} to answer"
        if when:
            label = f"{label}, from the run on {when}"
        inherited.append(
            InheritedLine(
                label=label,
                href=f"/app/products/{product_id}/reactions",
            )
        )
        runnable: Literal["ready", "degraded", "blocked"] = "ready"
    else:
        # The one stage where skipping ahead is meaningless rather than merely
        # weaker: you cannot draft an answer to an objection nobody raised.
        runnable = "blocked"
        missing.append(
            MissingInput(
                headline="There are no objections to answer yet",
                consequence=(
                    "This stage writes an answer to each thing people pushed "
                    "back on, publishes it, and runs the same room again to see "
                    "whether the objection died. With nothing to answer there is "
                    "nothing to test."
                ),
                action=Action(
                    label="Find out what they object to",
                    href=f"/app/products/{product_id}/reactions",
                ),
            )
        )

    produced: str | None = None
    drafted = sum(asset_counts.get(run["id"], 0) for run in finished_runs)
    tested = [
        result
        for run in finished_runs
        for result in results_by_parent.get(run["id"], [])
    ]
    if tested:
        effective = sum(r.get("assets_effective") or 0 for r in tested)
        total = sum(r.get("assets_tested") or 0 for r in tested)
        produced = f"{effective} of {total} answers actually moved the objection"
    elif drafted:
        produced = f"{_plural(drafted, 'answer')} drafted, none tested yet"

    return StageState(
        id="answers",
        number=3,
        label=STAGE_LABELS["answers"],
        blurb=STAGE_BLURBS["answers"],
        href=href,
        runnable=runnable,
        produced=produced,
        inherited=inherited,
        missing=missing,
    )


def _build_buyers(
    product_id: str,
    profile: dict | None,
    discovery_runs: list[dict],
) -> StageState:
    href = f"/app/products/{product_id}/buyers"

    inherited: list[InheritedLine] = []
    missing: list[MissingInput] = []

    confirmed = bool(profile and profile.get("confirmed_at"))

    if profile is not None:
        summary = _audience_summary(profile)
        inherited.append(
            InheritedLine(
                label=f"Audience — {summary}" if summary else "Audience",
                href=f"/app/products/{product_id}/audience",
            )
        )

    if not confirmed:
        missing.append(
            MissingInput(
                headline=(
                    "Your audience is not confirmed"
                    if profile is not None
                    else "No audience worked out yet"
                ),
                consequence=(
                    "We'll search from our guess at your buyer. Confirm the "
                    "audience first and the list gets sharper."
                ),
                action=Action(
                    label=(
                        "Read it and confirm"
                        if profile is not None
                        else "Work out who buys this"
                    ),
                    href=f"/app/products/{product_id}/audience",
                ),
            )
        )

    produced: str | None = None
    completed = [r for r in discovery_runs if r.get("status") in DISCOVERY_FINISHED]
    if completed:
        found = sum(r.get("candidates_found") or 0 for r in completed)
        when = _short_date(completed[0].get("created_at"))
        produced = f"{_plural(found, 'company', 'companies')} found"
        if when:
            produced = f"{produced} · last searched {when}"

    return StageState(
        id="buyers",
        number=4,
        label=STAGE_LABELS["buyers"],
        blurb=STAGE_BLURBS["buyers"],
        href=href,
        runnable="ready" if not missing else "degraded",
        produced=produced,
        inherited=inherited,
        missing=missing,
    )


def _scoreboard_of(row: dict) -> dict | None:
    """The scoreboard sub-object from a `artifact->scoreboard` select."""
    board = row.get("scoreboard")
    return board if isinstance(board, dict) else None


def _build_messages(
    product_id: str,
    profile: dict | None,
    finished_runs: list[dict],
    scoreboards: dict[str, dict],
) -> StageState:
    href = f"/app/products/{product_id}/messages"

    inherited: list[InheritedLine] = []
    missing: list[MissingInput] = []

    if profile is not None:
        summary = _audience_summary(profile)
        inherited.append(
            InheritedLine(
                label=f"Audience — {summary}" if summary else "Audience",
                href=f"/app/products/{product_id}/audience",
            )
        )
    else:
        missing.append(
            MissingInput(
                headline="No audience worked out yet",
                consequence=(
                    "Every version gets shown to the same room, so the "
                    "comparison is fair either way — but the room will be a "
                    "general business audience rather than your buyers."
                ),
                action=Action(
                    label="Work out who buys this",
                    href=f"/app/products/{product_id}/audience",
                ),
            )
        )

    produced: str | None = None
    compared = [
        run for run in finished_runs if (run.get("variants") or 1) > 1
    ]
    if compared:
        latest = compared[0]
        board = scoreboards.get(latest["id"])
        versions = latest.get("variants") or 0
        if board is None:
            produced = f"{_plural(versions, 'version')} tested"
        elif board.get("winner_variant_key"):
            produced = f"{_plural(versions, 'version')} tested — one came out ahead"
        else:
            produced = (
                f"{_plural(versions, 'version')} tested — too close to call"
            )

    return StageState(
        id="messages",
        number=5,
        label=STAGE_LABELS["messages"],
        blurb=STAGE_BLURBS["messages"],
        href=href,
        runnable="ready" if not missing else "degraded",
        produced=produced,
        inherited=inherited,
        missing=missing,
    )


# ---------------------------------------------------------------------------
# Attention
# ---------------------------------------------------------------------------

def _attention_lines(
    product_id: str,
    docs: list[dict],
    finished_runs: list[dict],
    objection_counts: dict[str, int],
    scoreboards: dict[str, dict],
    discovery_runs: list[dict],
    now: datetime,
) -> list[AttentionLine]:
    """Only things a row says. Nothing is manufactured to fill the card."""
    lines: list[AttentionLine] = []

    if finished_runs:
        latest = finished_runs[0]
        found = objection_counts.get(latest["id"])
        if found:
            lines.append(
                AttentionLine(
                    kind="run_finished",
                    weight="high",
                    text=f"Run finished. {_plural(found, 'objection')} found.",
                    href=f"/app/products/{product_id}/reactions",
                )
            )

    for run in finished_runs:
        board = scoreboards.get(run["id"])
        if board is None:
            continue
        if (run.get("variants") or 1) > 1 and not board.get("winner_variant_key"):
            lines.append(
                AttentionLine(
                    kind="message_test_unresolved",
                    weight="high",
                    text=(
                        "Message test unresolved — the versions were too close "
                        "to call."
                    ),
                    href=f"/app/products/{product_id}/messages",
                )
            )
            break

    completed_searches = [
        r for r in discovery_runs if r.get("status") in DISCOVERY_FINISHED
    ]
    if completed_searches:
        newest = _iso_to_dt(completed_searches[0].get("created_at"))
        if newest is not None and now - newest > CANDIDATE_LIST_STALE_AFTER:
            days = (now - newest).days
            lines.append(
                AttentionLine(
                    kind="buyers_stale",
                    text=f"Buyers list last refreshed {days} days ago.",
                    href=f"/app/products/{product_id}/buyers",
                )
            )

    still_reading = [
        d for d in docs if d.get("processing_status") in DOCUMENT_IN_FLIGHT
    ]
    if still_reading:
        lines.append(
            AttentionLine(
                kind="documents_processing",
                text=(
                    f"{_plural(len(still_reading), 'document')} still being read."
                ),
                href=f"/app/products/{product_id}/audience#material",
            )
        )

    failed = [d for d in docs if d.get("processing_status") in DOCUMENT_FAILED]
    if failed:
        lines.append(
            AttentionLine(
                kind="documents_failed",
                weight="high",
                text=(
                    f"{_plural(len(failed), 'file')} could not be read. "
                    "Nothing in them reached your audience."
                ),
                href=f"/app/products/{product_id}/audience#material",
            )
        )

    lines.sort(key=lambda line: 0 if line.weight == "high" else 1)
    return lines


# ---------------------------------------------------------------------------
# Axis B
# ---------------------------------------------------------------------------

DEFAULT_MOMENT = "pre_launch_positioning"


def _moment(runs: list[dict]) -> Moment:
    """Where the company is. Defaults to whatever the last run used.

    Asked per run rather than set once on the product: a founder moves from
    pre-launch to growth without starting over, and the same product at a
    different moment wants a different audience mix.
    """
    for run in runs:
        stage_id = run.get("founder_stage")
        spec = FOUNDER_STAGES.get(stage_id) if stage_id else None
        if spec is not None:
            return Moment(id=spec.id, label=spec.label, source="last_run")
    spec = FOUNDER_STAGES[DEFAULT_MOMENT]
    return Moment(id=spec.id, label=spec.label, source="default")


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def _check_invariants(product_id: str, stages: list[StageState]) -> None:
    """A stage states what it inherited or what is missing. Never neither.

    Logged rather than raised: a card that renders with one silent stage is a
    worse outcome than a card that does not render at all only in the sense that
    it is quieter, and the fix is to know about it. `tests/test_stage_state.py`
    turns this into a hard assertion so it cannot ship.
    """
    for stage in stages:
        if not stage.inherited and not stage.missing:
            log.error(
                "stage_declares_nothing",
                product_id=product_id,
                stage=stage.id,
                runnable=stage.runnable,
            )
        if stage.runnable == "blocked" and not any(m.action for m in stage.missing):
            log.error(
                "blocked_stage_has_no_way_forward",
                product_id=product_id,
                stage=stage.id,
            )


def _state_for_project(project: dict, data: _OrgData, now: datetime) -> ProductState:
    product_id = str(project["id"])

    docs = [d for d in data.documents if str(d.get("project_id")) == product_id]

    profiles = [p for p in data.profiles if str(p.get("project_id")) == product_id]
    profiles.sort(key=lambda p: str(p.get("created_at") or ""), reverse=True)
    profile = profiles[0] if profiles else None

    sims = [s for s in data.simulations if str(s.get("project_id")) == product_id]
    sims.sort(
        key=lambda s: str(s.get("completed_at") or s.get("created_at") or ""),
        reverse=True,
    )
    # A re-simulation is not a run whose reactions you read. It exists to answer
    # the parent's objections, and its own output is the before-and-after that
    # stage 3 reports. Including it here read as the newest run on a product
    # that had answered its objections, so stage 2 announced "objections not
    # worked out yet" about a run that was never going to have any of its own,
    # and stage 5 lost the scoreboard because that lives on the parent. Found by
    # looking at the deployed rail against a seeded product, not by a test.
    finished = [
        s
        for s in sims
        if s.get("status") in RUN_FINISHED and not s.get("parent_simulation_id")
    ]

    objection_counts: dict[str, int] = defaultdict(int)
    for row in data.objections:
        objection_counts[str(row["simulation_id"])] += 1

    asset_counts: dict[str, int] = defaultdict(int)
    for row in data.assets:
        asset_counts[str(row["simulation_id"])] += 1

    results_by_parent: dict[str, list[dict]] = defaultdict(list)
    for row in data.inoculation_results:
        results_by_parent[str(row["parent_simulation_id"])].append(row)

    scoreboards: dict[str, dict] = {}
    for row in data.analyses:
        board = _scoreboard_of(row)
        if board is not None:
            scoreboards[str(row["simulation_id"])] = board

    runs = [
        r for r in data.discovery_runs if str(r.get("project_id")) == product_id
    ]
    runs.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)

    stages = [
        _build_audience(product_id, docs, profile),
        _build_reactions(product_id, docs, profile, finished, objection_counts),
        _build_answers(
            product_id, finished, objection_counts, asset_counts, results_by_parent
        ),
        _build_buyers(product_id, profile, runs),
        _build_messages(product_id, profile, finished, scoreboards),
    ]
    _check_invariants(product_id, stages)

    return ProductState(
        id=product_id,
        name=project.get("name") or "Untitled product",
        description=project.get("description"),
        moment=_moment(sims),
        stages=stages,
        stages_ready=sum(1 for s in stages if s.runnable == "ready"),
        attention=_attention_lines(
            product_id,
            docs,
            finished,
            objection_counts,
            scoreboards,
            runs,
            now,
        ),
    )


def build_product_states(
    org_id: str, projects: list[dict], *, now: datetime | None = None
) -> list[ProductState]:
    """Every product's rail, in one pass over the org's rows."""
    if not projects:
        return []
    moment = now or datetime.now(UTC)
    data = _OrgData(org_id, [str(p["id"]) for p in projects])
    return [_state_for_project(project, data, moment) for project in projects]


def build_product_state(
    org_id: str, project: dict, *, now: datetime | None = None
) -> ProductState:
    """One product's rail."""
    return build_product_states(org_id, [project], now=now)[0]
