"""The clearance artifact: the exact output contract, and the founder report.

The JSON payload is checked key for key against the skill's output contract —
every key present, none renamed, empties as empty rather than missing — and
the disclaimer byte for byte, because every render and export carries it
verbatim (PRD_V3 §11). The markdown report is held to the same vocabulary rule
as every other artifact that leaves the building: the banned-word scan mirrors
`test_report_vocabulary.py`'s JARGON mechanics over these new strings.
"""
from __future__ import annotations

import json
import re

from app.services.clearance.artifact import (
    DISCLAIMER,
    build_artifact,
    compose_report_markdown,
)
from app.services.clearance.tracks import (
    ArtEntry,
    ClearanceResult,
    PendingApp,
    ProvisionalPriority,
    QueryRecord,
    TrademarkConflict,
    TrademarkFindings,
    WatchItem,
)

ITEM = "A firewall that intercepts malicious instructions before they reach a language model"
SEARCH_DATE = "2026-08-16"
BLIND_SPOT = "2025-02-16"
LINK = "https://tmsearch.uspto.gov/search/search-information"

# ── the contract, spelled out ────────────────────────────────────────

TOP_KEYS = {
    "skill", "version", "search_date", "item", "assumptions", "tier",
    "tracks_run", "trademark", "patents", "pending_landscape", "queries_run",
    "watch_list", "limitations", "disclaimer",
}
TRADEMARK_KEYS = {"status", "marks_checked", "conflicts", "official_search_link"}
CONFLICT_KEYS = {
    "mark", "serial_or_reg", "owner", "live", "classes", "goods_services",
    "similarity",
}
PATENTS_KEYS = {
    "overall_risk", "records_screened", "closest_art", "whitespace_signals",
    "crowded_areas",
}
ART_KEYS = {
    "number", "title", "assignee", "filed", "priority", "status",
    "claim_requirements", "differences", "risk",
}
PENDING_KEYS = {
    "notable_pending", "provisional_priorities_revealed", "blind_spot_note",
}
QUERY_KEYS = {"track", "query", "hits"}
WATCH_KEYS = {"target", "reason"}

#: Verbatim from the skill's Rules section. Retyped here rather than imported
#: so a drift in the constant fails a test instead of redefining the truth.
EXPECTED_DISCLAIMER = (
    "This is automated research support, not legal advice, and not a clearance "
    "or freedom-to-operate opinion. Consult a registered patent or trademark "
    "attorney before filing, launch, or enforcement decisions."
)

# ── the vocabulary rule, same mechanics as test_report_vocabulary ────

JARGON = (
    "ICP", "variant", "A/B", "adversarial", "cohort", "arena", "lens",
    "archetype", "canonical", "valence", "simulation", "project",
)


def _pattern(word: str) -> re.Pattern[str]:
    return re.compile(rf"\b{re.escape(word)}s?\b", re.IGNORECASE)


def _hits(text: str) -> list[str]:
    return [word for word in JARGON if _pattern(word).search(text)]


# ── fixtures ─────────────────────────────────────────────────────────

def _full_result() -> ClearanceResult:
    """Every branch populated, so the render has nothing left unexercised."""
    return ClearanceResult(
        tracks_run=["trademark", "patents", "pending_landscape", "examiner_behavior"],
        trademark=TrademarkFindings(
            status="CONFLICTS_FOUND",
            marks_checked=["ParryAI", "Parry"],
            conflicts=[
                TrademarkConflict(
                    mark="PARRY",
                    serial_or_reg="98123456",
                    owner="Parry Holdings LLC",
                    live=True,
                    classes=["9", "42"],
                    goods_services="downloadable security software",
                    similarity="identical",
                )
            ],
            official_search_link=LINK,
        ),
        overall_risk="RED",
        records_screened=9,
        closest_art=[
            ArtEntry(
                number="US20240011111A1",
                title="Prompt injection detection for language model firewalls",
                assignee="MegaCorp",
                filed="2023-01-15",
                priority="2022-09-30",
                status="Pending",
                live=True,
                claim_requirements="an interceptor placed between the user and the model",
                differences="the item works at the network layer",
                risk="RED",
                rationale="every required element appears present",
            ),
            ArtEntry(
                number="US11999999",
                title="Malicious instruction interception",
                assignee="MegaCorp",
                filed="2021-06-01",
                priority=None,
                status="Patented Case",
                live=True,
                claim_requirements="a scoring step before delivery",
                differences="no scoring step in the item as described",
                risk="YELLOW",
                rationale="overlap is conceptual, not element for element",
            ),
        ],
        whitespace_signals=[
            'no hits on the STRUCTURE axis: "\\"folded lattice\\" AND container" '
            "and its broadened form both returned zero results"
        ],
        crowded_areas=[
            '"security software" matched 1500 records — too generic to read as '
            'a finding; narrowed to "security software AND prompt" (40 records)'
        ],
        notable_pending=[
            PendingApp(
                app="17111111",
                title="Prompt injection detection for language model firewalls",
                assignee="MegaCorp",
                status="Pending",
            )
        ],
        provisional_priorities=[
            ProvisionalPriority(provisional="63/412,345", via="US20240011111A1")
        ],
        blind_spot_date=BLIND_SPOT,
        queries_run=[
            QueryRecord(track="trademark", query="ParryAI", hits=0),
            QueryRecord(track="patents", query="prompt AND (injection OR sanitization)", hits=12),
            QueryRecord(track="patents", query='"language model" AND firewall', hits=0),
            QueryRecord(track="patents", query='"language model"', hits=5),
            QueryRecord(track="patents", query="security software", hits=1500),
            QueryRecord(track="patents", query="security software AND prompt", hits=40),
            QueryRecord(track="patents", query="cpcClassificationBag:G06F AND prompt", hits=30),
            QueryRecord(track="patents", query='firstApplicantName:"Parry Inc"', hits=2),
            QueryRecord(track="examiner_behavior", query="prompt AND injection", hits=3),
        ],
        watch_list=[
            WatchItem(
                target="17111111",
                reason="a live application close to the item; its claims can "
                "still change before grant",
            ),
            WatchItem(
                target="MegaCorp",
                reason="a repeat filer in this art — new filings from them are "
                "the ones to watch",
            ),
        ],
        examiner_notes=[
            "Across 3 recent examiner rejection records for similar claims: "
            "1 cite subject-matter eligibility (section 101), 2 cite "
            "obviousness (section 103).",
        ],
    )


def _empty_result() -> ClearanceResult:
    """The thin run: no name, no hits, nothing read — every key still present."""
    return ClearanceResult(
        tracks_run=["patents", "pending_landscape"],
        trademark=None,
        overall_risk="GREEN",
        records_screened=0,
        closest_art=[],
        whitespace_signals=[],
        crowded_areas=[],
        notable_pending=[],
        provisional_priorities=[],
        blind_spot_date=BLIND_SPOT,
        queries_run=[QueryRecord(track="patents", query="quantum AND meal", hits=0)],
        watch_list=[],
        examiner_notes=[],
    )


def _artifact(result=None, assumptions=None):
    return build_artifact(
        ITEM,
        "COMPREHENSIVE" if result is None else "STANDARD",
        SEARCH_DATE,
        assumptions if assumptions is not None
        else ['no type hint was given; the item was read as "both"'],
        result if result is not None else _full_result(),
    )


# ── the JSON contract ────────────────────────────────────────────────

def test_every_key_of_the_contract_is_present_and_none_are_invented():
    for artifact in (_artifact(), _artifact(result=_empty_result(), assumptions=[])):
        assert set(artifact) == TOP_KEYS
        assert set(artifact["trademark"]) == TRADEMARK_KEYS
        assert set(artifact["patents"]) == PATENTS_KEYS
        assert set(artifact["pending_landscape"]) == PENDING_KEYS
        for conflict in artifact["trademark"]["conflicts"]:
            assert set(conflict) == CONFLICT_KEYS
        for entry in artifact["patents"]["closest_art"]:
            assert set(entry) == ART_KEYS
        for query in artifact["queries_run"]:
            assert set(query) == QUERY_KEYS
        for watch in artifact["watch_list"]:
            assert set(watch) == WATCH_KEYS
        for pending in artifact["pending_landscape"]["notable_pending"]:
            assert set(pending) == {"app", "title", "assignee", "status"}
        for prio in artifact["pending_landscape"]["provisional_priorities_revealed"]:
            assert set(prio) == {"provisional", "via"}


def test_the_artifact_is_plain_json():
    round_tripped = json.loads(json.dumps(_artifact()))
    assert round_tripped["skill"] == "ip-clearance-search"
    assert round_tripped["version"] == "1.0"
    assert round_tripped["search_date"] == SEARCH_DATE
    assert round_tripped["item"] == ITEM


def test_the_disclaimer_is_verbatim():
    assert DISCLAIMER == EXPECTED_DISCLAIMER
    assert _artifact()["disclaimer"] == EXPECTED_DISCLAIMER


def test_queries_run_keeps_the_zero_hit_and_too_broad_queries():
    queries = _artifact()["queries_run"]
    hits_by_query = {q["query"]: q["hits"] for q in queries}
    assert hits_by_query['"language model" AND firewall'] == 0
    assert hits_by_query["security software"] == 1500  # abandoned-as-too-broad
    assert hits_by_query["security software AND prompt"] == 40


def test_the_blind_spot_note_carries_the_real_derived_date():
    note = _artifact()["pending_landscape"]["blind_spot_note"]
    assert note == f"filings after {BLIND_SPOT} are largely unpublished"


def test_an_absent_trademark_track_is_not_searched_never_clear():
    artifact = _artifact(result=_empty_result(), assumptions=[])
    tm = artifact["trademark"]
    assert tm["status"] == "NOT_SEARCHED"
    assert tm["marks_checked"] == []
    assert tm["conflicts"] == []


def test_the_limitations_name_the_scope_gaps_the_skill_requires():
    joined = " ".join(_artifact()["limitations"])
    assert "title and metadata" in joined  # search scope
    assert "state" in joined and "common-law" in joined  # trademark gap
    assert "foreign" in joined  # geography gap
    assert "provisional" in joined  # the invisible filings
    assert "grace period" in joined  # the founder's own disclosures


# ── the report ───────────────────────────────────────────────────────

SECTION_HEADINGS = (
    "## Search coverage",
    "## Trademark findings",
    "## Closest patent art",
    "## Pending applications and the filings you cannot see yet",
    "## Risk summary",
    "## Recommended next steps",
    "## Limitations and disclaimer",
)


def test_the_report_has_the_contracts_eight_sections_in_order():
    markdown = compose_report_markdown(_artifact())
    positions = [markdown.index(h) for h in SECTION_HEADINGS]
    assert positions == sorted(positions)
    assert markdown.index("# Is this yours to build?") < positions[0]


def test_the_report_uses_no_word_a_founder_has_to_learn():
    for artifact in (_artifact(), _artifact(result=_empty_result(), assumptions=[])):
        markdown = compose_report_markdown(artifact)
        offenders = [
            f'"{word}" in {line!r}'
            for line in markdown.splitlines()
            for word in _hits(line)
        ]
        assert offenders == []


def test_the_jargon_scan_can_actually_see():
    """The canary for the scan above: the matcher matches, and the report has
    substance to scan — an empty render passes any vocabulary rule."""
    assert _hits("Adversarial cohort disclosure") == ["adversarial", "cohort"]
    assert _hits("Simulations") == ["simulation"]
    assert _hits("prior art and patent claims") == []
    markdown = compose_report_markdown(_artifact())
    assert len(markdown.splitlines()) > 40
    assert ITEM in markdown
    assert EXPECTED_DISCLAIMER in markdown


def test_the_report_states_the_blind_spot_with_the_real_date():
    markdown = compose_report_markdown(_artifact())
    assert f"filings after {BLIND_SPOT} are largely unpublished" in markdown
    assert "never published" in markdown  # the provisional invisibility


def test_a_not_searched_name_is_reported_as_unverified_with_the_link():
    result = _empty_result()
    result.trademark = TrademarkFindings(
        status="NOT_SEARCHED",
        marks_checked=["Zappo"],
        conflicts=[],
        official_search_link=LINK,
    )
    result.tracks_run = ["trademark", "patents", "pending_landscape"]
    markdown = compose_report_markdown(_artifact(result=result, assumptions=[]))
    assert "NOT SEARCHED" in markdown
    assert "unverified" in markdown
    assert LINK in markdown


def test_empty_results_are_reported_as_empty_not_as_clearance():
    markdown = compose_report_markdown(_artifact(result=_empty_result(), assumptions=[]))
    assert "not proof that no prior art exists" in markdown
    assert "No name was submitted" in markdown


def test_the_conflict_table_carries_the_owner_and_liveness():
    markdown = compose_report_markdown(_artifact())
    assert "Parry Holdings LLC" in markdown
    assert "98123456" in markdown
    assert "CONFLICTS FOUND" in markdown


def test_the_full_report_shows_the_watch_list_and_examiner_reading():
    result = _full_result()
    artifact = _artifact(result=result)
    markdown = compose_report_markdown(artifact, examiner_notes=result.examiner_notes)
    assert "Watch list" in markdown
    assert "MegaCorp" in markdown
    # The examiner reading rides in as its own argument: the JSON contract has
    # no key for it, and the payload must stay exactly the contract.
    assert "section 103" in markdown
    assert set(artifact) == TOP_KEYS  # notes added nothing to the payload
    # The report derives coverage figures from the query record, not from
    # fields the contract does not carry.
    assert "G06F" in markdown  # the class swept, recovered from its query
    assert "Parry Inc" in markdown  # the company swept, recovered from its query


def test_examiner_notes_scan_clean_too():
    result = _full_result()
    markdown = compose_report_markdown(
        _artifact(result=result), examiner_notes=result.examiner_notes
    )
    offenders = [
        f'"{word}" in {line!r}'
        for line in markdown.splitlines()
        for word in _hits(line)
    ]
    assert offenders == []
