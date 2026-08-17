"""The clearance tracks, run against a scripted USPTO client and a mocked LLM.

What these hold: the search record is complete (every query with its hit
count, including zero-hit and abandoned-too-broad queries), the count-triage
rules fire (broaden once on zero, narrow once past 1,000, two zero axes = a
whitespace signal), the deep-read budget follows the tier table, risk rolls up
with liveness applied, the trademark track never says "clear" without a search
result, a missing ODP key fails loudly before any track runs, and the
blind-spot date is derived from the injected search date — never from a clock
read inside the logic.

No live API and no live LLM anywhere: the client is a fake with scripted
responses, and the claim reader / plan builder LLM calls are monkeypatched.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.clearance import tracks
from app.services.clearance.claim_reader import ClaimReading
from app.services.clearance.query_plan import QueryPlan, TrackQuery
from app.services.clearance.tracks import (
    DEEP_READS,
    ClearanceResult,
    run_clearance_tracks,
)
from app.services.clearance.uspto_client import TRADEMARK_SEARCH_LINK, ClearanceConfigError

SEARCH_DATE = "2026-08-16"
ITEM = "A firewall that intercepts malicious instructions before they reach a language model"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

def _rec(
    app_number: str,
    title: str,
    *,
    status: str = "Pending",
    assignee: str = "",
    grant_number: str | None = None,
    publication_number: str | None = None,
    filed: str = "2023-01-15",
    raw: dict | None = None,
):
    """A duck-typed application record; the tracks only read attributes."""
    return SimpleNamespace(
        app_number=app_number,
        title=title,
        assignee=assignee,
        inventor="",
        filed=filed,
        status=status,
        grant_number=grant_number,
        publication_number=publication_number,
        cpc=[],
        raw=raw or {},
    )


class FakeClient:
    """Scripted USPTO client. `results` maps query string -> (total, items);
    an unscripted query answers zero hits, exactly like the real 404-as-zero."""

    def __init__(
        self,
        *,
        odp: bool = True,
        tsdr: bool = True,
        results: dict | None = None,
        claims: dict | None = None,
        continuity: dict | None = None,
        rejections: list | None = None,
        ptab: list | None = None,
    ):
        self._odp = odp
        self._tsdr = tsdr
        self.results = results or {}
        self.claims = claims or {}
        self.continuity = continuity or {}
        self.rejections = rejections or []
        self.ptab = ptab or []
        self.search_calls: list[tuple[str, int]] = []
        self.claims_calls: list[str] = []
        self.continuity_calls: list[str] = []

    @property
    def odp_available(self) -> bool:
        return self._odp

    @property
    def tsdr_available(self) -> bool:
        return self._tsdr

    async def search_applications(self, query, limit=25, offset=0, sort=None):
        self.search_calls.append((query, limit))
        total, items = self.results.get(query, (0, []))
        return SimpleNamespace(total=total, items=list(items))

    async def get_application(self, app_number):
        return None

    async def get_continuity(self, app_number):
        self.continuity_calls.append(app_number)
        return self.continuity.get(app_number)

    async def get_claims_text(self, record):
        self.claims_calls.append(record.app_number)
        return self.claims.get(record.app_number)

    async def get_trademark_status(self, serial):
        return None

    async def search_rejections(self, query, limit=20):
        return list(self.rejections)

    async def search_ptab(self, query, limit=20):
        return list(self.ptab)


def _reading(risk: str) -> ClaimReading:
    return ClaimReading(
        claim_requirements="a filter placed between the user and the model",
        differences="the item works at the network layer, not inside the model",
        risk=risk,
        rationale="the deciding element is the placement of the filter",
    )


@pytest.fixture
def scripted_readings(monkeypatch):
    """Route the deep reads to scripted risks instead of a live model."""
    risks: dict[str, str] = {}

    async def fake_read_claims(item, ref, claims_text, *, organization_id=None):
        return _reading(risks.get(ref.app_number, "GREEN"))

    monkeypatch.setattr(tracks, "read_claims", fake_read_claims)
    return risks


# ---------------------------------------------------------------------------
# The standard scenario: one plan, scripted counts, every triage rule visible
# ---------------------------------------------------------------------------

F1 = "prompt AND (injection OR sanitization)"
F2 = "intercepting AND malicious AND instructions"
S1 = '"language model" AND firewall'
S1_BROADENED = '"language model"'
D1 = "security software"
D1_NARROWED = "security software AND prompt"
CPC_G06F = "cpcClassificationBag:G06F AND (prompt OR injection)"
CPC_G06N = "cpcClassificationBag:G06N AND (prompt OR injection)"
ASSIGNEE_Q = 'firstApplicantName:"Parry Inc"'

R1 = _rec(
    "17111111",
    "Prompt injection detection and sanitization for language model firewalls",
    assignee="MegaCorp",
    publication_number="US20240011111A1",
)
R2 = _rec(
    "17222222",
    "Malicious instruction interception",
    status="Patented Case",
    assignee="MegaCorp",
    grant_number="US11999999",
)
R3 = _rec("17333333", "Network monitoring", status="Abandoned")
R4 = _rec(
    "17444444",
    "Intercepting malicious instructions in real time",
    assignee="Parry Inc",
)
R5 = _rec("17555555", "Language model serving")
R6 = _rec("17666666", "Software security scanner", status="Expired")
R7 = _rec("17777777", "Prompt filter")
R8 = _rec("17888888", "Neural moderation")
R9 = _rec("17999999", "Payment scheduling", assignee="Parry Inc")

ALL_RECORDS = (R1, R2, R3, R4, R5, R6, R7, R8, R9)


def _plan() -> QueryPlan:
    return QueryPlan(
        classification="both",
        assumptions=["the field was read as software security"],
        queries=[
            TrackQuery(track="patents", query=F1, axis="FUNCTION"),
            TrackQuery(track="patents", query=F2, axis="FUNCTION"),
            TrackQuery(track="patents", query=S1, axis="STRUCTURE"),
            TrackQuery(track="patents", query=D1, axis="DOMAIN"),
        ],
        candidate_cpc=["G06F", "G06N"],
        marks_to_check=["ParryAI", "Parry"],
    )


def _client(**kwargs) -> FakeClient:
    return FakeClient(
        results={
            F1: (12, [R1, R2, R3]),
            F2: (4, [R4]),
            S1: (0, []),
            S1_BROADENED: (5, [R5]),
            D1: (1500, []),
            D1_NARROWED: (40, [R6]),
            CPC_G06F: (30, [R7]),
            CPC_G06N: (8, [R8]),
            ASSIGNEE_Q: (2, [R9, R2]),
        },
        claims={r.app_number: f"1. A method for {r.title.lower()}." for r in ALL_RECORDS},
        continuity={
            "17111111": {
                "parentContinuityBag": [
                    {
                        "parentApplicationNumberText": "63/412,345",
                        "claimParentageTypeCodeDescriptionText": "Provisional",
                        "parentApplicationFilingDate": "2022-09-30",
                    }
                ]
            }
        },
        **kwargs,
    )


async def _standard_run(scripted_readings, tier="STANDARD", client=None):
    client = client or _client()
    scripted_readings.update({"17111111": "RED", "17444444": "YELLOW"})
    result = await run_clearance_tracks(
        client, _plan(), ITEM, tier, ["Parry Inc"], SEARCH_DATE
    )
    return client, result


async def test_every_query_is_recorded_including_zero_hit_and_too_broad(
    scripted_readings,
):
    """The search record is the deliverable: the zero-hit query, its broadened
    re-run, the too-broad query, and its narrowed follow-up all appear."""
    _, result = await _standard_run(scripted_readings)
    recorded = {(q.query, q.hits) for q in result.queries_run}
    assert recorded == {
        (F1, 12),
        (F2, 4),
        (S1, 0),  # the zero-hit query is a finding, not a failure
        (S1_BROADENED, 5),  # ...and its broadened re-run rides next to it
        (D1, 1500),  # the too-broad query stays in the record
        (D1_NARROWED, 40),  # ...with the narrowed follow-up
        (CPC_G06F, 30),
        (CPC_G06N, 8),
        (ASSIGNEE_Q, 2),
    }
    assert all(q.track == "patents" for q in result.queries_run)
    assert result.records_screened == len(ALL_RECORDS)


async def test_too_broad_count_is_reported_only_with_its_narrowed_follow_up(
    scripted_readings,
):
    _, result = await _standard_run(scripted_readings)
    assert len(result.crowded_areas) == 1
    note = result.crowded_areas[0]
    assert "1500" in note and D1_NARROWED in note and "40" in note


async def test_deep_reads_follow_the_tier_table(scripted_readings):
    for tier, expected in [("QUICK", 0), ("STANDARD", 5), ("COMPREHENSIVE", 7)]:
        client, _ = await _standard_run(scripted_readings, tier=tier)
        assert len(client.claims_calls) == expected, tier
    assert DEEP_READS == {"QUICK": 0, "STANDARD": 5, "COMPREHENSIVE": 7}


async def test_quick_is_the_top10_keyword_teaser_and_nothing_more(scripted_readings):
    client, result = await _standard_run(scripted_readings, tier="QUICK")
    assert all(limit == 10 for _, limit in client.search_calls)
    executed = {q.query for q in result.queries_run}
    assert not any(q.startswith("cpcClassificationBag") for q in executed)
    assert not any(q.startswith("firstApplicantName") for q in executed)
    assert result.tracks_run == ["trademark", "patents"]
    assert result.closest_art == []
    assert result.notable_pending == []
    # The honesty statement costs nothing, so even the teaser carries the date.
    assert result.blind_spot_date == "2025-02-16"


async def test_the_closest_reference_is_ranked_first(scripted_readings):
    """Ranking heuristic: R1's title carries five plan terms and the record is
    live, so it outscores every other screened record."""
    _, result = await _standard_run(scripted_readings)
    assert result.closest_art[0].number == "US20240011111A1"
    read_numbers = [entry.number for entry in result.closest_art]
    # The abandoned low-density record is not worth one of five deep reads.
    assert "17333333" not in read_numbers


async def test_risk_rolls_up_red_when_a_live_deep_read_is_red(scripted_readings):
    _, result = await _standard_run(scripted_readings)
    assert result.overall_risk == "RED"


async def test_a_dead_red_reference_cannot_set_the_headline(monkeypatch):
    """Dead art is still prior art, but it blocks nothing: a RED reading on an
    abandoned reference must not produce a RED (or YELLOW) headline."""
    dead = _rec("18000001", "Prompt firewall", status="Abandoned")
    client = FakeClient(
        results={"prompt AND firewall": (1, [dead])},
        claims={"18000001": "1. A method."},
    )

    async def always_red(item, ref, claims_text, *, organization_id=None):
        return _reading("RED")

    monkeypatch.setattr(tracks, "read_claims", always_red)
    plan = QueryPlan(
        classification="invention",
        queries=[TrackQuery(track="patents", query="prompt AND firewall", axis="FUNCTION")],
    )
    result = await run_clearance_tracks(client, plan, ITEM, "STANDARD", [], SEARCH_DATE)
    assert result.closest_art[0].risk == "RED"  # the entry itself stays honest
    assert result.overall_risk == "GREEN"


async def test_risk_rolls_up_yellow_when_the_worst_live_read_is_yellow(
    scripted_readings,
):
    scripted_readings.clear()
    client = _client()
    scripted_readings.update({"17444444": "YELLOW"})
    result = await run_clearance_tracks(
        client, _plan(), ITEM, "STANDARD", ["Parry Inc"], SEARCH_DATE
    )
    assert result.overall_risk == "YELLOW"


# ---------------------------------------------------------------------------
# Count triage: whitespace
# ---------------------------------------------------------------------------

async def test_two_zero_hit_axes_become_a_whitespace_signal(scripted_readings):
    client = FakeClient()  # every query answers zero
    plan = QueryPlan(
        classification="invention",
        queries=[
            TrackQuery(track="patents", query="quantum AND meal", axis="FUNCTION"),
            TrackQuery(
                track="patents", query='"folded lattice" AND container', axis="STRUCTURE"
            ),
        ],
    )
    result = await run_clearance_tracks(client, plan, ITEM, "STANDARD", [], SEARCH_DATE)
    assert len(result.whitespace_signals) == 2
    joined = " ".join(result.whitespace_signals)
    assert "FUNCTION" in joined and "STRUCTURE" in joined
    # Both originals AND both broadened re-runs are in the record.
    recorded = {q.query for q in result.queries_run}
    assert {"quantum AND meal", "quantum", '"folded lattice" AND container',
            '"folded lattice"'} <= recorded
    assert result.records_screened == 0
    assert result.closest_art == []
    assert result.overall_risk == "GREEN"


async def test_one_zero_axis_alone_is_not_whitespace(scripted_readings):
    hit = _rec("18000002", "Container closure")
    client = FakeClient(results={'"folded lattice" AND container': (3, [hit])})
    plan = QueryPlan(
        classification="invention",
        queries=[
            TrackQuery(track="patents", query="quantum AND meal", axis="FUNCTION"),
            TrackQuery(
                track="patents", query='"folded lattice" AND container', axis="STRUCTURE"
            ),
        ],
    )
    result = await run_clearance_tracks(client, plan, ITEM, "STANDARD", [], SEARCH_DATE)
    assert result.whitespace_signals == []


# ---------------------------------------------------------------------------
# Track A honesty
# ---------------------------------------------------------------------------

async def test_trademarks_are_not_searched_when_tsdr_is_unconfigured(
    scripted_readings,
):
    _, result = await _standard_run(
        scripted_readings, client=_client(tsdr=False)
    )
    assert result.trademark is not None
    assert result.trademark.status == "NOT_SEARCHED"
    assert result.trademark.marks_checked == ["ParryAI", "Parry"]
    assert result.trademark.official_search_link == TRADEMARK_SEARCH_LINK


async def test_trademarks_are_not_searched_when_the_client_cannot_word_search(
    scripted_readings,
):
    """A configured TSDR key is status lookup by serial, not word search — the
    honest status is still NOT_SEARCHED, never a quiet 'clear'."""
    _, result = await _standard_run(scripted_readings)  # tsdr=True, no word search
    assert result.trademark.status == "NOT_SEARCHED"
    assert result.trademark.official_search_link == TRADEMARK_SEARCH_LINK


async def test_a_word_search_capable_client_reports_real_conflicts(
    scripted_readings,
):
    class WordSearchClient(FakeClient):
        async def search_trademarks(self, mark):
            if mark == "Parry":
                return [
                    SimpleNamespace(
                        mark="PARRY",
                        serial="98123456",
                        live=True,
                        owner="Parry Holdings LLC",
                        classes=[9, 42],
                        goods_services="downloadable security software",
                        status_text="REGISTERED",
                        raw={},
                    )
                ]
            return []

    client = _client()
    word_client = WordSearchClient(
        results=client.results, claims=client.claims, continuity=client.continuity
    )
    _, result = await _standard_run(scripted_readings, client=word_client)
    tm = result.trademark
    assert tm.status == "CONFLICTS_FOUND"
    conflict = tm.conflicts[0]
    assert (conflict.serial_or_reg, conflict.owner, conflict.live) == (
        "98123456",
        "Parry Holdings LLC",
        True,
    )
    assert conflict.similarity == "identical"  # "PARRY" vs checked "Parry"
    marks_recorded = {
        (q.query, q.hits) for q in result.queries_run if q.track == "trademark"
    }
    assert marks_recorded == {("ParryAI", 0), ("Parry", 1)}


async def test_no_marks_means_no_trademark_track(scripted_readings):
    plan = _plan()
    plan.marks_to_check = []
    client = _client()
    result = await run_clearance_tracks(
        client, plan, ITEM, "STANDARD", ["Parry Inc"], SEARCH_DATE
    )
    assert result.trademark is None
    assert "trademark" not in result.tracks_run


# ---------------------------------------------------------------------------
# Degrade honestly / fail loudly
# ---------------------------------------------------------------------------

async def test_no_odp_key_raises_before_any_track_runs(scripted_readings):
    client = _client(odp=False)
    with pytest.raises(ClearanceConfigError):
        await run_clearance_tracks(
            client, _plan(), ITEM, "STANDARD", [], SEARCH_DATE
        )
    assert client.search_calls == []


async def test_an_unknown_tier_is_rejected(scripted_readings):
    with pytest.raises(ValueError):
        await run_clearance_tracks(_client(), _plan(), ITEM, "DELUXE", [], SEARCH_DATE)


async def test_a_bad_search_date_is_rejected_not_fabricated(scripted_readings):
    with pytest.raises(ValueError):
        await run_clearance_tracks(
            _client(), _plan(), ITEM, "STANDARD", [], "sometime in August"
        )


async def test_unfetchable_claims_produce_an_unreviewed_entry_not_a_guess(
    monkeypatch,
):
    live = _rec("18000003", "Prompt firewall")
    client = FakeClient(results={"prompt AND firewall": (1, [live])}, claims={})

    async def never_called(item, ref, claims_text, *, organization_id=None):
        raise AssertionError("read_claims must not run without claims text")

    monkeypatch.setattr(tracks, "read_claims", never_called)
    plan = QueryPlan(
        classification="invention",
        queries=[TrackQuery(track="patents", query="prompt AND firewall", axis="FUNCTION")],
    )
    result = await run_clearance_tracks(client, plan, ITEM, "STANDARD", [], SEARCH_DATE)
    entry = result.closest_art[0]
    assert "not reviewed at claim level" in entry.claim_requirements
    assert entry.risk == "YELLOW"  # unread + live = counsel should look, not "clear"
    assert result.overall_risk == "YELLOW"


# ---------------------------------------------------------------------------
# Track C: the blind spot and the provisionals
# ---------------------------------------------------------------------------

async def test_blind_spot_date_derives_from_the_injected_search_date(
    scripted_readings,
):
    _, result = await _standard_run(scripted_readings)
    assert result.blind_spot_date == "2025-02-16"


async def test_blind_spot_arithmetic_clamps_short_months(scripted_readings):
    client = _client()
    result = await run_clearance_tracks(
        client, _plan(), ITEM, "STANDARD", ["Parry Inc"], "2026-10-31"
    )
    assert result.blind_spot_date == "2025-04-30"  # April has no 31st


async def test_continuity_reveals_the_provisional_and_the_priority_date(
    scripted_readings,
):
    _, result = await _standard_run(scripted_readings)
    assert [(p.provisional, p.via) for p in result.provisional_priorities] == [
        ("63/412,345", "US20240011111A1")
    ]
    top = result.closest_art[0]
    assert top.priority == "2022-09-30"


async def test_pending_apps_are_flagged_and_dead_or_granted_ones_are_not(
    scripted_readings,
):
    _, result = await _standard_run(scripted_readings)
    flagged = {p.app for p in result.notable_pending}
    assert "17111111" in flagged  # live, no grant yet
    assert "17222222" not in flagged  # granted
    assert "17333333" not in flagged  # abandoned


# ---------------------------------------------------------------------------
# COMPREHENSIVE extras: repeat assignees, Track D, watch list
# ---------------------------------------------------------------------------

async def test_comprehensive_sweeps_repeat_assignees_the_founder_never_named(
    scripted_readings,
):
    client = _client(
        rejections=[{"rejectionType": "103"}, {"statute": "103"}, {"basis": "101"}],
        ptab=[{"trialNumber": "IPR2024-00001"}],
    )
    _, result = await _standard_run(
        scripted_readings, tier="COMPREHENSIVE", client=client
    )
    executed = {q.query for q in result.queries_run}
    # MegaCorp appears on two screened records without being named by the caller.
    assert 'firstApplicantName:"MegaCorp"' in executed
    assert 'firstApplicantName:"Parry Inc"' in executed


async def test_track_d_runs_only_at_comprehensive_and_summarizes_patterns(
    scripted_readings,
):
    client = _client(
        rejections=[{"rejectionType": "103"}, {"statute": "103"}, {"basis": "101"}],
        ptab=[{"trialNumber": "IPR2024-00001"}],
    )
    _, comprehensive = await _standard_run(
        scripted_readings, tier="COMPREHENSIVE", client=client
    )
    assert "examiner_behavior" in comprehensive.tracks_run
    examiner_queries = [
        q for q in comprehensive.queries_run if q.track == "examiner_behavior"
    ]
    assert [(q.query, q.hits) for q in examiner_queries] == [(F1, 3), (F1, 1)]
    notes = " ".join(comprehensive.examiner_notes)
    assert "2" in notes and "103" in notes and "101" in notes

    _, standard = await _standard_run(scripted_readings, client=_client())
    assert "examiner_behavior" not in standard.tracks_run
    assert standard.examiner_notes == []


async def test_empty_examiner_results_are_reported_as_results(scripted_readings):
    _, result = await _standard_run(
        scripted_readings, tier="COMPREHENSIVE", client=_client()
    )
    notes = " ".join(result.examiner_notes)
    assert "No examiner rejection records" in notes
    assert "not proof" in notes


async def test_the_watch_list_exists_only_at_comprehensive(scripted_readings):
    _, comprehensive = await _standard_run(scripted_readings, tier="COMPREHENSIVE")
    targets = {w.target for w in comprehensive.watch_list}
    assert "17111111" in targets  # the close live application
    assert "MegaCorp" in targets  # the repeat filer

    _, standard = await _standard_run(scripted_readings)
    assert standard.watch_list == []


async def test_tracks_run_reflects_the_tier(scripted_readings):
    _, standard = await _standard_run(scripted_readings)
    assert standard.tracks_run == ["trademark", "patents", "pending_landscape"]
    _, comprehensive = await _standard_run(scripted_readings, tier="COMPREHENSIVE")
    assert comprehensive.tracks_run == [
        "trademark",
        "patents",
        "pending_landscape",
        "examiner_behavior",
    ]


# ---------------------------------------------------------------------------
# The plan builder (Stage 0 + Stage 1), LLM mocked
# ---------------------------------------------------------------------------

class _PlanCall:
    def __init__(self, response: QueryPlan):
        self.response = response
        self.messages = None
        self.model = None

    async def __call__(self, messages, schema, model=None):
        self.messages = messages
        self.model = model
        return self.response


async def test_the_plan_prompt_carries_the_translation_table_and_cpc_map(
    monkeypatch,
):
    from app.services.clearance import query_plan as qp

    call = _PlanCall(QueryPlan(classification="invention"))
    monkeypatch.setattr(qp, "llm_structured", call)
    await qp.build_query_plan(ITEM, None, "software security", [])
    prompt = call.messages[0]["content"]
    assert "brandable coined words" in prompt  # the translation table
    assert "no-spill travel mug" in prompt  # a per-field example
    assert "G06N" in prompt  # the CPC guidance
    assert "FUNCTION" in prompt and "STRUCTURE" in prompt and "DOMAIN" in prompt


async def test_the_plan_runs_on_the_main_model_not_the_fast_one(monkeypatch):
    from app.core.config import settings
    from app.services.clearance import query_plan as qp

    call = _PlanCall(QueryPlan(classification="invention"))
    monkeypatch.setattr(qp, "llm_structured", call)
    await qp.build_query_plan(ITEM, None, None, [])
    assert call.model == f"{settings.llm_provider}/{settings.llm_model}"


async def test_a_type_hint_always_wins_over_the_models_classification(monkeypatch):
    from app.services.clearance import query_plan as qp

    call = _PlanCall(QueryPlan(classification="invention", marks_to_check=[]))
    monkeypatch.setattr(qp, "llm_structured", call)
    plan = await qp.build_query_plan("Zappo", "name", None, [])
    assert plan.classification == "name"
    # A name with nothing to check would be a track that silently never runs.
    assert plan.marks_to_check == ["Zappo"]


async def test_an_inferred_classification_is_recorded_as_an_assumption(monkeypatch):
    from app.services.clearance import query_plan as qp

    call = _PlanCall(QueryPlan(classification="invention"))
    monkeypatch.setattr(qp, "llm_structured", call)
    plan = await qp.build_query_plan(ITEM, None, None, [])
    assert any("invention" in a for a in plan.assumptions)


async def test_an_invention_classification_empties_the_marks(monkeypatch):
    from app.services.clearance import query_plan as qp

    call = _PlanCall(
        QueryPlan(classification="invention", marks_to_check=["Firewall", "firewall "])
    )
    monkeypatch.setattr(qp, "llm_structured", call)
    plan = await qp.build_query_plan(ITEM, None, None, [])
    assert plan.marks_to_check == []


async def test_the_plan_is_normalized_axes_upper_queries_deduped_cpc_cleaned(
    monkeypatch,
):
    from app.services.clearance import query_plan as qp

    call = _PlanCall(
        QueryPlan(
            classification="both",
            queries=[
                TrackQuery(track="patents", query="prompt AND filter", axis="function"),
                TrackQuery(track="patents", query="Prompt AND Filter", axis="FUNCTION"),
                TrackQuery(track="patents", query="", axis="FUNCTION"),
                TrackQuery(track="patents", query="model AND guard", axis="sideways"),
            ],
            candidate_cpc=["g06f 21", "G06F21", "X"],
            marks_to_check=["Zappo", "zappo", " "],
        )
    )
    monkeypatch.setattr(qp, "llm_structured", call)
    plan = await qp.build_query_plan("Zappo, a prompt filter", None, None, [])
    assert [q.query for q in plan.queries] == ["prompt AND filter"]
    assert plan.queries[0].axis == "FUNCTION"
    assert plan.candidate_cpc == ["G06F21"]  # cleaned, deduped, "X" too short
    assert plan.marks_to_check == ["Zappo"]


# ---------------------------------------------------------------------------
# The claim reader, LLM mocked
# ---------------------------------------------------------------------------

async def test_claim_reader_runs_on_the_main_model_and_normalizes_risk(monkeypatch):
    from app.core.config import settings
    from app.services.clearance import claim_reader as cr

    seen = {}

    async def fake_llm(messages, schema, model=None):
        seen["model"] = model
        seen["prompt"] = messages[0]["content"]
        return ClaimReading(
            claim_requirements="an interceptor between user and model",
            differences="no interceptor at the network layer",
            risk="red",
            rationale="every element appears present",
        )

    monkeypatch.setattr(cr, "llm_structured", fake_llm)
    reading = await cr.read_claims(ITEM, R1, "1. A method comprising...")
    assert reading.risk == "RED"
    assert seen["model"] == f"{settings.llm_provider}/{settings.llm_model}"
    assert "1. A method comprising..." in seen["prompt"]
    assert R1.title in seen["prompt"]


async def test_an_unrecognized_risk_tier_defaults_to_yellow_loudly(monkeypatch):
    from app.services.clearance import claim_reader as cr

    async def fake_llm(messages, schema, model=None):
        return ClaimReading(
            claim_requirements="x", differences="y", risk="PURPLE", rationale="z"
        )

    monkeypatch.setattr(cr, "llm_structured", fake_llm)
    reading = await cr.read_claims(ITEM, R1, "1. A method.")
    assert reading.risk == "YELLOW"
    assert "PURPLE" in reading.rationale  # the anomaly is visible, not swallowed


async def test_over_long_claims_are_truncated_and_the_prompt_says_so(monkeypatch):
    from app.services.clearance import claim_reader as cr

    seen = {}

    async def fake_llm(messages, schema, model=None):
        seen["prompt"] = messages[0]["content"]
        return _reading("GREEN")

    monkeypatch.setattr(cr, "llm_structured", fake_llm)
    await cr.read_claims(ITEM, R1, "claim text " * 5000)
    assert "truncated" in seen["prompt"]


# ---------------------------------------------------------------------------
# Canary
# ---------------------------------------------------------------------------

async def test_the_scripted_run_actually_ran_every_stage(scripted_readings):
    """A fake whose queries never matched would make half the tests above pass
    on empty results. This pins the run's overall shape."""
    client, result = await _standard_run(scripted_readings)
    assert isinstance(result, ClearanceResult)
    assert len(result.queries_run) == 9
    assert len(result.closest_art) == 5
    assert len(client.continuity_calls) == 5
    assert result.notable_pending  # the landscape saw the live applications
