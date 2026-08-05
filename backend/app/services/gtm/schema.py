# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# DiscoveryQuery, SearchResult, EvidenceItem
# ProposedCandidate, ProposedContact   — unverified model output
# Candidate, Contact                   — verified, storable
# EVIDENCED_FIELDS, QUERY_ANGLES, QueryAngle
# ─────────────────────────────────────────────────────────
"""The shapes go-to-market discovery moves between its four stages.

Two of these types exist only because the boundary between "what a model said"
and "what a source supports" has to be a type boundary and not a convention.
`ProposedCandidate` is what the extraction model emits; `Candidate` is what
survived verification against the URLs the search provider actually returned.
Nothing writes a `Candidate` except `extraction.verify_candidates`, so a field
that reaches storage has been through the check by construction rather than by
somebody remembering to call it.

**Every field on a candidate is optional except the ones that make it
actionable.** A company whose size is not evidenced in a retrieved source
carries `employee_count_range=None`, not a plausible band. This is the same rule
Phase 1 spent itself installing one level up: a report may not write its own
numbers, and a prospect list may not write its own firmographics. A founder who
finds one invented headcount has no reason to believe any of the others.

**Provenance is not metadata here, it is the record.** `source_url` and
`retrieved_at` are non-optional on every candidate and every contact, because a
subject-access or deletion request is answerable only if Saibyl can say where a
personal record came from and when it was retrieved. See `privacy.py`.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# The three angles one archetype yields. Not a free-form list: each is a
# different way of finding the same buyer, and a fourth would need its own
# argument about what it finds that these three miss.
#
#   firmographic     — who they are (category, role, seniority)
#   incumbent_tooling— what they already run, which is the field a B2B buyer
#                      actually evaluates against (icp_schema: "the single most
#                      load-bearing field in the profile")
#   pain_trigger     — what they complain about in public
QUERY_ANGLES: tuple[str, ...] = ("firmographic", "incumbent_tooling", "pain_trigger")

QueryAngle = Literal["firmographic", "incumbent_tooling", "pain_trigger"]

# Candidate fields that may only be populated from a quote in a retrieved
# source. `company_name`, `source_url` and `retrieved_at` are not here because
# they are the record's identity and provenance rather than claims about it.
EVIDENCED_FIELDS: frozenset[str] = frozenset({
    "one_liner",
    "domain",
    "employee_count_range",
    "industry",
    "hq_location",
    "incumbent_tooling",
})

# Patterns that mark a string as personal contact detail rather than public
# professional information. A contact record matching any of these is dropped
# whole — see `privacy.py` for why this is a hard rule and not a filter to be
# relaxed when the output looks thin.
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
_CONTACT_DETAIL_PATTERNS = (_EMAIL, _PHONE)


def contains_personal_contact_detail(text: str) -> bool:
    """True when `text` carries something that is not public professional info.

    Deliberately over-broad: a false positive costs one dropped contact, and a
    false negative puts a personal email address in Saibyl's database.
    """
    return any(pattern.search(text) for pattern in _CONTACT_DETAIL_PATTERNS)


class DiscoveryQuery(BaseModel):
    """One search a compiled ICP asks for."""

    archetype_id: str
    archetype_label: str
    angle: QueryAngle
    query: str
    # Which archetype fields produced this query. A query that returns nothing
    # useful is then traceable to the ICP field the founder should correct,
    # rather than to "the search". Synthesis proposes, the founder disposes
    # (DECISIONS §3) applies to the queries too.
    derived_from: list[str] = Field(default_factory=list)

    # Companies negated out of `query` as search operators, in the order they
    # appear in it. Empty is a real and common state — the incumbent angle
    # cannot negate the vendor it is asking about (`companies using Datadog
    # -Datadog` finds nothing), so those are caught by the post-filter in
    # `extraction.verify_candidates` instead. Read the full set off
    # `CategoryExclusions`, which is what is actually enforced; this field says
    # only what made it into this one query's text.
    #
    # Defaults empty so discovery runs stored before exclusions existed still
    # load: `store.create_run` persists these rows as JSON.
    excluded_terms: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    """One retrieved source, from whichever provider the adapter wraps.

    `snippet` is provider-supplied text about the page. Providers that return a
    text extract (Brave, Serper, Exa) put it here directly. The Anthropic
    server-side web search tool returns encrypted page content that only the
    model in that turn can read, so its adapter has the model write a factual
    digest per URL and puts that here — which is why every downstream quote is
    checked against this string rather than trusted.

    An empty `snippet` is a real state, not a placeholder: it means the provider
    gave no text for this URL, and therefore that no field can be evidenced from
    it. Extraction treats it that way rather than falling back to the title.
    """

    provider: str
    query: str
    url: str
    title: str = ""
    snippet: str = ""
    page_age: str | None = None
    retrieved_at: datetime


class EvidenceItem(BaseModel):
    """One field, the source it came from, and the text that supports it."""

    field: str
    source_url: str
    # Must appear verbatim in that source's snippet. Checked in
    # `extraction.verify_candidates`; an item that fails is dropped and the
    # field it supported reverts to None.
    quote: str


class ProposedContact(BaseModel):
    """A named person the extraction model proposed. Unverified."""

    full_name: str
    role_title: str = ""
    employer: str = ""
    # A public professional profile page. Never a personal contact channel.
    public_profile_url: str | None = None
    source_url: str
    quote: str = ""


class Contact(BaseModel):
    """A named person, verified against a retrieved source.

    Only public professional information: name, role, employer, public profile
    URL. No personal email, no phone number, no address, no inferred or
    sensitive attribute. `source_url` and `retrieved_at` are what make a
    deletion or access request answerable.
    """

    full_name: str
    role_title: str = ""
    employer: str = ""
    public_profile_url: str | None = None
    source_url: str
    retrieved_at: datetime


class ProposedCandidate(BaseModel):
    """A company the extraction model proposed. Unverified.

    Every claim field defaults to empty rather than being required, so a model
    that knows only the name produces a thin candidate instead of a padded one.
    """

    company_name: str
    domain: str | None = None
    one_liner: str = ""
    employee_count_range: str | None = None
    industry: str | None = None
    hq_location: str | None = None
    incumbent_tooling: list[str] = Field(default_factory=list)

    # Why this company matches the archetype, in the model's words. Rendered to
    # the founder next to the source, so it is a claim they can check.
    match_reasons: list[str] = Field(default_factory=list)

    source_url: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    contacts: list[ProposedContact] = Field(default_factory=list)


class Candidate(BaseModel):
    """A company that survived verification, ranked against one archetype.

    `archetype_id` and `source_url` are required and are the point of the type.
    A candidate a founder cannot trace back to the archetype that found it and
    the page that evidenced it is a lead they cannot act on, so there is no
    valid state of this object in which either is absent.
    """

    company_name: str
    domain: str | None = None
    one_liner: str = ""
    employee_count_range: str | None = None
    industry: str | None = None
    hq_location: str | None = None
    incumbent_tooling: list[str] = Field(default_factory=list)

    # Which archetype matched, and why.
    archetype_id: str
    archetype_label: str
    angle: QueryAngle
    query: str
    match_reasons: list[str] = Field(default_factory=list)

    # Where the evidence came from, and when it was retrieved.
    source_url: str
    source_title: str = ""
    retrieved_at: datetime
    evidence: list[EvidenceItem] = Field(default_factory=list)

    # 0..1 rank ordering against this archetype. Not a probability and not a
    # fit score in any calibrated sense — see `scoring.py`.
    match_score: float = 0.0
    score_components: dict[str, float] = Field(default_factory=dict)

    contacts: list[Contact] = Field(default_factory=list)

    @property
    def evidenced_fields(self) -> set[str]:
        return {item.field for item in self.evidence}
