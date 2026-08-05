"""Tests for go-to-market candidate discovery.

The governing failure is the same one the rest of this suite is built around: a
miss and a legitimate absence sharing one value. Here it takes four forms, and
each has a test below.

  * A firmographic nobody stated, read as a firmographic somebody stated.
  * A page the model remembered, read as a page a search returned.
  * A contact gate that could not be read, read as a gate that is off — and its
    mirror, a gate that is off failing to actually stop anything.
  * Spend that never reached `llm_usage`, read as a stage that cost nothing.

Log assertions use `structlog.testing.capture_logs`; `caplog` passes vacuously
in this codebase because structlog is not bound to stdlib logging outside
`create_app`.
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from structlog.testing import capture_logs

from app.services.engine.personas.icp_schema import ICPArchetype, ICPProfile
from app.services.gtm import extraction, privacy, query_compiler, scoring, store
from app.services.gtm.pricing import (
    SEARCHES_PER_QUERY,
    WEB_SEARCH_USD_PER_REQUEST,
    estimate_discovery_cost,
    search_fee_usd,
)
from app.services.gtm.schema import (
    Candidate,
    EvidenceItem,
    ProposedCandidate,
    ProposedContact,
    SearchResult,
)
from app.services.gtm.search_adapter import AnthropicWebSearchAdapter

RETRIEVED_AT = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


def _events(logs) -> set[str]:
    return {entry["event"] for entry in logs}


# ── Fixtures ─────────────────────────────────────────────

def _archetype(**overrides) -> ICPArchetype:
    base = {
        "id": "platform_lead",
        "label": "Platform lead",
        "role": "platform engineer",
        "seniority": "director",
        "incumbent_tooling": ["Datadog", "New Relic"],
        "evaluation_criteria": ["migration effort from existing agents"],
        "pains": ["alert fatigue from noisy dashboards"],
    }
    base.update(overrides)
    return ICPArchetype(**base)


def _profile(archetypes=None, category="observability tooling") -> ICPProfile:
    return ICPProfile(
        name="Observability buyers",
        category=category,
        product_summary="An observability tool",
        archetypes=archetypes or [_archetype()],
    )


def _result(url="https://example.com/a", snippet="", title="Example") -> SearchResult:
    return SearchResult(
        provider="test",
        query="q",
        url=url,
        title=title,
        snippet=snippet,
        retrieved_at=RETRIEVED_AT,
    )


# ── The query compiler is deterministic from a profile ───

def test_the_compiler_returns_the_same_queries_every_time():
    """The queries are the one thing a founder can argue with before paying.

    A set that varies run to run cannot be argued with, and cannot be tested by
    assertion either — which is how a bad query angle would survive.
    """
    profile = _profile()
    first = query_compiler.compile_queries(profile)
    second = query_compiler.compile_queries(profile)
    assert [q.model_dump() for q in first] == [q.model_dump() for q in second]


def test_one_archetype_yields_the_three_angles_with_exact_queries():
    """The exact query text, negatives included.

    The trailing `-Datadog -"New Relic"` is the fix for a live defect: a founder
    searching for buyers was handed the vendors they compete with. It is pinned
    in the exact-text assertion rather than tested separately, so an angle that
    stops excluding cannot pass this file. `test_gtm_exclusions.py` covers why
    those two names are on the list and what happens to them on the way back.
    """
    queries = query_compiler.compile_queries(_profile())
    by_angle = {q.angle: q.query for q in queries}

    assert by_angle["firmographic"] == (
        '"observability tooling" "platform engineer" director companies '
        '-Datadog -"New Relic"'
    )
    # The one angle that cannot negate its own subject: `companies using
    # Datadog -Datadog` finds nothing. Datadog is dropped after the search
    # instead — see `test_gtm_exclusions.py`.
    assert by_angle["incumbent_tooling"] == (
        'companies using Datadog OR "New Relic" "observability tooling"'
    )
    assert by_angle["pain_trigger"] == (
        '"alert fatigue from noisy dashboards" "platform engineer" '
        '"observability tooling" -Datadog -"New Relic"'
    )


def test_every_query_names_the_archetype_that_produced_it():
    queries = query_compiler.compile_queries(_profile())
    assert queries
    assert all(q.archetype_id == "platform_lead" for q in queries)
    assert all(q.derived_from for q in queries)


def test_an_angle_with_no_source_field_is_skipped_not_padded():
    """An archetype with no incumbent tooling yields two queries, not three.

    The alternative — a generic stand-in query — spends credits pretending the
    ICP has a field it does not, and `ICPProfile.gaps` already exists to say so.
    """
    thin = _archetype(incumbent_tooling=[], pains=[], skepticism_triggers=[])
    with capture_logs() as logs:
        queries = query_compiler.compile_queries(_profile([thin]))

    assert [q.angle for q in queries] == ["firmographic"]
    entry = next(e for e in logs if e["event"] == "gtm_queries_compiled")
    assert "platform_lead:incumbent_tooling" in entry["skipped_angles"]
    assert "platform_lead:pain_trigger" in entry["skipped_angles"]


def test_the_cap_is_angle_major_so_every_archetype_is_covered():
    """Capped at 4 across two archetypes, both get their firmographic query."""
    a = _archetype(id="a", label="A")
    b = _archetype(id="b", label="B", role="SRE", incumbent_tooling=["Grafana"])
    queries = query_compiler.compile_queries(_profile([a, b]), max_queries=4)

    assert len(queries) == 4
    firmographic = [q.archetype_id for q in queries if q.angle == "firmographic"]
    assert sorted(firmographic) == ["a", "b"]


def test_the_adversarial_cohort_produces_no_prospect_queries():
    """DECISIONS §7's cohort exists for the simulation, not for the pipeline.

    Compiling searches for incumbent advocates would hand the founder a list of
    people whose entire position is that they are not buying.
    """
    profile = _profile()
    profile.adversarial = []
    queries = query_compiler.compile_queries(profile)
    assert all(q.archetype_id == "platform_lead" for q in queries)


# ── An unevidenced field is None, never invented ─────────

def test_a_field_with_no_supporting_quote_is_none():
    """The whole integrity argument, in one assertion."""
    results = [_result(snippet="Acme Corp runs Datadog across its estate.")]
    proposed = ProposedCandidate(
        company_name="Acme Corp",
        source_url="https://example.com/a",
        employee_count_range="200-500",
        industry="fintech",
        incumbent_tooling=["Datadog"],
        evidence=[EvidenceItem(
            field="incumbent_tooling",
            source_url="https://example.com/a",
            quote="Acme Corp runs Datadog across its estate",
        )],
    )

    kept = extraction.verify_candidates(
        [proposed], results, _archetype(), query="q", angle="firmographic"
    )

    assert len(kept) == 1
    candidate = kept[0]
    assert candidate.incumbent_tooling == ["Datadog"]
    # Stated by the model, stated by nothing else.
    assert candidate.employee_count_range is None
    assert candidate.industry is None


def test_a_quote_that_is_not_in_the_source_does_not_support_a_field():
    results = [_result(snippet="Acme Corp is a company.")]
    proposed = ProposedCandidate(
        company_name="Acme Corp",
        source_url="https://example.com/a",
        employee_count_range="200-500",
        evidence=[
            EvidenceItem(
                field="employee_count_range",
                source_url="https://example.com/a",
                quote="Acme employs roughly 350 people",
            ),
            EvidenceItem(
                field="one_liner",
                source_url="https://example.com/a",
                quote="Acme Corp is a company",
            ),
        ],
    )

    with capture_logs() as logs:
        kept = extraction.verify_candidates(
            [proposed], results, _archetype(), query="q", angle="firmographic"
        )

    assert kept[0].employee_count_range is None
    entry = next(e for e in logs if e["event"] == "gtm_candidates_verified")
    assert entry["dropped"]["evidence_unsupported_quote"] == 1


def test_a_candidate_attributed_to_an_unreturned_url_is_rejected_whole():
    """A URL the search never returned is recall wearing a link."""
    results = [_result(url="https://example.com/a", snippet="Acme Corp runs Datadog.")]
    proposed = ProposedCandidate(
        company_name="Ghost Inc",
        source_url="https://never-searched.example/x",
        evidence=[EvidenceItem(
            field="one_liner",
            source_url="https://never-searched.example/x",
            quote="Ghost Inc is a company that exists",
        )],
    )

    with capture_logs() as logs:
        kept = extraction.verify_candidates(
            [proposed], results, _archetype(), query="q", angle="firmographic"
        )

    assert kept == []
    entry = next(e for e in logs if e["event"] == "gtm_candidates_verified")
    assert entry["dropped"]["unreturned_source_url"] == 1


def test_a_candidate_with_no_surviving_evidence_is_dropped():
    results = [_result(snippet="Nothing relevant here at all.")]
    proposed = ProposedCandidate(
        company_name="Acme Corp",
        source_url="https://example.com/a",
        industry="fintech",
        evidence=[EvidenceItem(
            field="industry",
            source_url="https://example.com/a",
            quote="Acme is a fintech company",
        )],
    )
    kept = extraction.verify_candidates(
        [proposed], results, _archetype(), query="q", angle="firmographic"
    )
    assert kept == []


def test_a_trivially_short_quote_cannot_support_a_field():
    """A three-character quote is a substring of nearly any snippet."""
    results = [_result(snippet="Acme Corp is a fintech company in Berlin.")]
    proposed = ProposedCandidate(
        company_name="Acme Corp",
        source_url="https://example.com/a",
        industry="fintech",
        evidence=[EvidenceItem(
            field="industry", source_url="https://example.com/a", quote="a",
        )],
    )
    assert extraction.verify_candidates(
        [proposed], results, _archetype(), query="q", angle="firmographic"
    ) == []


# ── Every candidate carries archetype + source URL ───────

def test_every_stored_candidate_carries_its_archetype_and_source():
    results = [_result(snippet="Acme Corp runs Datadog across its estate.")]
    proposed = ProposedCandidate(
        company_name="Acme Corp",
        source_url="https://example.com/a",
        incumbent_tooling=["Datadog"],
        match_reasons=["Runs the incumbent this archetype would switch from"],
        evidence=[EvidenceItem(
            field="incumbent_tooling",
            source_url="https://example.com/a",
            quote="Acme Corp runs Datadog across its estate",
        )],
    )

    candidate = extraction.verify_candidates(
        [proposed], results, _archetype(), query="q", angle="incumbent_tooling"
    )[0]

    assert candidate.archetype_id == "platform_lead"
    assert candidate.archetype_label == "Platform lead"
    assert candidate.source_url == "https://example.com/a"
    assert candidate.retrieved_at == RETRIEVED_AT
    assert candidate.match_reasons


def test_the_candidate_model_has_no_state_without_archetype_or_source():
    """A lead a founder cannot trace back is a lead they cannot act on."""
    with pytest.raises(Exception):
        Candidate(company_name="Acme", retrieved_at=RETRIEVED_AT)  # type: ignore[call-arg]


# ── Scoring is a rank ordering, and shows its arithmetic ──

def test_scoring_orders_by_score_and_breaks_ties_deterministically():
    def _candidate(name: str, tools: list[str]) -> Candidate:
        return Candidate(
            company_name=name,
            incumbent_tooling=tools,
            archetype_id="platform_lead",
            archetype_label="Platform lead",
            angle="firmographic",
            query="q",
            source_url="https://example.com/a",
            retrieved_at=RETRIEVED_AT,
            evidence=[EvidenceItem(
                field="incumbent_tooling", source_url="https://example.com/a",
                quote="uses the tooling described here",
            )],
        )

    ranked = scoring.score_candidates(
        [_candidate("Zeta", []), _candidate("Acme", ["Datadog", "New Relic"])],
        _archetype(),
    )

    assert [c.company_name for c in ranked] == ["Acme", "Zeta"]
    assert ranked[0].match_score > ranked[1].match_score
    # The arithmetic is exposed, not just the number.
    assert set(ranked[0].score_components) == set(scoring.SCORE_WEIGHTS)


def test_the_score_weights_sum_to_one():
    assert round(sum(scoring.SCORE_WEIGHTS.values()), 6) == 1.0


# ── Contact discovery is inert with the org setting off ──

def _contact_candidate() -> ProposedCandidate:
    return ProposedCandidate(
        company_name="Acme Corp",
        source_url="https://example.com/a",
        evidence=[EvidenceItem(
            field="one_liner", source_url="https://example.com/a",
            quote="Acme Corp builds observability tooling",
        )],
        contacts=[ProposedContact(
            full_name="Dana Vale",
            role_title="Director of Platform",
            employer="Acme Corp",
            source_url="https://example.com/a",
            quote="Dana Vale, Director of Platform at Acme Corp",
        )],
    )


def test_contacts_are_dropped_when_the_gate_is_off():
    """A prompt is not a control. This is the line that makes "off" mean off."""
    results = [_result(snippet=(
        "Acme Corp builds observability tooling. "
        "Dana Vale, Director of Platform at Acme Corp, spoke at the conference."
    ))]

    with capture_logs() as logs:
        kept = extraction.verify_candidates(
            [_contact_candidate()], results, _archetype(),
            query="q", angle="firmographic", include_contacts=False,
        )

    assert kept[0].contacts == []
    entry = next(e for e in logs if e["event"] == "gtm_candidates_verified")
    assert entry["dropped"]["contacts_dropped_gate_off"] == 1


def test_company_discovery_is_complete_with_the_gate_off():
    """Off is the working default, not a degraded mode.

    If contacts-off produced a thinner company record, someone would eventually
    turn it on for everyone to make the product look better.
    """
    results = [_result(snippet=(
        "Acme Corp builds observability tooling. "
        "Dana Vale, Director of Platform at Acme Corp, spoke at the conference."
    ))]
    off = extraction.verify_candidates(
        [_contact_candidate()], results, _archetype(),
        query="q", angle="firmographic", include_contacts=False,
    )[0]
    on = extraction.verify_candidates(
        [_contact_candidate()], results, _archetype(),
        query="q", angle="firmographic", include_contacts=True,
    )[0]

    assert off.model_dump(exclude={"contacts"}) == on.model_dump(exclude={"contacts"})
    assert on.contacts and not off.contacts


def test_a_contact_carries_its_source_url_and_retrieval_time():
    """Provenance is what makes an access or erasure request answerable."""
    results = [_result(snippet=(
        "Acme Corp builds observability tooling. "
        "Dana Vale, Director of Platform at Acme Corp, spoke at the conference."
    ))]
    contact = extraction.verify_candidates(
        [_contact_candidate()], results, _archetype(),
        query="q", angle="firmographic", include_contacts=True,
    )[0].contacts[0]

    assert contact.source_url == "https://example.com/a"
    assert contact.retrieved_at == RETRIEVED_AT


def test_a_contact_carrying_personal_contact_detail_is_dropped_whole():
    proposed = _contact_candidate()
    proposed.contacts[0].role_title = "Director of Platform, dana@acme.example"
    results = [_result(snippet=(
        "Acme Corp builds observability tooling. "
        "Dana Vale, Director of Platform at Acme Corp, spoke at the conference."
    ))]

    with capture_logs() as logs:
        kept = extraction.verify_candidates(
            [proposed], results, _archetype(),
            query="q", angle="firmographic", include_contacts=True,
        )

    assert kept[0].contacts == []
    assert "gtm_contact_rejected" in _events(logs)


def test_an_unreadable_gate_raises_rather_than_reading_as_off(monkeypatch):
    """A database error and a deliberate opt-out must not share a value."""
    class _Admin:
        def table(self, _name):
            raise ConnectionError("supabase unreachable")

    monkeypatch.setattr(privacy, "get_supabase_admin", lambda: _Admin())
    with pytest.raises(privacy.ContactGateUnavailableError):
        privacy.contact_discovery_gate("org-1")


def test_a_missing_gate_column_raises_rather_than_reading_as_off(monkeypatch):
    """NULL means migration 027 has not been applied, not "not opted in"."""
    monkeypatch.setattr(
        privacy, "get_supabase_admin",
        lambda: _FakeAdmin([{"id": "org-1", privacy.ORG_SETTING_COLUMN: None}]),
    )
    with pytest.raises(privacy.ContactGateUnavailableError):
        privacy.contact_discovery_gate("org-1")


def test_the_gate_reads_false_when_the_org_has_not_opted_in(monkeypatch):
    monkeypatch.setattr(
        privacy, "get_supabase_admin",
        lambda: _FakeAdmin([{"id": "org-1", privacy.ORG_SETTING_COLUMN: False}]),
    )
    assert privacy.contact_discovery_gate("org-1").enabled is False


def test_blocked_profile_domains_cover_the_obvious_one():
    """Contact-bearing searches exclude sites whose terms forbid this use.

    There is no scraper in this package; the block list goes to the search
    tool, so the provider never returns these for contact queries.
    """
    assert "linkedin.com" in privacy.CONTACT_BLOCKED_DOMAINS
    assert extraction._blocked_profile_url("https://www.linkedin.com/in/someone")
    assert not extraction._blocked_profile_url("https://acme.example/team/dana")


# ── Spend reaches the ledger ─────────────────────────────

class _FakeQuery:
    def __init__(self, data, count=0):
        self._data = data
        self._count = count

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def gte(self, *_a, **_k):
        return self

    def ilike(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def range(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        return SimpleNamespace(data=self._data, count=self._count)


class _FakeAdmin:
    def __init__(self, data, count=0):
        self._data = data
        self._count = count

    def table(self, _name):
        return _FakeQuery(self._data, self._count)


class _CapturingAdmin:
    """Records what would be inserted into `llm_usage`."""

    def __init__(self):
        self.rows: list[dict] = []
        self._admin = self

    def table(self, _name):
        return self

    def insert(self, rows):
        self.rows.extend(rows)
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


def _search_response(*, searches: int):
    """One turn: a search result block, a record_source call, then done."""
    web_result = SimpleNamespace(
        url="https://example.com/a",
        title="Acme Corp",
        page_age="July 2026",
    )
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="web_search_tool_result", content=[web_result]),
            SimpleNamespace(
                type="tool_use",
                id="toolu_1",
                name="record_source",
                input={
                    "url": "https://example.com/a",
                    "title": "Acme Corp",
                    "summary": "Acme Corp runs Datadog across its estate.",
                },
            ),
        ],
        stop_reason="end_turn",
        stop_details=None,
        usage=SimpleNamespace(
            input_tokens=18_400,
            output_tokens=940,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
            server_tool_use=SimpleNamespace(web_search_requests=searches),
        ),
    )


class _FakeAnthropic:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []
        self.messages = self

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_search_spend_reaches_the_usage_ledger(monkeypatch):
    """Spend that is not in `llm_usage` is invisible to reconcile_run_cost."""
    from app.services.billing import usage_ledger

    capture = _CapturingAdmin()
    monkeypatch.setattr(usage_ledger, "get_supabase_admin", lambda: capture)

    adapter = AnthropicWebSearchAdapter(
        client=_FakeAnthropic([_search_response(searches=2)]),
        model="claude-haiku-4-5",
    )

    with usage_ledger.usage_context("gtm_discovery", organization_id="org-1"):
        results = await adapter.search("companies using Datadog")

    assert [r.url for r in results] == ["https://example.com/a"]
    assert results[0].snippet.startswith("Acme Corp runs Datadog")

    assert capture.rows, "the search turn's tokens never reached llm_usage"
    row = capture.rows[0]
    assert row["stage"] == "gtm_discovery"
    assert row["organization_id"] == "org-1"
    assert row["input_tokens"] == 18_400
    assert row["output_tokens"] == 940
    assert row["cost_usd"] > 0


@pytest.mark.asyncio
async def test_the_adapter_counts_searches_because_the_ledger_cannot(monkeypatch):
    """The per-search charge has no column in `llm_usage`.

    `searches_performed` is the only place it is countable, which is why it is
    on the adapter and why `discovery.py` logs the dollar figure per run.
    """
    from app.services.billing import usage_ledger

    monkeypatch.setattr(usage_ledger, "get_supabase_admin", lambda: _CapturingAdmin())
    adapter = AnthropicWebSearchAdapter(
        client=_FakeAnthropic([_search_response(searches=2)]),
        model="claude-haiku-4-5",
    )
    with usage_ledger.usage_context("gtm_discovery", organization_id="org-1"):
        await adapter.search("q")

    assert adapter.searches_performed == 2
    assert search_fee_usd(2) == WEB_SEARCH_USD_PER_REQUEST * 2


@pytest.mark.asyncio
async def test_a_search_tool_error_is_logged_and_yields_no_sources(monkeypatch):
    """On an error the API returns 200 with `content` as an error object.

    Reading it as a list of results would yield zero sources and no error —
    "the market is empty" instead of "the search failed".
    """
    from app.services.billing import usage_ledger

    monkeypatch.setattr(usage_ledger, "get_supabase_admin", lambda: _CapturingAdmin())
    errored = SimpleNamespace(
        content=[SimpleNamespace(
            type="web_search_tool_result",
            content=SimpleNamespace(
                type="web_search_tool_result_error", error_code="max_uses_exceeded"
            ),
        )],
        stop_reason="end_turn",
        stop_details=None,
        usage=SimpleNamespace(
            input_tokens=300, output_tokens=20,
            cache_read_input_tokens=0, cache_creation_input_tokens=0,
            server_tool_use=SimpleNamespace(web_search_requests=2),
        ),
    )
    adapter = AnthropicWebSearchAdapter(
        client=_FakeAnthropic([errored]), model="claude-haiku-4-5"
    )

    with capture_logs() as logs:
        with usage_ledger.usage_context("gtm_discovery", organization_id="org-1"):
            results = await adapter.search("q")

    assert results == []
    entry = next(e for e in logs if e["event"] == "gtm_search_tool_error")
    assert entry["error_code"] == "max_uses_exceeded"


@pytest.mark.asyncio
async def test_a_source_the_search_did_not_return_is_dropped(monkeypatch):
    from app.services.billing import usage_ledger

    monkeypatch.setattr(usage_ledger, "get_supabase_admin", lambda: _CapturingAdmin())
    response = _search_response(searches=1)
    response.content[1].input["url"] = "https://invented.example/x"
    adapter = AnthropicWebSearchAdapter(
        client=_FakeAnthropic([response]), model="claude-haiku-4-5"
    )

    with capture_logs() as logs:
        with usage_ledger.usage_context("gtm_discovery", organization_id="org-1"):
            results = await adapter.search("q")

    assert results == []
    assert "gtm_search_unreturned_urls_dropped" in _events(logs)


# ── Pricing accounts for both tokens and the per-search fee ──

def test_the_estimate_includes_the_per_search_charge():
    """Web search bills $10 per 1,000 searches on top of tokens.

    An estimate built from tokens alone is wrong in a direction the token
    ledger cannot reveal.
    """
    estimate = estimate_discovery_cost(9)
    assert estimate.searches == 9 * SEARCHES_PER_QUERY
    assert estimate.search_fee_usd == pytest.approx(
        float(WEB_SEARCH_USD_PER_REQUEST) * 9 * SEARCHES_PER_QUERY
    )
    assert estimate.actual_cost_usd == pytest.approx(
        estimate.token_cost_usd + estimate.search_fee_usd
    )
    assert estimate.credits > 0


def test_the_estimate_is_flagged_unmeasured():
    """These profiles are constructed from enforced bounds, not from the ledger.

    Flipping `measured` is what a session that re-derives them from live
    `llm_usage` rows should have to do deliberately.
    """
    assert estimate_discovery_cost(1).measured is False


def test_the_estimate_is_capped_at_the_query_ceiling():
    capped = estimate_discovery_cost(query_compiler.MAX_QUERIES_PER_DISCOVERY + 50)
    assert capped.queries == query_compiler.MAX_QUERIES_PER_DISCOVERY


# ── The list envelope, and paging past page 1 ────────────

def test_list_candidates_returns_items_and_a_total(monkeypatch):
    """A bare array means a user with 50 rows never reaches page 2."""
    monkeypatch.setattr(
        store, "get_supabase_admin",
        lambda: _FakeAdmin([{"id": "c1", "company_name": "Acme"}], count=137),
    )
    items, total = store.list_candidates("org-1", limit=50, offset=0)
    assert items == [{"id": "c1", "company_name": "Acme"}]
    assert total == 137


class _RecordingInsertAdmin:
    """Records inserts per table, returning rows in reversed order.

    Reversed on purpose: it stands in for a backend that does not guarantee the
    order of a multi-row insert's returned representation.
    """

    def __init__(self):
        self.inserts: dict[str, list[dict]] = {}
        self._table = ""
        self._rows: list[dict] = []

    def table(self, name):
        self._table = name
        return self

    def insert(self, rows):
        self.inserts.setdefault(self._table, []).extend(rows)
        self._rows = list(reversed(rows))
        return self

    def execute(self):
        return SimpleNamespace(data=self._rows, count=len(self._rows))


def test_a_contact_is_filed_against_the_right_candidate(monkeypatch):
    """Pairing on insert order would file a named person under the wrong company.

    Invisible until somebody notices the name does not belong there — and a
    data-protection problem, not just a data-quality one.
    """
    admin = _RecordingInsertAdmin()
    monkeypatch.setattr(store, "get_supabase_admin", lambda: admin)

    def _candidate(name: str, contacts: list) -> Candidate:
        return Candidate(
            company_name=name,
            archetype_id="platform_lead",
            archetype_label="Platform lead",
            angle="firmographic",
            query="q",
            source_url="https://example.com/a",
            retrieved_at=RETRIEVED_AT,
            contacts=contacts,
        )

    from app.services.gtm.schema import Contact

    dana = Contact(
        full_name="Dana Vale",
        source_url="https://example.com/a",
        retrieved_at=RETRIEVED_AT,
    )
    run = {"id": "run-1", "project_id": "proj-1", "organization_id": "org-1"}
    store.insert_candidates(
        run, [_candidate("Acme", []), _candidate("Zeta", [dana])]
    )

    candidates = {row["company_name"]: row["id"] for row in admin.inserts["gtm_candidates"]}
    contacts = admin.inserts["gtm_contacts"]
    assert len(contacts) == 1
    assert contacts[0]["candidate_id"] == candidates["Zeta"]


def test_the_gtm_routes_are_registered():
    from app.main import create_app

    paths = {r.path for r in create_app().routes if hasattr(r, "path")}
    for expected in (
        "/api/gtm/discover",
        "/api/gtm/estimate",
        "/api/gtm/settings",
        "/api/gtm/purge",
        "/api/gtm/runs",
        "/api/gtm/candidates",
        "/api/gtm/candidates/{id}",
    ):
        assert expected in paths, f"{expected} is not registered"
