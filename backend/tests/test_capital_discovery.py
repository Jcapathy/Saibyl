"""Nothing enters the family-office bank that the open web did not say.

The bank goes out under Saido Labs' name as a recommendation, which makes an
invented field worse than a missing one: a founder who finds one wrong cheque
range has no reason to believe any other row, and the cost lands on a real firm
receiving a pitch we caused.

So `verify_firms` is pure — no network, no clock but the one passed in — and
every guarantee below is settled here by assertion rather than by watching a
live curation run.

The guarantees, in the order they matter:

1. A firm the search did not return cannot enter, whatever the model wrote.
2. A field with no supporting quote is absent, not guessed.
3. A firm with no evidenced thesis is not a record — it is a name, and a name
   cannot be matched, which is the entire product.
4. An unstated inbound posture becomes the most conservative real answer, never
   an invented route.
5. Personal data cannot enter, because the schema refuses it and this module
   cannot talk its way past a type.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.capital.discovery import (
    MIN_QUOTE_CHARS,
    ProposedFirm,
    curation_queries,
    verify_firms,
)
from app.services.capital.schema import DEFAULT_FRESHNESS_DAYS
from app.services.gtm.schema import SearchResult

NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
URL = "https://ashgrove.example/approach"
OTHER = "https://directory.example/ashgrove"

THESIS = "We back founders in clinical software from first revenue onward."
ROUTE = "Send material through the form on this page; we read everything."
SECTORS = "Our published focus is healthcare and clinical workflow software."


def _result(url: str = URL, snippet: str = "") -> SearchResult:
    return SearchResult(
        provider="test", query="family office", url=url, title="Ash Grove",
        snippet=snippet, retrieved_at=NOW,
    )


def _sources() -> list[SearchResult]:
    return [_result(URL, f"{THESIS} {ROUTE} {SECTORS}")]


def _proposed(**overrides) -> ProposedFirm:
    base = {
        "firm_name": "Ash Grove Office",
        "domain": "ashgrove.example",
        "firm_type": "single_family",
        "thesis": THESIS,
        "sectors": ["healthcare"],
        "stages": [],
        "check_size_low": None,
        "check_size_high": None,
        "geography": [],
        "notable_investments": [],
        "inbound_kind": "submission_form",
        "inbound_value": "https://ashgrove.example/submit",
        "inbound_source_url": URL,
        "source_url": URL,
        "source_title": "How to approach us",
        "evidence": [
            {"field": "thesis", "source_url": URL, "quote": THESIS},
            {"field": "inbound_kind", "source_url": URL, "quote": ROUTE},
            {"field": "inbound_value", "source_url": URL, "quote": ROUTE},
            {"field": "sectors", "source_url": URL, "quote": SECTORS},
        ],
    }
    base.update(overrides)
    return ProposedFirm.model_validate(base)


# ---------------------------------------------------------------------------
# The happy path, so the failures below mean something
# ---------------------------------------------------------------------------

def test_a_fully_evidenced_firm_enters_the_bank():
    verified = verify_firms([_proposed()], _sources(), now=NOW)

    assert len(verified.firms) == 1
    firm = verified.firms[0]
    assert firm.firm_name == "Ash Grove Office"
    assert firm.thesis == THESIS
    assert firm.sectors == ["healthcare"]
    assert firm.inbound_path.kind == "submission_form"
    assert firm.source_url == URL


def test_freshness_is_stamped_rather_than_left_to_a_caller():
    """A record with no expiry never goes stale, which is how an investor list
    launders decay into confidence."""
    firm = verify_firms([_proposed()], _sources(), now=NOW).firms[0]

    assert firm.retrieved_at == NOW
    assert firm.stale_after == NOW + timedelta(days=DEFAULT_FRESHNESS_DAYS)
    assert firm.stale_after > firm.retrieved_at


# ---------------------------------------------------------------------------
# 1. The provenance gate
# ---------------------------------------------------------------------------

def test_a_firm_whose_source_the_search_never_returned_is_dropped():
    """The model can write any URL it likes. It cannot write one the provider
    returned without the provider having returned it."""
    verified = verify_firms(
        [_proposed(source_url="https://invented.example/page")],
        _sources(),
        now=NOW,
    )

    assert verified.firms == []
    assert verified.rejections["source_url_not_returned"] == 1


def test_evidence_citing_an_unreturned_url_supports_nothing():
    proposed = _proposed(evidence=[
        {"field": "thesis", "source_url": URL, "quote": THESIS},
        {"field": "sectors", "source_url": "https://elsewhere.example", "quote": SECTORS},
        {"field": "inbound_kind", "source_url": URL, "quote": ROUTE},
        {"field": "inbound_value", "source_url": URL, "quote": ROUTE},
    ])
    verified = verify_firms([proposed], _sources(), now=NOW)

    assert verified.firms[0].sectors == [], "a field kept its unevidenced value"
    assert verified.rejections["evidence_cites_unreturned_url"] == 1


# ---------------------------------------------------------------------------
# 2. The evidence gate — a field is absent, never guessed
# ---------------------------------------------------------------------------

def test_a_cheque_range_no_source_states_is_absent_not_a_band():
    """The failure this exists for. A founder who finds one invented range has
    no reason to believe any other field."""
    proposed = _proposed(check_size_low=1_000_000, check_size_high=5_000_000)
    firm = verify_firms([proposed], _sources(), now=NOW).firms[0]

    assert firm.check_size_low is None
    assert firm.check_size_high is None


def test_a_quote_that_is_not_in_the_snippet_supports_nothing():
    proposed = _proposed(
        notable_investments=["Acme Health"],
        evidence=[
            {"field": "thesis", "source_url": URL, "quote": THESIS},
            {"field": "inbound_kind", "source_url": URL, "quote": ROUTE},
            {"field": "inbound_value", "source_url": URL, "quote": ROUTE},
            {
                "field": "notable_investments",
                "source_url": URL,
                "quote": "We led the Series A in Acme Health last spring.",
            },
        ],
    )
    verified = verify_firms([proposed], _sources(), now=NOW)

    assert verified.firms[0].notable_investments == []
    assert verified.rejections["unsupported_quote"] == 1


def test_a_quote_too_short_to_be_evidence_is_not_evidence():
    """A three-character quote appears in almost any snippet. A short one is
    not evidence, it is a coincidence about to be counted as one."""
    short = THESIS[: MIN_QUOTE_CHARS - 4]
    assert short in THESIS, "the fixture must actually be a substring"

    proposed = _proposed(
        geography=["United Kingdom"],
        evidence=[
            {"field": "thesis", "source_url": URL, "quote": THESIS},
            {"field": "inbound_kind", "source_url": URL, "quote": ROUTE},
            {"field": "inbound_value", "source_url": URL, "quote": ROUTE},
            {"field": "geography", "source_url": URL, "quote": short},
        ],
    )
    verified = verify_firms([proposed], _sources(), now=NOW)

    assert verified.firms[0].geography == []
    assert verified.rejections["unsupported_quote"] == 1


def test_an_evidence_field_nobody_declared_is_counted_not_ignored():
    proposed = _proposed(evidence=[
        {"field": "thesis", "source_url": URL, "quote": THESIS},
        {"field": "inbound_kind", "source_url": URL, "quote": ROUTE},
        {"field": "inbound_value", "source_url": URL, "quote": ROUTE},
        {"field": "assets_under_management", "source_url": URL, "quote": THESIS},
    ])
    verified = verify_firms([proposed], _sources(), now=NOW)

    assert verified.rejections["unknown_evidence_field"] == 1


# ---------------------------------------------------------------------------
# 3. No thesis, no record
# ---------------------------------------------------------------------------

def test_a_firm_with_no_evidenced_thesis_is_not_a_record():
    """The thesis is the mechanism of the match — it is what gets compared to
    the founder's material and quoted back to them. Without it the row is a
    name, and a name cannot be matched to anything."""
    proposed = _proposed(evidence=[
        {"field": "inbound_kind", "source_url": URL, "quote": ROUTE},
        {"field": "inbound_value", "source_url": URL, "quote": ROUTE},
    ])
    verified = verify_firms([proposed], _sources(), now=NOW)

    assert verified.firms == []
    assert verified.rejections["thesis_unevidenced"] == 1


def test_an_empty_thesis_is_refused_even_when_evidence_claims_one():
    proposed = _proposed(thesis="   ")
    verified = verify_firms([proposed], _sources(), now=NOW)

    assert verified.firms == []
    assert verified.rejections["thesis_unevidenced"] == 1


# ---------------------------------------------------------------------------
# 4. Inbound: a refusal is an answer, and an unknown is not a route
# ---------------------------------------------------------------------------

def test_an_unstated_inbound_posture_becomes_no_inbound_not_a_guess():
    """Family offices are private by design. Guessing that one accepts
    submissions causes a real approach to a firm that never invited it."""
    proposed = _proposed(evidence=[
        {"field": "thesis", "source_url": URL, "quote": THESIS},
    ])
    verified = verify_firms([proposed], _sources(), now=NOW)

    firm = verified.firms[0]
    assert firm.inbound_path.kind == "no_inbound"
    assert not firm.inbound_path.value
    assert verified.rejections["inbound_unevidenced_defaulted"] == 1


def test_a_stated_refusal_carries_no_route():
    """A route stored next to 'they take no inbound' is a route somebody
    uses anyway."""
    refusal = "We consider opportunities only through people we already know."
    sources = [_result(URL, f"{THESIS} {refusal}")]
    proposed = _proposed(
        inbound_kind="warm_intro_only",
        inbound_value="submissions@ashgrove.example",
        evidence=[
            {"field": "thesis", "source_url": URL, "quote": THESIS},
            {"field": "inbound_kind", "source_url": URL, "quote": refusal},
        ],
    )
    firm = verify_firms([proposed], sources, now=NOW).firms[0]

    assert firm.inbound_path.kind == "warm_intro_only"
    assert not firm.inbound_path.value


def test_an_evidenced_kind_with_an_unevidenced_route_falls_back_to_no_inbound():
    proposed = _proposed(evidence=[
        {"field": "thesis", "source_url": URL, "quote": THESIS},
        {"field": "inbound_kind", "source_url": URL, "quote": ROUTE},
    ])
    verified = verify_firms([proposed], _sources(), now=NOW)

    assert verified.firms[0].inbound_path.kind == "no_inbound"
    assert verified.rejections["inbound_route_unevidenced"] == 1


# ---------------------------------------------------------------------------
# 5. The privacy boundary, which this module may not argue with
# ---------------------------------------------------------------------------

def test_a_thesis_carrying_a_personal_address_is_refused_whole():
    """`schema.FamilyOffice` scans every stored string. The thesis is the field
    it exists for: it is copied off a firm's own page, and firm pages have
    footers."""
    leaky = (
        "We back clinical software founders. Reach James at "
        "james.holt@ashgrove.example for anything."
    )
    sources = [_result(URL, leaky)]
    proposed = _proposed(thesis=leaky, evidence=[
        {"field": "thesis", "source_url": URL, "quote": leaky},
    ])
    verified = verify_firms([proposed], sources, now=NOW)

    assert verified.firms == []
    assert verified.rejections["schema_refused"] == 1


def test_an_individuals_address_cannot_enter_as_an_inbound_route():
    """Nobody is named `submissions`. That distinction is the whole gate."""
    line = "Write to our partner directly at j.holt@ashgrove.example any time."
    sources = [_result(URL, f"{THESIS} {line}")]
    proposed = _proposed(
        inbound_kind="firm_address",
        inbound_value="j.holt@ashgrove.example",
        evidence=[
            {"field": "thesis", "source_url": URL, "quote": THESIS},
            {"field": "inbound_kind", "source_url": URL, "quote": line},
            {"field": "inbound_value", "source_url": URL, "quote": line},
        ],
    )
    verified = verify_firms([proposed], sources, now=NOW)

    assert verified.firms == []
    assert verified.rejections["schema_refused"] == 1


def test_a_published_role_address_is_allowed():
    """The one deliberate carve-out, so the test suite proves it is narrow
    rather than closed."""
    line = "Send material to submissions@ashgrove.example and we will read it."
    sources = [_result(URL, f"{THESIS} {line}")]
    proposed = _proposed(
        inbound_kind="firm_address",
        inbound_value="submissions@ashgrove.example",
        evidence=[
            {"field": "thesis", "source_url": URL, "quote": THESIS},
            {"field": "inbound_kind", "source_url": URL, "quote": line},
            {"field": "inbound_value", "source_url": URL, "quote": line},
        ],
    )
    firm = verify_firms([proposed], sources, now=NOW).firms[0]

    assert firm.inbound_path.value == "submissions@ashgrove.example"


# ---------------------------------------------------------------------------
# Deduplication — a bank that lists a firm twice tells a founder to pitch twice
# ---------------------------------------------------------------------------

def test_the_same_firm_under_two_names_enters_once():
    sources = [_result(URL, f"{THESIS} {ROUTE}"), _result(OTHER, f"{THESIS} {ROUTE}")]
    again = _proposed(
        firm_name="Ash Grove Office LLC",
        source_url=OTHER,
        inbound_source_url=OTHER,
        evidence=[
            {"field": "thesis", "source_url": OTHER, "quote": THESIS},
            {"field": "inbound_kind", "source_url": OTHER, "quote": ROUTE},
            {"field": "inbound_value", "source_url": OTHER, "quote": ROUTE},
        ],
    )
    verified = verify_firms([_proposed(), again], sources, now=NOW)

    assert len(verified.firms) == 1
    assert verified.rejections["duplicate_firm"] == 1


def test_a_firm_already_in_the_bank_is_not_added_again():
    verified = verify_firms(
        [_proposed()], _sources(), now=NOW, known_domains={"ashgrove.example"}
    )

    assert verified.firms == []
    assert verified.rejections["duplicate_firm"] == 1


# ---------------------------------------------------------------------------
# The queries
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# The firm's own words — the rule the first live pass forced
# ---------------------------------------------------------------------------

def test_a_thesis_quoted_from_a_third_party_is_not_the_firms_thesis():
    """The defect a live pass found on the first try.

    The top results for the obvious queries were trade journalism and a
    competitor's listicle, and the model dutifully quoted a third party's
    *summary* of a firm as that firm's thesis. A paraphrase of a paraphrase
    cannot be quoted back to a founder as "here is what they say they fund",
    which is the whole mechanism this bank sells.
    """
    listicle = "https://competitor.example/blog/5-family-offices-in-health"
    summary = "Ash Grove pursues diverse opportunities across venture and growth."
    sources = [_result(listicle, summary)]
    proposed = _proposed(
        source_url=listicle,
        inbound_source_url=listicle,
        thesis=summary,
        evidence=[{"field": "thesis", "source_url": listicle, "quote": summary}],
    )
    verified = verify_firms([proposed], sources, now=NOW)

    assert verified.firms == []
    assert verified.rejections["thesis_not_from_firm_site"] == 1


def test_a_firm_whose_own_site_we_cannot_identify_is_not_a_record():
    verified = verify_firms([_proposed(domain=None)], _sources(), now=NOW)

    assert verified.firms == []
    assert verified.rejections["firm_site_unknown"] == 1


def test_a_subdomain_of_the_firms_site_is_the_firms_site():
    about = "https://about.ashgrove.example/investing"
    sources = [_result(about, f"{THESIS} {ROUTE}")]
    proposed = _proposed(
        source_url=about,
        inbound_source_url=about,
        evidence=[
            {"field": "thesis", "source_url": about, "quote": THESIS},
            {"field": "inbound_kind", "source_url": about, "quote": ROUTE},
            {"field": "inbound_value", "source_url": about, "quote": ROUTE},
        ],
    )
    assert len(verify_firms([proposed], sources, now=NOW).firms) == 1


def test_a_lookalike_host_is_not_the_firms_site():
    """`ashgrove.example.directory.com` is a directory, not Ash Grove. Matching
    by suffix rather than by label is how that gets through."""
    impostor = "https://ashgrove.example.directory.com/profile"
    sources = [_result(impostor, f"{THESIS} {ROUTE}")]
    proposed = _proposed(
        source_url=impostor,
        inbound_source_url=impostor,
        evidence=[{"field": "thesis", "source_url": impostor, "quote": THESIS}],
    )
    verified = verify_firms([proposed], sources, now=NOW)

    assert verified.firms == []
    assert verified.rejections["thesis_not_from_firm_site"] == 1


def test_queries_are_first_person_because_journalists_write_in_the_third():
    """The discriminator the live web forced. `"family office" "investment
    thesis" healthcare` returned eight think-pieces — CNBC, a trade magazine,
    a competitor's blog. A firm writes "we are a single family office"."""
    queries = curation_queries(["healthcare"])

    first_person = [q for q in queries if '"we ' in q or '"our ' in q]
    assert len(first_person) >= len(queries) // 2, (
        "most templates should be first-person; third-person phrasing returns "
        "journalism about the category rather than firms"
    )


def test_queries_look_for_published_positions_not_for_lists_of_names():
    """A name with no stated thesis cannot be matched against a founder's
    material, and matching is the product — so a query that would return a
    directory listing is the wrong query."""
    queries = curation_queries(["healthcare"])

    assert queries, "no queries produced"
    assert all("healthcare" in q for q in queries)
    assert any("thesis" in q or "we invest in" in q for q in queries)


def test_queries_are_deduped_and_sector_scoped():
    both = curation_queries(["fintech", "fintech"])
    one = curation_queries(["fintech"])

    assert both == one, "the same sector twice produced duplicate queries"


def test_an_empty_sector_list_falls_back_rather_than_producing_nothing():
    assert curation_queries([]) == curation_queries(None)
