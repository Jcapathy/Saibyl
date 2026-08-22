# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# build_artifact(item, tier, search_date, assumptions, result) -> dict
# compose_report_markdown(artifact) -> str
# DISCLAIMER, SKILL_NAME, SCHEMA_VERSION
# ─────────────────────────────────────────────────────────
"""The clearance run's two outputs: the exact JSON contract, and the report.

The JSON payload is the skill's output contract byte for byte in shape: every
key present on every run (null/empty rather than omitted), `queries_run`
complete — including zero-hit queries and the too-broad ones that were
narrowed — so any run is reproducible and auditable, and the disclaimer
verbatim. The markdown report follows the contract's eight sections and is
written for a founder: no word from the banned-vocabulary list the rest of the
product is held to (`test_report_vocabulary.py`); "patent", "trademark",
"claims" and "prior art" are the reader's own words and are used freely.

Both functions are pure over their inputs. Everything factual in them arrived
from USPTO client responses or from LLM analysis of client-fetched claim
text — nothing here invents a number, a title, an owner, or a date.

**One thing is removed, and only one.** `build_artifact` returns its payload
through `privacy.scrub_clearance_artifact`, which replaces personal contact
channels — emails, phone numbers, postal addresses — with a visible marker.
Names of record are untouched: an inventor or assignee name *is* the prior-art
finding, and a report that hides it is a report a founder cannot act on. Read
`clearance/privacy.py` before changing either half of that; it is the write-side
half of a boundary whose other half is `GET /api/clearance/{run_id}`.
"""
from __future__ import annotations

import re

from app.services.clearance.privacy import scrub_clearance_artifact
from app.services.clearance.tracks import ClearanceResult

SKILL_NAME = "ip-clearance-search"
SCHEMA_VERSION = "1.0"

# Verbatim from the skill — every output ends with this, unaltered.
DISCLAIMER = (
    "This is automated research support, not legal advice, and not a clearance "
    "or freedom-to-operate opinion. Consult a registered patent or trademark "
    "attorney before filing, launch, or enforcement decisions."
)

# Stated on every run. The blind-spot window and the invisibility of
# provisional applications additionally appear in `pending_landscape`.
LIMITATIONS = [
    "Patent searching here works at title and metadata level — it does not "
    "search full claim or specification text. Commission a professional "
    "full-text search before filing or launch decisions.",
    "Trademark results cover USPTO federal records only: no state "
    "registrations and no common-law (unregistered) use. Commission a "
    "comprehensive commercial search before adopting a name.",
    "United States coverage only — no foreign patent or trademark records "
    "were searched.",
    "United States provisional applications are never published. They surface "
    "only when a later application claims priority to one, so a competitor's "
    "\"patent pending\" claim cannot be verified directly.",
    "Prior art includes anything published before your filing date — "
    "including your own public disclosures. The US allows a 1-year grace "
    "period for your own disclosures; most other countries allow none.",
]

_TRACK_LABELS = {
    "trademark": "Trademark search",
    "patents": "Patent prior art",
    "pending_landscape": "Unpublished-filing window",
    "examiner_behavior": "Examiner behavior",
}

_RISK_MEANING = {
    "GREEN": "no reference surfaced whose claims plausibly cover the item, or "
    "every such reference is dead",
    "YELLOW": "live references overlap conceptually; differences exist, but a "
    "claim-level review by counsel is warranted",
    "RED": "at least one live reference's claims appear to cover the item as "
    "described",
}


def build_artifact(
    item: str,
    tier: str,
    search_date: str,
    assumptions: list[str],
    result: ClearanceResult,
) -> dict:
    """The machine-readable payload, exactly per the skill's output contract.

    Every key of the contract is present on every run; absent findings are
    empty lists or null, never missing keys.

    Scrubbed of personal contact detail before it is returned, which is what
    makes it safe to store: the worker writes this dict to `clearance_runs`,
    flattens it into `clearance_findings`, and composes the report from it, so
    scrubbing here covers all three. See `clearance/privacy.py` for what is
    removed, what is deliberately kept, and why the two are not the same rule
    the GTM module applies.
    """
    trademark = result.trademark
    return scrub_clearance_artifact({
        "skill": SKILL_NAME,
        "version": SCHEMA_VERSION,
        "search_date": search_date,
        "item": item,
        "assumptions": list(assumptions),
        "tier": tier,
        "tracks_run": list(result.tracks_run),
        "trademark": {
            "status": trademark.status if trademark else "NOT_SEARCHED",
            "marks_checked": list(trademark.marks_checked) if trademark else [],
            "conflicts": [
                {
                    "mark": c.mark,
                    "serial_or_reg": c.serial_or_reg,
                    "owner": c.owner,
                    "live": c.live,
                    "classes": list(c.classes),
                    "goods_services": c.goods_services,
                    "similarity": c.similarity,
                }
                for c in (trademark.conflicts if trademark else [])
            ],
            "official_search_link": trademark.official_search_link if trademark else None,
        },
        "patents": {
            "overall_risk": result.overall_risk,
            "records_screened": result.records_screened,
            "closest_art": [
                {
                    "number": entry.number,
                    "title": entry.title,
                    "assignee": entry.assignee,
                    "filed": entry.filed,
                    "priority": entry.priority,
                    "status": entry.status,
                    "claim_requirements": entry.claim_requirements,
                    "differences": entry.differences,
                    "risk": entry.risk,
                }
                for entry in result.closest_art
            ],
            "whitespace_signals": list(result.whitespace_signals),
            "crowded_areas": list(result.crowded_areas),
        },
        "pending_landscape": {
            "notable_pending": [
                {
                    "app": p.app,
                    "title": p.title,
                    "assignee": p.assignee,
                    "status": p.status,
                }
                for p in result.notable_pending
            ],
            "provisional_priorities_revealed": [
                {"provisional": p.provisional, "via": p.via}
                for p in result.provisional_priorities
            ],
            "blind_spot_note": (
                f"filings after {result.blind_spot_date} are largely unpublished"
            ),
        },
        "queries_run": [
            {"track": q.track, "query": q.query, "hits": q.hits}
            for q in result.queries_run
        ],
        "watch_list": [
            {"target": w.target, "reason": w.reason} for w in result.watch_list
        ],
        "limitations": list(LIMITATIONS),
        "disclaimer": DISCLAIMER,
    })


# ---------------------------------------------------------------------------
# The human report
# ---------------------------------------------------------------------------

_CPC_IN_QUERY = re.compile(r"cpcClassificationBag:([A-Za-z0-9/]+)")
_ASSIGNEE_IN_QUERY = re.compile(r'firstApplicantName:"([^"]+)"')


def _md(text: str) -> str:
    """Make a value safe inside a markdown table cell."""
    return str(text).replace("|", "\\|").replace("\n", " ")


def _header_section(artifact: dict) -> list[str]:
    tracks = ", ".join(
        _TRACK_LABELS.get(track, track) for track in artifact["tracks_run"]
    )
    lines = [
        "# Is this yours to build? — USPTO clearance search",
        "",
        f"**Item searched:** {artifact['item']}",
        f"**Depth:** {artifact['tier']}",
        f"**Search date:** {artifact['search_date']}",
        f"**Checks run:** {tracks or 'none'}",
    ]
    if artifact["assumptions"]:
        lines += ["", "**Assumptions made on your behalf:**"]
        lines += [f"- {assumption}" for assumption in artifact["assumptions"]]
    return lines


def _coverage_section(artifact: dict) -> list[str]:
    queries = artifact["queries_run"]
    classes = sorted(
        {m for q in queries for m in _CPC_IN_QUERY.findall(q["query"])}
    )
    assignees = sorted(
        {m for q in queries for m in _ASSIGNEE_IN_QUERY.findall(q["query"])}
    )
    lines = [
        "## Search coverage",
        "",
        "Every query run, with its hit count — including the ones that found "
        "nothing and the ones that were too broad and had to be narrowed. This "
        "record is what makes the search repeatable.",
        "",
        "| Check | Query | Hits |",
        "|---|---|---|",
    ]
    lines += [
        f"| {_md(_TRACK_LABELS.get(q['track'], q['track']))} | {_md(q['query'])} "
        f"| {q['hits']} |"
        for q in queries
    ]
    lines += [
        "",
        f"Patent classification codes swept: {', '.join(classes) if classes else 'none'}. "
        f"Company filings swept: {', '.join(assignees) if assignees else 'none'}. "
        f"Records screened: {artifact['patents']['records_screened']}.",
    ]
    return lines


def _trademark_section(artifact: dict) -> list[str]:
    tm = artifact["trademark"]
    lines = ["## Trademark findings", ""]
    if not tm["marks_checked"]:
        lines.append(
            "No name was submitted, so no trademark check was run. Submit the "
            "name you plan to use and re-run to cover it."
        )
        return lines

    checked = ", ".join(f'"{m}"' for m in tm["marks_checked"])
    if tm["status"] == "NOT_SEARCHED":
        lines += [
            f"**Status: NOT SEARCHED.** The names to check ({checked}) could not "
            "be word-searched with the tools configured for this run — the USPTO "
            "offers no public word-search interface for programs. That means "
            "their availability is **unverified**, not clear.",
        ]
        if tm["official_search_link"]:
            lines += [
                "",
                f"Run the check yourself at the official USPTO search: "
                f"{tm['official_search_link']}",
            ]
        return lines

    lines.append(f"**Status: {tm['status'].replace('_', ' ')}.** Names checked: {checked}.")
    if tm["conflicts"]:
        lines += [
            "",
            "| Mark found | Serial/Reg. | Owner | Live | Classes | Similarity |",
            "|---|---|---|---|---|---|",
        ]
        lines += [
            f"| {_md(c['mark'])} | {_md(c['serial_or_reg'])} | {_md(c['owner'])} "
            f"| {'yes' if c['live'] else 'no'} | {_md(', '.join(c['classes']))} "
            f"| {_md(c['similarity'])} |"
            for c in tm["conflicts"]
        ]
    else:
        lines.append(
            "No conflicting marks came back for these queries. That is a search "
            "result on the queries above, not a guarantee that no similar mark "
            "exists."
        )
    return lines


def _closest_art_section(artifact: dict) -> list[str]:
    art = artifact["patents"]["closest_art"]
    lines = ["## Closest patent art", ""]
    if not art:
        lines.append(
            "No references were read at claim level at this depth. This is a "
            "statement about the searches run above — not proof that no prior "
            "art exists."
        )
        return lines

    for entry in art:
        dates = f"filed {entry['filed'] or 'date not stated'}"
        if entry["priority"]:
            dates += f", earliest priority {entry['priority']}"
        lines += [
            f"### {entry['number']} — {entry['title'] or '(no title in record)'}",
            "",
            f"*{entry['assignee'] or 'assignee not stated'} · {dates} · "
            f"status: {entry['status'] or 'not stated'} · risk: {entry['risk']}*",
            "",
            f"**What the claims require:** {entry['claim_requirements']}",
            "",
            f"**Where your item differs:** "
            f"{entry['differences'] or 'no differences identified from the description given'}",
            "",
        ]
    return lines


def _pending_section(artifact: dict) -> list[str]:
    pending = artifact["pending_landscape"]
    lines = [
        "## Pending applications and the filings you cannot see yet",
        "",
        f"**The blind spot, stated plainly:** {pending['blind_spot_note']}. "
        "Patent applications publish about 18 months after filing, so recent "
        "filings are mostly invisible to every search, including this one. US "
        "provisional applications are never published at all — they surface "
        "only when a later application claims priority to one.",
    ]
    if pending["notable_pending"]:
        lines += ["", "Live applications worth knowing about:", ""]
        lines += [
            f"- {p['app']} — {p['title'] or '(no title in record)'} "
            f"({p['assignee'] or 'assignee not stated'}; {p['status'] or 'status not stated'})"
            for p in pending["notable_pending"]
        ]
    else:
        lines += [
            "",
            "No live pending applications stood out from these sweeps.",
        ]
    if pending["provisional_priorities_revealed"]:
        lines += [
            "",
            "Provisional filings revealed through priority claims on close "
            "references:",
            "",
        ]
        lines += [
            f"- {p['provisional']} (via {p['via']})"
            for p in pending["provisional_priorities_revealed"]
        ]
    return lines


def _risk_section(artifact: dict) -> list[str]:
    patents = artifact["patents"]
    art = patents["closest_art"]
    reds = sum(1 for e in art if e["risk"] == "RED")
    yellows = sum(1 for e in art if e["risk"] == "YELLOW")
    overall = patents["overall_risk"]

    parts = [
        f"Of {patents['records_screened']} records screened, {len(art)} were "
        "read at claim level."
    ]
    if reds:
        parts.append(
            f"{reds} read as RED — claims that appear to cover the item as described."
        )
    if yellows:
        parts.append(f"{yellows} read as YELLOW — overlap that counsel should review.")
    if not reds and not yellows and art:
        parts.append("None read as covering the item as described.")
    if patents["whitespace_signals"]:
        parts.append(
            "Open ground: "
            + "; ".join(patents["whitespace_signals"])
            + ". Zero hits on well-formed queries is a finding about the "
            "searched record, and worth verifying with a full-text search."
        )
    if patents["crowded_areas"]:
        parts.append("Crowded ground: " + "; ".join(patents["crowded_areas"]) + ".")

    lines = [
        "## Risk summary",
        "",
        f"**Overall: {overall}** — {_RISK_MEANING[overall]}.",
        "",
        " ".join(parts),
    ]
    return lines


def _next_steps_section(artifact: dict) -> list[str]:
    lines = [
        "## Recommended next steps",
        "",
        "1. **Professional full-text search.** This search reads titles and "
        "record data; a professional search reads every claim and "
        "specification. Commission one before filing or launch.",
        "2. **Attorney review.** Take this report — especially the closest-art "
        "entries and their differences — to a registered patent or trademark "
        "attorney.",
        "3. **Re-run quarterly.** Results go stale as new filings publish. The "
        "query record above makes any re-run reproducible and comparable.",
    ]
    if artifact["watch_list"]:
        lines += ["", "**Watch list** — re-check these on every re-run:", ""]
        lines += [
            f"- {w['target']}: {w['reason']}" for w in artifact["watch_list"]
        ]
    return lines


def _limitations_section(artifact: dict) -> list[str]:
    lines = ["## Limitations and disclaimer", ""]
    lines += [f"- {limitation}" for limitation in artifact["limitations"]]
    lines += ["", f"*{artifact['disclaimer']}*"]
    return lines


def _examiner_section(examiner_notes: list[str]) -> list[str]:
    lines = ["## How examiners treat claims like these", ""]
    lines += [f"- {note}" for note in examiner_notes]
    return lines


def compose_report_markdown(
    artifact: dict, examiner_notes: list[str] | None = None
) -> str:
    """The founder-readable report: the contract's eight sections, in order.

    `examiner_notes` carries the Track D summary (COMPREHENSIVE runs). It is a
    separate argument because the JSON contract has no key for it — the
    contract's `queries_run` records the examiner-behavior queries, and the
    prose reading of them belongs to the report, not the payload. Passing it
    here keeps the payload exactly the contract without dropping the finding.
    """
    sections = [
        _header_section(artifact),
        _coverage_section(artifact),
        _trademark_section(artifact),
        _closest_art_section(artifact),
        _pending_section(artifact),
        _risk_section(artifact),
    ]
    if examiner_notes:
        sections.append(_examiner_section(examiner_notes))
    sections += [
        _next_steps_section(artifact),
        _limitations_section(artifact),
    ]
    return "\n".join("\n".join(section).rstrip() for section in sections) + "\n"
