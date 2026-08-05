# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# compile_queries(profile, *, max_queries=MAX_QUERIES_PER_DISCOVERY) -> list[DiscoveryQuery]
# MAX_QUERIES_PER_DISCOVERY, MAX_INCUMBENTS_IN_QUERY, MAX_PAIN_CHARS
# ─────────────────────────────────────────────────────────
"""Turn a synthesized ICP into the searches that find real companies.

The ICP already encodes what a search needs. `icp_schema` says of
`incumbent_tooling` that it is "the single most load-bearing field in the
profile: a B2B buyer evaluates net of what they would have to rip out" — which
is also the most specific thing you can search the open web for. "Companies
using Datadog" is a query; "companies that would like better observability" is
not. So the three angles are read straight off the archetype rather than
invented:

    firmographic       category + role + seniority          — who they are
    incumbent_tooling  incumbent_tooling + category         — what they run now
    pain_trigger       pains / skepticism_triggers + role   — what they say

**This module is deterministic and takes no model call.** Given a profile it
returns the same queries, in the same order, every time. That is not tidiness:
the queries are the one part of discovery a founder can read and argue with
before spending credits, and a query set that varies run to run cannot be
argued with. It also means the compiler is testable by assertion rather than by
eyeball, which is how `tests/test_gtm_discovery.py` pins the angles and
`tests/test_gtm_exclusions.py` pins what they leave out.

**Adversarial archetypes produce no queries.** The incumbent-aligned cohort
exists so a simulation contains the objection a pure-buyer swarm misses
(DECISIONS §7). It is not an audience to sell to, and compiling prospect
searches for "sunk-cost consultants who defend Datadog" would hand the founder
a list of people whose entire position is that they are not buying.

**An angle with no source field is skipped, not padded.** An archetype whose
`incumbent_tooling` is empty yields two queries, not three with a vague one
standing in. The founder's ICP has a gap there and `ICPProfile.gaps` is where
that is already surfaced; a generic query would spend credits pretending it
isn't.

**Every query excludes the founder's own category.** The three angles above are
good at finding the vendor as well as the buyer — `companies using Datadog
"observability tooling"` describes Datadog's homepage more exactly than it
describes any of Datadog's customers — and until this was applied, a founder
searching for buyers was handed their own competitors. The set comes from
`exclusions.build_exclusions`, which derives it from the profile's own
`competitors[]` and `incumbent_tooling` rather than from a list of vendor names
somebody typed; read that module for why those two fields and not others.

It is applied **here**, once, to whatever each builder returned, rather than
inside the three builders. A fourth angle would otherwise ship without it and
nothing would fail — which is precisely how the defect this fixes reached a
live user. `excluded_terms` on the returned query records what was negated, so
the estimate preview can show the founder what is being kept out before they
pay for the search.
"""
from __future__ import annotations

import structlog

from app.services.engine.personas.icp_schema import ICPArchetype, ICPProfile
from app.services.gtm.exclusions import CategoryExclusions, build_exclusions
from app.services.gtm.schema import QUERY_ANGLES, DiscoveryQuery

log = structlog.get_logger()

# Hard ceiling on one discovery's searches. Each query is two model calls plus
# a per-search charge, so this is the cost bound the credit gate quotes against
# — it is not a display limit. Raising it raises the price of every discovery.
MAX_QUERIES_PER_DISCOVERY = 12

# Incumbent tools in one OR-clause. Past three the query matches pages that
# list tools (comparison articles, awesome-lists) rather than pages about
# companies that use them.
MAX_INCUMBENTS_IN_QUERY = 3

# A pain or skepticism trigger is a sentence in the founder's ICP; a search
# query is a phrase. Truncated at a word boundary so the quoted term stays a
# real phrase rather than ending mid-word.
MAX_PAIN_CHARS = 90

_SENIORITY_TERM: dict[str, str] = {
    # Individual contributors are not usefully narrowed by the word "ic", and
    # no job posting or directory uses it. Empty means the term is omitted.
    "ic": "",
    "manager": "manager",
    "director": "director",
    "vp": "VP",
    "c_level": "executive",
    "founder": "founder",
}


def _quote(term: str) -> str:
    """Quote a multi-word term so the provider treats it as a phrase."""
    term = " ".join(term.split())
    if not term:
        return ""
    return f'"{term}"' if " " in term else term


def _join(terms: list[str]) -> str:
    return " ".join(t for t in terms if t)


def _truncate_phrase(text: str, limit: int) -> str:
    """Cut at the last word boundary at or before `limit`."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    boundary = cut.rfind(" ")
    return cut[:boundary] if boundary > 0 else cut


def _firmographic(archetype: ICPArchetype, category: str) -> DiscoveryQuery | None:
    if not archetype.role.strip():
        return None
    seniority = _SENIORITY_TERM.get(archetype.seniority, "")
    query = _join([
        _quote(category),
        _quote(archetype.role),
        seniority,
        "companies",
    ])
    derived = ["role"]
    if category.strip():
        derived.insert(0, "category")
    if seniority:
        derived.append("seniority")
    return DiscoveryQuery(
        archetype_id=archetype.id,
        archetype_label=archetype.label,
        angle="firmographic",
        query=query,
        derived_from=derived,
    )


def _incumbent(archetype: ICPArchetype, category: str) -> DiscoveryQuery | None:
    tools = [t for t in archetype.incumbent_tooling if t.strip()][:MAX_INCUMBENTS_IN_QUERY]
    if not tools:
        return None
    clause = " OR ".join(_quote(t) for t in tools)
    query = _join(["companies using", clause, _quote(category)])
    derived = ["incumbent_tooling"]
    if category.strip():
        derived.append("category")
    return DiscoveryQuery(
        archetype_id=archetype.id,
        archetype_label=archetype.label,
        angle="incumbent_tooling",
        query=query,
        derived_from=derived,
    )


def _pain(archetype: ICPArchetype, category: str) -> DiscoveryQuery | None:
    """Search on what this archetype complains about, in their own words.

    Pains first, skepticism triggers second. A pain is what they say when they
    are looking for a fix; a skepticism trigger is what they say when someone
    offers one. Both find the same people, but the first finds them earlier.
    """
    source_field = "pains"
    phrases = [p for p in archetype.pains if p.strip()]
    if not phrases:
        source_field = "skepticism_triggers"
        phrases = [p for p in archetype.skepticism_triggers if p.strip()]
    if not phrases:
        return None

    phrase = _truncate_phrase(phrases[0], MAX_PAIN_CHARS)
    query = _join([_quote(phrase), _quote(archetype.role), _quote(category)])
    derived = [source_field]
    if archetype.role.strip():
        derived.append("role")
    if category.strip():
        derived.append("category")
    return DiscoveryQuery(
        archetype_id=archetype.id,
        archetype_label=archetype.label,
        angle="pain_trigger",
        query=query,
        derived_from=derived,
    )


_BUILDERS = {
    "firmographic": _firmographic,
    "incumbent_tooling": _incumbent,
    "pain_trigger": _pain,
}


def _apply_exclusions(
    candidate: DiscoveryQuery,
    exclusions: CategoryExclusions,
) -> DiscoveryQuery:
    """Negate the founder's own category out of one compiled query.

    Mutates nothing: returns the query with the negatives appended to `query`
    and recorded on `excluded_terms`. A name the query already asks for
    positively is not negated — `negative_terms_for` decides that, and the
    post-filter in `extraction.verify_candidates` catches what it has to leave
    in.
    """
    terms = exclusions.negative_terms_for(candidate.query)
    if not terms:
        return candidate
    negatives = " ".join(f"-{_quote(term)}" for term in terms)
    return candidate.model_copy(update={
        "query": f"{candidate.query} {negatives}",
        "excluded_terms": terms,
    })


def compile_queries(
    profile: ICPProfile,
    *,
    max_queries: int = MAX_QUERIES_PER_DISCOVERY,
) -> list[DiscoveryQuery]:
    """Compile one ICP into an ordered, deduplicated set of searches.

    Ordering is angle-major, then the founder's own archetype order: every
    archetype gets its firmographic query before any archetype gets its second.
    A four-archetype profile capped at 12 therefore covers all four on all three
    angles rather than exhausting the first two.

    Archetype `weight` deliberately does not reorder this. Weight is the share
    of the *simulated swarm*, which is a statement about how the market is
    composed, not about which segment is worth prospecting first — and a founder
    who reordered their archetypes expects that order to mean something.
    """
    if max_queries <= 0:
        return []

    exclusions = build_exclusions(profile)
    queries: list[DiscoveryQuery] = []
    seen: set[str] = set()
    skipped: list[str] = []

    for angle in QUERY_ANGLES:
        build = _BUILDERS[angle]
        for archetype in profile.archetypes:
            candidate = build(archetype, profile.category)
            if candidate is None:
                skipped.append(f"{archetype.id}:{angle}")
                continue
            key = candidate.query.casefold()
            if key in seen:
                # Two archetypes that differ only in seniority can compile to
                # the same incumbent query. Dropping the duplicate is free;
                # paying for it twice is not. Keyed on the query before its
                # negatives, which are a deterministic function of it.
                skipped.append(f"{archetype.id}:{angle}:duplicate")
                continue
            seen.add(key)
            queries.append(_apply_exclusions(candidate, exclusions))

    truncated = len(queries) - max_queries
    if truncated > 0:
        queries = queries[:max_queries]

    log.info(
        "gtm_queries_compiled",
        profile=profile.name,
        archetypes=len(profile.archetypes),
        compiled=len(queries),
        # Both of these are ordinary outcomes, and both change what the founder
        # gets. Logged so a discovery that covered less of the ICP than the
        # founder assumed is visible rather than inferred from a short list.
        skipped_angles=skipped,
        truncated_at_cap=max(0, truncated),
        # How many of the compiled queries carry a negative term. A profile with
        # competitors whose queries all show zero here means the exclusion set
        # was built and then negated nothing — a different fact from a profile
        # that had nothing to exclude, and the two must not read the same.
        excluded_available=len(exclusions.companies),
        queries_with_exclusions=sum(1 for q in queries if q.excluded_terms),
    )
    return queries
