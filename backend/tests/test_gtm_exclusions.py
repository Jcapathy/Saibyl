"""A competitor is not a buyer.

The defect these pin arrived from live use: a founder asked discovery for
companies to sell to and it returned the companies they sell against. `companies
using Datadog "observability tooling"` describes Datadog's own site better than
it describes any Datadog customer, so Datadog came back at the top of a prospect
list.

It is the same failure class as the rest of this suite, one level out. Elsewhere
a lookup miss and a legitimate absence share one value; here *no exclusion ran*
and *nothing needed excluding* shared one value — an unfiltered list — and
nothing logged, nothing failed, and the run reported success. So these tests
assert on both sides of that line: what is kept out, and that an empty exclusion
set is legible as an empty one.

Two mechanisms, tested separately because only one of them is enforced:

  * the compiler negates names into the query text, which a provider may honour;
  * `extraction.verify_candidates` drops them from what comes back, which is not
    optional and is the only thing protecting the incumbent angle — a query that
    asks `companies using Datadog` cannot also say `-Datadog`.

Log assertions use `structlog.testing.capture_logs`; `caplog` passes vacuously
in this codebase (`test_log_capture_canary.py` guards it).
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from structlog.testing import capture_logs

from app.services.engine.personas.icp_schema import (
    AdversarialArchetype,
    Competitor,
    ICPArchetype,
    ICPProfile,
)
from app.services.gtm import query_compiler
from app.services.gtm.exclusions import (
    MAX_EXCLUSIONS_IN_QUERY,
    build_exclusions,
)
from app.services.gtm.extraction import verify_candidates
from app.services.gtm.schema import EvidenceItem, ProposedCandidate, SearchResult

RETRIEVED_AT = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)

# A real ICP, in the shape the reported defect arrived in: a founder selling an
# observability tool, whose buyers run Datadog and New Relic, and whose uploaded
# material named Honeycomb as a rival.
_SNIPPET = (
    "Datadog is a monitoring and security platform for cloud applications. "
    "Northwind Freight runs Datadog across its logistics estate."
)


def _profile(**overrides) -> ICPProfile:
    base = {
        "name": "Observability buyers",
        "category": "observability tooling",
        "product_summary": "An observability tool",
        "competitors": [
            Competitor(name="Honeycomb", mentioned_in=["doc-competitor-1"]),
        ],
        "archetypes": [
            ICPArchetype(
                id="platform_lead",
                label="Platform lead",
                role="platform engineer",
                seniority="director",
                incumbent_tooling=["Datadog", "New Relic"],
                pains=["alert fatigue from noisy dashboards"],
            ),
        ],
    }
    base.update(overrides)
    return ICPProfile(**base)


def _result(url: str = "https://example.com/a", snippet: str = _SNIPPET) -> SearchResult:
    return SearchResult(
        provider="test",
        query="companies using Datadog",
        url=url,
        title="Datadog customers",
        snippet=snippet,
        retrieved_at=RETRIEVED_AT,
    )


def _proposed(name: str, *, domain: str | None = None) -> ProposedCandidate:
    """A candidate whose evidence genuinely survives verification.

    The quote is verbatim from `_SNIPPET`, so anything dropped below is dropped
    by the exclusion filter and not by the evidence rule — which is what makes
    these assertions about exclusion rather than about quoting.
    """
    return ProposedCandidate(
        company_name=name,
        domain=domain,
        source_url="https://example.com/a",
        incumbent_tooling=["Datadog"],
        evidence=[EvidenceItem(
            field="incumbent_tooling",
            source_url="https://example.com/a",
            quote="Datadog is a monitoring and security platform",
        )],
    )


def _verify(proposed, profile: ICPProfile):
    return verify_candidates(
        proposed,
        [_result()],
        profile.archetypes[0],
        query="companies using Datadog",
        angle="incumbent_tooling",
        exclusions=build_exclusions(profile),
    )


# ── What the set is derived from ─────────────────────────

def test_the_exclusion_set_is_derived_from_the_profile_not_a_vendor_list():
    """Three sources, all on the founder's own profile.

    A hardcoded list of vendor names would be wrong for every founder outside
    whichever categories somebody thought to type in. These come from what this
    founder uploaded and what this founder's buyers run.
    """
    profile = _profile(
        adversarial=[AdversarialArchetype(
            id="incumbent_rep",
            label="Incumbent rep",
            role="incumbent_employee",
            competitor_name="Splunk",
            grounded_in=["doc-competitor-2"],
        )],
    )
    exclusions = build_exclusions(profile)

    assert [c.name for c in exclusions.companies] == [
        "Honeycomb",   # named in uploaded competitor material
        "Splunk",      # named by a grounded incumbent-aligned archetype
        "Datadog",     # makes a tool the buyers already run
        "New Relic",
    ]
    assert {c.name: c.reason for c in exclusions.companies} == {
        "Honeycomb": "named_rival",
        "Splunk": "named_rival",
        "Datadog": "incumbent_tool",
        "New Relic": "incumbent_tool",
    }
    assert exclusions.category == "observability tooling"


def test_an_ungrounded_competitor_is_never_excluded_or_named():
    """DECISIONS §7's guardrail, applied to this feature.

    A competitor with no uploaded document behind it may be something the model
    remembered. The excluded list is rendered to the founder by name, so
    excluding on one would present a possibly-invented company as their rival.
    Counted so the founder learns something is missing; never named.
    """
    profile = _profile(competitors=[
        Competitor(name="Honeycomb", mentioned_in=["doc-competitor-1"]),
        Competitor(name="Chronosphere", mentioned_in=[]),
    ])
    with capture_logs() as logs:
        exclusions = build_exclusions(profile)

    names = [c.name for c in exclusions.companies]
    assert "Honeycomb" in names
    assert "Chronosphere" not in names
    assert exclusions.ungrounded_count == 1
    assert "Chronosphere" not in exclusions.sentence

    entry = next(
        e for e in logs if e["event"] == "gtm_exclusions_ungrounded_competitors"
    )
    assert entry["competitors"] == ["Chronosphere"]


def test_nothing_to_exclude_says_so_rather_than_reading_as_filtered():
    """An empty set is a state, not a silence.

    This is the failure this whole module exists to close: before it, a run that
    excluded nothing and a run whose exclusion never happened produced the same
    unfiltered list and the same logs.
    """
    profile = _profile(
        competitors=[],
        archetypes=[ICPArchetype(
            id="platform_lead",
            label="Platform lead",
            role="platform engineer",
            incumbent_tooling=[],
            pains=["alert fatigue"],
        )],
    )
    with capture_logs() as logs:
        exclusions = build_exclusions(profile)

    assert exclusions.companies == []
    assert "doesn't name a rival" in exclusions.sentence
    entry = next(e for e in logs if e["event"] == "gtm_exclusions_built")
    assert entry["excluded"] == 0


# ── The compiled queries exclude the founder's own category ──

def test_compiled_queries_exclude_the_profiles_own_category_vendors():
    """The acceptance criterion, stated as an assertion.

    Every query that *can* carry a negative does, and the names it carries are
    the ones the profile says sell what the founder sells.
    """
    profile = _profile()
    queries = query_compiler.compile_queries(profile)
    by_angle = {q.angle: q for q in queries}

    assert by_angle["firmographic"].excluded_terms == ["Honeycomb", "Datadog", "New Relic"]
    assert by_angle["pain_trigger"].excluded_terms == ["Honeycomb", "Datadog", "New Relic"]

    for angle in ("firmographic", "pain_trigger"):
        text = by_angle[angle].query
        assert '-Datadog' in text
        assert '-"New Relic"' in text
        assert "-Honeycomb" in text

    # And the exclusions are not merely recorded: every query that names a
    # competitor names it negatively.
    for query in queries:
        for term in query.excluded_terms:
            assert f"-{term}" in query.query or f'-"{term}"' in query.query


def test_the_incumbent_angle_does_not_negate_the_tool_it_asks_about():
    """`companies using Datadog -Datadog` returns nothing at all.

    So the most load-bearing of the three angles must not negate its own
    subject, and Datadog has to be dropped on the way back instead. The next
    test is the other half of this one; neither is sufficient alone.
    """
    queries = query_compiler.compile_queries(_profile())
    incumbent = next(q for q in queries if q.angle == "incumbent_tooling")

    assert "-Datadog" not in incumbent.query
    assert '-"New Relic"' not in incumbent.query
    # The competitor it is *not* asking about is still negated.
    assert incumbent.excluded_terms == ["Honeycomb"]
    assert "-Honeycomb" in incumbent.query


def test_a_query_carries_at_most_the_negative_term_cap():
    """Past a handful the negatives outweigh the query they qualify.

    The post-filter still enforces the whole set, so the cap costs noise rather
    than safety — asserted here so a future raise is a deliberate one.
    """
    profile = _profile(competitors=[
        Competitor(name=f"Rival{n}", mentioned_in=["doc-competitor-1"])
        for n in range(MAX_EXCLUSIONS_IN_QUERY + 4)
    ])
    exclusions = build_exclusions(profile)
    queries = query_compiler.compile_queries(profile)

    assert len(exclusions.companies) > MAX_EXCLUSIONS_IN_QUERY
    assert all(len(q.excluded_terms) <= MAX_EXCLUSIONS_IN_QUERY for q in queries)


def test_the_compiler_is_still_deterministic_with_exclusions_applied():
    """The preview is only a preview if it is what runs."""
    profile = _profile()
    first = query_compiler.compile_queries(profile)
    second = query_compiler.compile_queries(profile)
    assert [q.model_dump() for q in first] == [q.model_dump() for q in second]


# ── The enforced half: what comes back is filtered ───────

def test_the_vendor_named_in_the_query_is_dropped_from_the_results():
    """The reported defect, end to end.

    "Companies using Datadog" returned Datadog. The query cannot negate it, so
    this is the line that has to catch it.
    """
    profile = _profile()
    with capture_logs() as logs:
        kept = _verify([_proposed("Datadog"), _proposed("Northwind Freight")], profile)

    assert [c.company_name for c in kept] == ["Northwind Freight"]
    entry = next(e for e in logs if e["event"] == "gtm_candidates_verified")
    assert entry["dropped"]["sells_what_the_founder_sells"] == 1
    assert entry["excluded_as_competitor"] == ["Datadog~Datadog"]
    assert entry["exclusions_applied"] is True


def test_a_competitor_is_dropped_by_domain_when_the_name_does_not_match():
    """`datadoghq.com` under some other company name is still Datadog."""
    profile = _profile()
    kept = _verify(
        [_proposed("Datadog Cloud Monitoring", domain="www.datadoghq.com")],
        profile,
    )
    assert kept == []


def test_a_legal_suffix_does_not_let_a_competitor_through():
    profile = _profile()
    kept = _verify([_proposed("New Relic, Inc.")], profile)
    assert kept == []


def test_a_real_buyer_is_not_dropped_by_a_partial_word_match():
    """The filter errs toward exclusion, but not on a coincidence.

    "Relic Restorations" shares a word with "New Relic" and sells nothing the
    founder sells. Matching on whole contiguous tokens is what keeps it in.
    """
    profile = _profile()
    kept = _verify(
        [
            _proposed("Relic Restorations"),
            _proposed("Honeycomb Logistics Group"),
            _proposed("Northwind Freight", domain="northwind.example"),
        ],
        profile,
    )
    kept_names = [c.company_name for c in kept]
    assert "Relic Restorations" in kept_names
    assert "Northwind Freight" in kept_names
    # "Honeycomb Logistics Group" contains the rival's full name as a token run
    # and is excluded. Stated rather than left implicit: this is the deliberate
    # false-positive cost, and it is why the estimate names what it kept out.
    assert "Honeycomb Logistics Group" not in kept_names


def test_the_post_filter_reports_when_it_did_not_run():
    """No exclusion set and an exclusion set that matched nothing differ.

    Without this, a caller that forgot to pass exclusions would produce exactly
    the log line of a clean run.
    """
    profile = _profile()
    with capture_logs() as logs:
        kept = verify_candidates(
            [_proposed("Datadog")],
            [_result()],
            profile.archetypes[0],
            query="companies using Datadog",
            angle="incumbent_tooling",
        )

    assert [c.company_name for c in kept] == ["Datadog"]
    entry = next(e for e in logs if e["event"] == "gtm_candidates_verified")
    assert entry["exclusions_applied"] is False
    assert entry["exclusions_available"] == 0


# ── What the founder is shown ────────────────────────────

def test_the_preview_names_what_was_excluded_and_why():
    """`GET /gtm/estimate` renders this. It has to read as English.

    A founder who has never heard the phrase "ideal customer profile" has to be
    able to look at this before spending credits and say "no, Datadog is not my
    rival" — which is only possible if the reason travels with the name.
    """
    payload = build_exclusions(_profile()).model_dump(mode="json")

    assert payload["category"] == "observability tooling"
    assert [c["name"] for c in payload["companies"]] == [
        "Honeycomb", "Datadog", "New Relic",
    ]
    assert payload["companies"][0]["note"] == (
        "your uploaded material names them as a rival"
    )
    assert payload["companies"][1]["note"] == (
        "makes a tool your buyers already run, so they sell what you sell"
    )
    assert payload["sentence"] == (
        "Leaving out 3 companies that sell what you sell, so they don't crowd "
        "out real buyers: Honeycomb, Datadog and New Relic."
    )


def test_the_estimate_endpoint_returns_the_exclusions_beside_the_queries(monkeypatch):
    """The founder cannot argue with a filter they cannot see.

    Discovery was already deterministic and already showed its queries; what it
    never showed was what those queries would refuse to return. Asserted at the
    endpoint rather than on `build_exclusions`, because the payload assembly is
    the part that can silently drop a key.
    """
    import asyncio

    from app.api import gtm as gtm_api

    monkeypatch.setattr(
        gtm_api, "_fetch_profile",
        lambda profile_id, org_id: {"profile": _profile().model_dump(mode="json")},
    )
    monkeypatch.setattr(
        gtm_api, "check_discovery_budget",
        lambda org_id, queries: SimpleNamespace(model_dump=lambda: {"allowed": True}),
    )

    payload = asyncio.run(gtm_api.estimate(
        icp_profile_id="icp-1",
        max_queries=12,
        auth={"org_id": "org-1", "user": {"id": "user-1"}},
    ))

    assert set(payload) == {"queries", "excluded", "estimate", "budget"}
    assert [c["name"] for c in payload["excluded"]["companies"]] == [
        "Honeycomb", "Datadog", "New Relic",
    ]
    assert payload["excluded"]["sentence"]
    assert all("note" in c for c in payload["excluded"]["companies"])

    # And the per-query record of what each search negated, so the founder can
    # see that the one asking about Datadog is the one that could not.
    by_angle = {q["angle"]: q["excluded_terms"] for q in payload["queries"]}
    assert by_angle["incumbent_tooling"] == ["Honeycomb"]
    assert by_angle["firmographic"] == ["Honeycomb", "Datadog", "New Relic"]


def test_no_founder_facing_string_uses_the_product_s_internal_vocabulary():
    """The register of `AudienceReview.tsx`, enforced.

    These strings reach a founder. None of the words below mean anything to
    them, and several mean the wrong thing.
    """
    jargon = (
        "icp", "variant", "a/b", "adversarial", "cohort", "arena", "lens",
        "archetype", "canonical", "valence", "firmographic", "incumbent",
    )
    exclusions = build_exclusions(_profile())
    rendered = " ".join(
        [exclusions.sentence] + [c.note for c in exclusions.companies]
    ).lower()

    for word in jargon:
        assert word not in rendered, f"{word!r} reaches the founder"
