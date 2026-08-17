# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# run_clearance_tracks(client, plan, item, tier, competitors, search_date)
#     -> ClearanceResult                                    [async]
# ClearanceResult and its parts (QueryRecord, TrademarkFindings, ArtEntry, …)
# DEEP_READS — deep reads per tier (the skill's tier table, as code)
# ─────────────────────────────────────────────────────────
"""The clearance tracks: the skill's methodology, executed against the client.

Track A trademarks, Track B prior art (keyword sweep → CPC sweep → assignee
sweep → claim deep-reads), Track C pending-landscape honesty, Track D examiner
behavior — with the count-triage rules from the skill's query-patterns
reference: a zero-hit query is broadened once and BOTH queries are recorded; a
>1,000-hit query is narrowed and both are recorded; two well-formed zero-hit
queries on different axes are reported as a whitespace signal rather than a
failure.

Everything numeric or factual in the result comes from client responses —
titles, owners, counts, dates — or from LLM analysis OF client-fetched claim
text. Nothing is fabricated, empty results are reported as empty, and "no
results for these queries" is kept distinct from "no prior art exists".

`search_date` is an argument, never `datetime.now()` read deep in the logic:
the blind-spot arithmetic and the artifact's date-stamp must come from the
run's declared date so a re-run of a stored search record reproduces the same
report.
"""
from __future__ import annotations

import re
from calendar import monthrange
from datetime import date
from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, Field

from app.services.clearance.claim_reader import read_claims
from app.services.clearance.query_plan import QueryPlan
from app.services.clearance.uspto_client import TRADEMARK_SEARCH_LINK, ClearanceConfigError

if TYPE_CHECKING:
    from app.services.clearance.uspto_client import AppRecord, UsptoClient

logger = structlog.get_logger()

TIERS = ("QUICK", "STANDARD", "COMPREHENSIVE")

# The skill's tier table, as code: QUICK is the keyword-only teaser, STANDARD
# reads 3–5 references at claim level, COMPREHENSIVE 5–7. The value is the
# ceiling; the floor is however many close references actually exist — reading
# fewer because the art is thin is honest, padding to a count is not.
DEEP_READS = {"QUICK": 0, "STANDARD": 5, "COMPREHENSIVE": 7}

# Count-triage thresholds from the skill's query-patterns reference.
BROAD_HIT_CEILING = 1_000

# Items requested per search. QUICK is the "top-10 sweep, one screen" teaser.
SCREEN_LIMIT = 25
QUICK_SCREEN_LIMIT = 10

# Caps on derived sweeps so a plan cannot fan out into unbounded API calls.
MAX_CPC_SWEEPS = 4
MAX_ASSIGNEE_SWEEPS = 8
MAX_NOTABLE_PENDING = 10
MAX_WATCH_ITEMS = 12

# Status substrings that mean a reference is no longer live. Dead art is still
# prior art, but it blocks nothing (skill risk-tier definitions).
_DEAD_MARKERS = ("abandon", "expire", "withdraw", "cancel")

_STOPWORDS = frozenset(
    {"and", "or", "not", "the", "for", "with", "method", "system", "apparatus"}
)


class QueryRecord(BaseModel):
    track: str  # patents | trademark | examiner_behavior
    query: str
    hits: int


class TrademarkConflict(BaseModel):
    mark: str
    serial_or_reg: str
    owner: str
    live: bool
    classes: list[str] = Field(default_factory=list)
    goods_services: str = ""
    similarity: str = "close"  # identical | close | related-goods


class TrademarkFindings(BaseModel):
    status: str  # CLEAR_ON_SEARCH | CONFLICTS_FOUND | NEEDS_REVIEW | NOT_SEARCHED
    marks_checked: list[str] = Field(default_factory=list)
    conflicts: list[TrademarkConflict] = Field(default_factory=list)
    official_search_link: str | None = None


class ArtEntry(BaseModel):
    number: str
    title: str = ""
    assignee: str = ""
    filed: str = ""
    priority: str | None = None
    status: str = ""
    live: bool = True
    claim_requirements: str = ""
    differences: str = ""
    risk: str = "YELLOW"
    rationale: str = ""


class PendingApp(BaseModel):
    app: str
    title: str = ""
    assignee: str = ""
    status: str = ""


class ProvisionalPriority(BaseModel):
    provisional: str
    via: str  # the reference whose continuity revealed it


class WatchItem(BaseModel):
    target: str
    reason: str


class ClearanceResult(BaseModel):
    tracks_run: list[str] = Field(default_factory=list)
    trademark: TrademarkFindings | None = None
    overall_risk: str = "GREEN"
    records_screened: int = 0
    closest_art: list[ArtEntry] = Field(default_factory=list)
    whitespace_signals: list[str] = Field(default_factory=list)
    crowded_areas: list[str] = Field(default_factory=list)
    notable_pending: list[PendingApp] = Field(default_factory=list)
    provisional_priorities: list[ProvisionalPriority] = Field(default_factory=list)
    blind_spot_date: str = ""
    queries_run: list[QueryRecord] = Field(default_factory=list)
    watch_list: list[WatchItem] = Field(default_factory=list)
    examiner_notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Query mechanics
# ---------------------------------------------------------------------------

def _terms(query: str) -> list[str]:
    """Meaningful search terms of a query: quoted phrases and bare words,
    minus boolean operators, punctuation, and generic patent-ese stopwords."""
    parts = re.findall(r'"([^"]+)"|([A-Za-z][\w-]{2,})', query)
    out: list[str] = []
    for phrase, word in parts:
        term = (phrase or word).strip().lower()
        if term and term not in _STOPWORDS and term not in out:
            out.append(term)
    return out


def _clauses(query: str) -> list[str]:
    """Top-level AND clauses; the unit the triage rules add and drop."""
    return [c.strip() for c in re.split(r"\s+AND\s+", query) if c.strip()]


def _broaden(query: str) -> str | None:
    """One broadening step for a zero-hit query: drop the last qualifier.

    The skill's rule is drop-a-qualifier / swap-a-synonym; dropping the final
    AND clause (or, for a single-clause query, the final term) is the
    deterministic version — synonym swaps already exist in the plan as the
    other phrasings of the same axis. Returns None when nothing is left to
    drop, which the caller records as a confirmed zero.
    """
    clauses = _clauses(query)
    if len(clauses) > 1:
        return " AND ".join(clauses[:-1])
    parts = re.findall(r'"[^"]+"|\S+', query)
    if len(parts) > 1:
        return " ".join(parts[:-1])
    return None


def _narrow(query: str, axis: str, plan: QueryPlan) -> str | None:
    """One narrowing step for a >1,000-hit query: add a qualifier from another
    axis (the skill's "add DOMAIN + FUNCTION together" rule). Returns None when
    the plan has no other-axis term that is not already in the query."""
    source_axis = "FUNCTION" if axis != "FUNCTION" else "DOMAIN"
    existing = set(_terms(query))
    for planned in plan.queries:
        if planned.axis != source_axis:
            continue
        for term in _terms(planned.query):
            if term not in existing:
                qualifier = f'"{term}"' if " " in term else term
                return f"{query} AND {qualifier}"
    return None


def _plan_terms(plan: QueryPlan) -> list[str]:
    """Every distinct term across the plan's queries, order preserved.

    Deduped so a term the plan phrases twice does not count twice in the
    closeness score — the score ranks records, not phrasings.
    """
    return list(
        dict.fromkeys(
            term for planned in plan.queries for term in _terms(planned.query)
        )
    )


def _is_live(status: str | None) -> bool:
    lowered = (status or "").lower()
    return not any(marker in lowered for marker in _DEAD_MARKERS)


def _minus_18_months(search_date: str) -> str:
    """The publication blind-spot boundary: the search date minus 18 months.

    Filings after this date are largely unpublished (the ~18-month publication
    lag), so the report must say the window out loud with a real date. Raises
    on an unparseable date rather than inventing one — a fabricated date in
    the blind-spot sentence is exactly the class of output the skill forbids.
    """
    try:
        anchor = date.fromisoformat(search_date.strip()[:10])
    except ValueError as exc:
        raise ValueError(
            f"search_date must start with YYYY-MM-DD, got {search_date!r}"
        ) from exc
    months = anchor.year * 12 + (anchor.month - 1) - 18
    year, month = months // 12, months % 12 + 1
    day = min(anchor.day, monthrange(year, month)[1])
    return date(year, month, day).isoformat()


# ---------------------------------------------------------------------------
# Deep-read ranking
# ---------------------------------------------------------------------------

def _closeness(record: AppRecord, plan_terms: list[str], source_count: int) -> float:
    """Closeness score used to pick the deep-read references.

    The heuristic, in order of weight:

    - **Keyword density in the title** — +2.0 per distinct plan term found in
      the title. The title is the only text every ODP record is guaranteed to
      carry, and metadata-level search is the declared scope of this stage.
    - **Keyword density in the abstract** — +1.0 per distinct plan term found
      in the record's abstract text when the raw record carries one.
    - **Live status** — +1.5 when the record is not abandoned/expired/
      withdrawn. A live reference can block; a dead one is prior art only, so
      between two equally-worded records the live one is the one to read.
    - **Query multiplicity** — +0.5 per additional query that surfaced the
      same record (capped at +1.5). A record that three differently-phrased
      queries all found is close to the item's substance, not to one phrasing.
    """
    title = (record.title or "").lower()
    raw = record.raw if isinstance(record.raw, dict) else {}
    abstract = str(
        raw.get("abstractText") or raw.get("abstract") or ""
    ).lower()

    score = 0.0
    for term in plan_terms:
        if term in title:
            score += 2.0
        elif abstract and term in abstract:
            score += 1.0
    if _is_live(record.status):
        score += 1.5
    score += min(1.5, 0.5 * max(0, source_count - 1))
    return score


# ---------------------------------------------------------------------------
# Track A — trademarks
# ---------------------------------------------------------------------------

async def _track_a(
    client: UsptoClient, marks: list[str], queries_run: list[QueryRecord]
) -> TrademarkFindings:
    """The trademark check, honest about what the client can actually search.

    The USPTO retired its public word-mark search API; the client exposes
    status lookup by serial number only (see `uspto_client`'s module
    docstring). Without a word search — no TSDR key, or no `search_trademarks`
    capability on the client — the only honest status is NOT_SEARCHED with the
    official search link. Never "clear" without an actual search result: the
    skill's Track A rule 4.
    """
    word_search = getattr(client, "search_trademarks", None)
    if not client.tsdr_available or word_search is None:
        return TrademarkFindings(
            status="NOT_SEARCHED",
            marks_checked=marks,
            conflicts=[],
            official_search_link=TRADEMARK_SEARCH_LINK,
        )

    conflicts: list[TrademarkConflict] = []
    for mark in marks:
        hits = await word_search(mark)
        queries_run.append(QueryRecord(track="trademark", query=mark, hits=len(hits)))
        for hit in hits:
            found = (hit.mark or "").strip()
            conflicts.append(
                TrademarkConflict(
                    mark=found,
                    serial_or_reg=hit.serial,
                    owner=hit.owner or "",
                    live=bool(hit.live),
                    classes=[str(c) for c in hit.classes],
                    goods_services=hit.goods_services or "",
                    similarity=(
                        "identical" if found.lower() == mark.strip().lower() else "close"
                    ),
                )
            )

    if any(c.live for c in conflicts):
        status = "CONFLICTS_FOUND"
    elif conflicts:
        # Dead-only hits: nothing live blocks, but a graveyard of the same
        # name is worth a human look before adopting it.
        status = "NEEDS_REVIEW"
    else:
        status = "CLEAR_ON_SEARCH"
    return TrademarkFindings(
        status=status,
        marks_checked=marks,
        conflicts=conflicts,
        official_search_link=TRADEMARK_SEARCH_LINK,
    )


# ---------------------------------------------------------------------------
# Track B/C/D machinery
# ---------------------------------------------------------------------------

class _Screen:
    """Accumulates every screened record and which queries surfaced it."""

    def __init__(self) -> None:
        self.records: dict[str, AppRecord] = {}
        self.sources: dict[str, set[str]] = {}

    def add(self, items: list[AppRecord], query: str) -> None:
        for record in items:
            number = record.app_number
            if not number:
                continue
            self.records.setdefault(number, record)
            self.sources.setdefault(number, set()).add(query)


async def _run_query(
    client: UsptoClient,
    query: str,
    limit: int,
    queries_run: list[QueryRecord],
    screen: _Screen,
) -> int:
    """Execute one search, record it (every query is part of the deliverable),
    and screen its items. Returns the hit count."""
    result = await client.search_applications(query, limit=limit)
    queries_run.append(QueryRecord(track="patents", query=query, hits=result.total))
    if 0 < result.total <= BROAD_HIT_CEILING:
        screen.add(result.items, query)
    return result.total


async def _keyword_sweep(
    client: UsptoClient,
    plan: QueryPlan,
    tier: str,
    queries_run: list[QueryRecord],
    screen: _Screen,
) -> tuple[list[str], list[str]]:
    """The Stage-1 phrasings, with count triage. Returns (whitespace_signals,
    crowded_areas)."""
    limit = QUICK_SCREEN_LIMIT if tier == "QUICK" else SCREEN_LIMIT
    zero_axes: dict[str, str] = {}  # axis -> the query that confirmed the zero
    crowded: list[str] = []

    for planned in plan.queries:
        if planned.track != "patents":
            continue
        total = await _run_query(client, planned.query, limit, queries_run, screen)

        if total == 0:
            broadened = _broaden(planned.query)
            if broadened:
                rerun = await _run_query(client, broadened, limit, queries_run, screen)
                if rerun == 0:
                    zero_axes.setdefault(planned.axis, planned.query)
            else:
                zero_axes.setdefault(planned.axis, planned.query)
        elif total > BROAD_HIT_CEILING:
            narrowed = _narrow(planned.query, planned.axis, plan)
            if narrowed:
                rerun = await _run_query(client, narrowed, limit, queries_run, screen)
                crowded.append(
                    f'"{planned.query}" matched {total} records — too generic to '
                    f'read as a finding; narrowed to "{narrowed}" ({rerun} records)'
                )
            # A bare >1,000 count is never reported as a crowded field without
            # a narrowed follow-up (query-patterns count-triage rule).

    # Two well-formed zero-hit queries on DIFFERENT axes = whitespace signal.
    # One zero axis alone is just a query that found nothing.
    whitespace: list[str] = []
    if len(zero_axes) >= 2:
        whitespace = [
            f'no hits on the {axis} axis: "{query}" and its broadened form both '
            "returned zero results"
            for axis, query in sorted(zero_axes.items())
        ]
    return whitespace, crowded


async def _cpc_sweep(
    client: UsptoClient,
    plan: QueryPlan,
    queries_run: list[QueryRecord],
    screen: _Screen,
) -> list[str]:
    """Candidate CPC prefixes × 1–2 FUNCTION keywords. Returns classes swept."""
    function_terms = [
        term
        for planned in plan.queries
        if planned.axis == "FUNCTION"
        for term in _terms(planned.query)
    ]
    keywords = function_terms[:2]
    if not keywords:
        return []

    swept: list[str] = []
    for cpc in plan.candidate_cpc[:MAX_CPC_SWEEPS]:
        quoted = [f'"{kw}"' if " " in kw else kw for kw in keywords]
        joined = f"({' OR '.join(quoted)})" if len(quoted) > 1 else quoted[0]
        query = f"cpcClassificationBag:{cpc} AND {joined}"
        await _run_query(client, query, SCREEN_LIMIT, queries_run, screen)
        swept.append(cpc)
    return swept


async def _assignee_sweep(
    client: UsptoClient,
    names: list[str],
    queries_run: list[QueryRecord],
    screen: _Screen,
) -> list[str]:
    """Sweep filings by applicant name — catches filings whose titles hide the
    ball. Query syntax per the client's ODP field map: `firstApplicantName`."""
    swept: list[str] = []
    for name in names[:MAX_ASSIGNEE_SWEEPS]:
        cleaned = name.strip()
        if not cleaned:
            continue
        query = f'firstApplicantName:"{cleaned}"'
        await _run_query(client, query, SCREEN_LIMIT, queries_run, screen)
        swept.append(cleaned)
    return swept


def _repeat_assignees(screen: _Screen, already: list[str]) -> list[str]:
    """Assignees appearing on ≥2 screened records, minus ones already swept."""
    skip = {name.strip().lower() for name in already}
    counts: dict[str, int] = {}
    for record in screen.records.values():
        name = (record.assignee or "").strip()
        if name and name.lower() not in skip:
            counts[name] = counts.get(name, 0) + 1
    return [name for name, n in sorted(counts.items(), key=lambda kv: -kv[1]) if n >= 2]


async def _deep_read(
    client: UsptoClient,
    plan: QueryPlan,
    item: str,
    tier: str,
    screen: _Screen,
    organization_id: str | None,
) -> list[ArtEntry]:
    """Claim-level reads of the closest references (ranking: `_closeness`)."""
    budget = DEEP_READS.get(tier, DEEP_READS["STANDARD"])
    if budget == 0 or not screen.records:
        return []

    plan_terms = _plan_terms(plan)
    ranked = sorted(
        screen.records.values(),
        key=lambda r: _closeness(r, plan_terms, len(screen.sources.get(r.app_number, ()))),
        reverse=True,
    )

    entries: list[ArtEntry] = []
    for record in ranked[:budget]:
        live = _is_live(record.status)
        claims_text = await client.get_claims_text(record)
        if claims_text:
            reading = await read_claims(
                item, record, claims_text, organization_id=organization_id
            )
            requirements, differences = reading.claim_requirements, reading.differences
            risk, rationale = reading.risk, reading.rationale
        else:
            # No claims text is a fact to report, not a gap to paper over. The
            # honest tier for an unread close reference is YELLOW if it could
            # block (live) and GREEN if it cannot (dead).
            requirements = (
                "Claims text could not be retrieved for this reference — it was "
                "not reviewed at claim level."
            )
            differences = ""
            risk = "YELLOW" if live else "GREEN"
            rationale = (
                "A close reference whose claims could not be fetched warrants "
                "review by counsel."
                if live
                else "This reference is no longer live, so it blocks nothing, "
                "though it remains prior art."
            )
        entries.append(
            ArtEntry(
                number=record.grant_number
                or record.publication_number
                or record.app_number,
                title=record.title or "",
                assignee=record.assignee or "",
                filed=record.filed or "",
                priority=None,  # filled from continuity in Track C
                status=record.status or "",
                live=live,
                claim_requirements=requirements,
                differences=differences,
                risk=risk,
                rationale=rationale,
            )
        )
    return entries


_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


async def _track_c(
    client: UsptoClient,
    screen: _Screen,
    closest_art: list[ArtEntry],
    plan: QueryPlan,
) -> tuple[list[PendingApp], list[ProvisionalPriority]]:
    """Pending landscape: flag live pending/allowed applications from the
    sweeps, and pull continuity on the deep-read references to expose
    provisional priority claims (provisionals are never published; a later
    application claiming priority to one is the only way they surface)."""
    plan_terms = _plan_terms(plan)
    pending_candidates = [
        record
        for record in screen.records.values()
        if not record.grant_number and _is_live(record.status)
    ]
    pending_candidates.sort(
        key=lambda r: _closeness(r, plan_terms, len(screen.sources.get(r.app_number, ()))),
        reverse=True,
    )
    notable = [
        PendingApp(
            app=record.app_number,
            title=record.title or "",
            assignee=record.assignee or "",
            status=record.status or "",
        )
        for record in pending_candidates[:MAX_NOTABLE_PENDING]
    ]

    provisionals: list[ProvisionalPriority] = []
    number_by_app = {
        (r.grant_number or r.publication_number or r.app_number): r.app_number
        for r in screen.records.values()
    }
    for entry in closest_art:
        app_number = number_by_app.get(entry.number, entry.number)
        continuity = await client.get_continuity(app_number)
        if not isinstance(continuity, dict):
            continue
        bag = continuity.get("parentContinuityBag") or []
        parent_dates: list[str] = []
        for parent in bag if isinstance(bag, list) else []:
            if not isinstance(parent, dict):
                continue
            parent_number = str(
                parent.get("parentApplicationNumberText")
                or parent.get("applicationNumberText")
                or ""
            ).strip()
            if not parent_number:
                continue
            blob = str(parent).lower()
            if "provisional" in blob or parent_number[:2] in {"60", "61", "62", "63"}:
                provisionals.append(
                    ProvisionalPriority(provisional=parent_number, via=entry.number)
                )
            for value in parent.values():
                if isinstance(value, str):
                    parent_dates.extend(_ISO_DATE.findall(value))
        if parent_dates and entry.priority is None:
            # Earliest parent filing date in the chain — the priority date a
            # freedom-to-operate read actually competes with.
            entry.priority = min(parent_dates)
    return notable, provisionals


_SECTION_CODES = ("101", "102", "103", "112")
_SECTION_MEANING = {
    "101": "subject-matter eligibility (section 101)",
    "102": "anticipation (section 102)",
    "103": "obviousness (section 103)",
    "112": "clarity or written support (section 112)",
}


async def _track_d(
    client: UsptoClient, plan: QueryPlan, queries_run: list[QueryRecord]
) -> list[str]:
    """Examiner behavior on the close art (COMPREHENSIVE only): how examiners
    reject similar claims, and whether granted patents in the area have
    survived PTAB review."""
    function_queries = [q.query for q in plan.queries if q.axis == "FUNCTION"]
    seed = function_queries[0] if function_queries else (
        plan.queries[0].query if plan.queries else ""
    )
    if not seed:
        return []

    notes: list[str] = []

    rejections = await client.search_rejections(seed, limit=20)
    queries_run.append(
        QueryRecord(track="examiner_behavior", query=seed, hits=len(rejections))
    )
    if rejections:
        counts = dict.fromkeys(_SECTION_CODES, 0)
        for row in rejections:
            blob = str(row)
            for code in _SECTION_CODES:
                if re.search(rf"\b{code}\b", blob):
                    counts[code] += 1
        breakdown = ", ".join(
            f"{n} cite {_SECTION_MEANING[code]}" for code, n in counts.items() if n
        )
        notes.append(
            f"Across {len(rejections)} recent examiner rejection records for "
            f"similar claims: {breakdown or 'no statutory basis was stated in the records'}."
        )
    else:
        notes.append(
            "No examiner rejection records surfaced for this art — a result of "
            "these queries, not proof of an easy path to grant."
        )

    ptab = await client.search_ptab(seed, limit=20)
    queries_run.append(
        QueryRecord(track="examiner_behavior", query=seed, hits=len(ptab))
    )
    if ptab:
        notes.append(
            f"{len(ptab)} PTAB trial proceedings touch this art. Claims that "
            "survived review are strong against challenge; claims that were "
            "invalidated are free to practice."
        )
    else:
        notes.append(
            "No PTAB trial proceedings surfaced for this art with these queries."
        )
    return notes


def _rollup(closest_art: list[ArtEntry]) -> str:
    """Overall risk from the deep-read tiers, liveness applied.

    RED needs a live RED reference — a dead reference cannot block, whatever
    its claims once covered (it remains prior art, which the per-reference
    entry says). YELLOW needs a live YELLOW. Everything else — including a run
    with no deep reads at all, whose limitations section says exactly that —
    is GREEN.
    """
    live = [entry for entry in closest_art if entry.live]
    if any(entry.risk == "RED" for entry in live):
        return "RED"
    if any(entry.risk == "YELLOW" for entry in live):
        return "YELLOW"
    return "GREEN"


# ---------------------------------------------------------------------------
# The orchestrator
# ---------------------------------------------------------------------------

async def run_clearance_tracks(
    client: UsptoClient,
    plan: QueryPlan,
    item: str,
    tier: str,
    competitors: list[str],
    search_date: str,
    *,
    organization_id: str | None = None,
) -> ClearanceResult:
    """Execute the clearance tracks for one plan. See the module docstring.

    Degrades honestly rather than silently: no ODP key raises
    `ClearanceConfigError` before any track runs (a patent search that cannot
    search is not a cheaper report, it is no report), and no TSDR word-search
    capability makes Track A report NOT_SEARCHED with the official link.
    """
    tier = (tier or "STANDARD").strip().upper()
    if tier not in TIERS:
        raise ValueError(f"tier must be one of {TIERS}, got {tier!r}")
    if not client.odp_available:
        raise ClearanceConfigError(
            "the USPTO Open Data Portal key is not configured — the patent "
            "tracks cannot run, and running only the rest would misrepresent "
            "the report's coverage"
        )
    blind_spot_date = _minus_18_months(search_date)  # fail fast on a bad date

    queries_run: list[QueryRecord] = []
    screen = _Screen()
    tracks_run: list[str] = []

    # Track A — trademarks, when a name is present.
    trademark: TrademarkFindings | None = None
    if plan.marks_to_check:
        trademark = await _track_a(client, plan.marks_to_check, queries_run)
        tracks_run.append("trademark")

    # Track B — keyword sweep with count triage, then CPC and assignee sweeps.
    tracks_run.append("patents")
    whitespace, crowded = await _keyword_sweep(
        client, plan, tier, queries_run, screen
    )

    cpc_swept: list[str] = []
    assignees_swept: list[str] = []
    if tier != "QUICK":
        cpc_swept = await _cpc_sweep(client, plan, queries_run, screen)
        # Competitors the caller named are swept at STANDARD and up — the
        # input contract promises it. The ≥2×-repeat-assignee discovery sweep
        # is COMPREHENSIVE, per the skill's tier table.
        assignees_swept = await _assignee_sweep(
            client, competitors, queries_run, screen
        )
        if tier == "COMPREHENSIVE":
            assignees_swept += await _assignee_sweep(
                client, _repeat_assignees(screen, assignees_swept), queries_run, screen
            )

    closest_art = await _deep_read(
        client, plan, item, tier, screen, organization_id
    )

    # Track C — pending landscape (STANDARD and up; the blind-spot date is
    # computed for every tier because the honesty statement costs nothing).
    notable_pending: list[PendingApp] = []
    provisionals: list[ProvisionalPriority] = []
    if tier != "QUICK":
        tracks_run.append("pending_landscape")
        notable_pending, provisionals = await _track_c(
            client, screen, closest_art, plan
        )

    # Track D — examiner behavior (COMPREHENSIVE only).
    examiner_notes: list[str] = []
    if tier == "COMPREHENSIVE":
        tracks_run.append("examiner_behavior")
        examiner_notes = await _track_d(client, plan, queries_run)

    watch_list: list[WatchItem] = []
    if tier == "COMPREHENSIVE":
        watch_list = [
            WatchItem(
                target=pending.app,
                reason="a live application close to the item; its claims can "
                "still change before grant",
            )
            for pending in notable_pending[: MAX_WATCH_ITEMS // 2]
        ] + [
            WatchItem(
                target=assignee,
                reason="a repeat filer in this art — new filings from them are "
                "the ones to watch",
            )
            for assignee in _repeat_assignees(screen, [])[: MAX_WATCH_ITEMS // 2]
        ]

    result = ClearanceResult(
        tracks_run=tracks_run,
        trademark=trademark,
        overall_risk=_rollup(closest_art),
        records_screened=len(screen.records),
        closest_art=closest_art,
        whitespace_signals=whitespace,
        crowded_areas=crowded,
        notable_pending=notable_pending,
        provisional_priorities=provisionals,
        blind_spot_date=blind_spot_date,
        queries_run=queries_run,
        watch_list=watch_list,
        examiner_notes=examiner_notes,
    )
    logger.info(
        "clearance_tracks_complete",
        tier=tier,
        tracks_run=tracks_run,
        queries_run=len(queries_run),
        records_screened=result.records_screened,
        deep_reads=len(closest_art),
        overall_risk=result.overall_risk,
        cpc_swept=cpc_swept,
        assignees_swept=assignees_swept,
        trademark_status=trademark.status if trademark else None,
    )
    return result
