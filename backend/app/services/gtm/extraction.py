# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# extract_candidates(results, archetype, profile, *, query, angle,
#                    include_contacts=False, client=None, model=None)
#                                                    -> list[Candidate]
# verify_candidates(proposed, results, archetype, *, query, angle,
#                   include_contacts=False, exclusions=None) -> list[Candidate]
# normalise(text) -> str
# ─────────────────────────────────────────────────────────
"""Turn retrieved sources into candidates, and refuse to invent anything.

This module has two halves and the split is the point. `extract_candidates`
makes the model call. `verify_candidates` is pure, takes no network, and decides
what survives — so the rule that a field must be evidenced is testable by
assertion rather than by watching a live run.

**The rule.** A candidate reaches storage only if:

  * its `source_url` is one the search provider actually returned, and
  * at least one evidence item survives.

A *field* on that candidate is populated only if an evidence item names it,
cites a returned URL, and quotes text that appears verbatim in that URL's
snippet. Everything else is `None` — not a band, not a guess, not "unknown
(estimated)".

**Why this exact shape.** The model can write any string it likes into
`employee_count_range`. It cannot write a `quote` that appears in a snippet it
did not also write, about a URL a search did not return, without the check
catching it. That is not proof the page says what the snippet says — a
provider that returns real text extracts would make it proof, and this
interface takes those unchanged — but it does close the gap that matters,
which is the model filling a field from memory because the field existed.

Phase 1 spent itself on the same defect one level up: a report may not write its
own numbers. A fabricated firmographic is that defect wearing a prospect list.
The founder's entire reason to act on this list is that the numbers in it came
from somewhere, and one invented headcount discovered by hand costs the
credibility of every other row.

**A competitor is not a buyer, and this is where that is enforced.** The
compiler negates the founder's own category out of the query text, but a
negative term is an instruction to a search provider rather than a control, and
the incumbent angle cannot negate the vendor it is asking about at all —
`companies using Datadog -Datadog` returns nothing. So `verify_candidates`
drops a candidate that matches `CategoryExclusions`, on name or on domain
stem, and that drop is the enforced half of the pair. See `exclusions.py`.

**Nothing is silently dropped.** Every rejection — unreturned URL, unsupported
quote, contact carrying a personal email, a company that sells what the founder
sells — is counted and logged with its reason. A discovery that found twenty
companies and stored four is a fact about the sources, and it has to be visible
as one rather than read as a thin market.
"""
from __future__ import annotations

import re
from typing import Any

import structlog
from anthropic import APIStatusError, AsyncAnthropic
from pydantic import ValidationError

from app.core.config import settings
from app.services.billing.usage_ledger import record_llm_call
from app.services.engine.personas.icp_schema import ICPArchetype, ICPProfile
from app.services.gtm.exclusions import CategoryExclusions, build_exclusions
from app.services.gtm.privacy import CONTACT_BLOCKED_DOMAINS, rejects_as_personal_data
from app.services.gtm.schema import (
    EVIDENCED_FIELDS,
    Candidate,
    Contact,
    EvidenceItem,
    ProposedCandidate,
    QueryAngle,
    SearchResult,
)

log = structlog.get_logger()

# Candidates one query may yield. Bounds the extraction turn's output and, with
# MAX_SOURCES_PER_QUERY, the whole per-query cost.
MAX_CANDIDATES_PER_QUERY = 8

# Sized for MAX_CANDIDATES_PER_QUERY tool calls with their evidence. Also the
# reason no `thinking` parameter is set: where thinking is on by default it
# shares this budget (HANDOFF §8 item 9), so the budget covers both.
_EXTRACTION_MAX_TOKENS = 6_000

_WHITESPACE = re.compile(r"\s+")

# The shortest quote that can support a field. A three-character quote is a
# substring of almost any snippet, which would make the check pass on nothing.
_MIN_QUOTE_CHARS = 12


def normalise(text: str) -> str:
    """Casefold and collapse whitespace, for substring comparison."""
    return _WHITESPACE.sub(" ", (text or "")).strip().casefold()


_CANDIDATE_TOOL: dict[str, Any] = {
    "name": "record_candidate",
    "description": (
        "Record one real company found in the provided sources that matches "
        "the buyer archetype. Leave any field null unless one of the sources "
        "states it."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "company_name": {"type": "string"},
            "source_url": {
                "type": "string",
                "description": "The source URL this company was found in. Must be one of the provided URLs.",
            },
            "one_liner": {
                "type": ["string", "null"],
                "description": "What the company does, in the source's own terms. Null if no source says.",
            },
            "domain": {"type": ["string", "null"]},
            "employee_count_range": {
                "type": ["string", "null"],
                "description": "Only if a source states a headcount or band. Never estimated.",
            },
            "industry": {"type": ["string", "null"]},
            "hq_location": {"type": ["string", "null"]},
            "incumbent_tooling": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tools a source states this company uses. Empty if none is stated.",
            },
            "match_reasons": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Why this company matches the archetype, referring to the sources.",
            },
            "evidence": {
                "type": "array",
                "description": (
                    "One entry per field you populated other than company_name "
                    "and source_url. The quote must appear word-for-word in "
                    "that source's summary."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {
                            "type": "string",
                            "enum": sorted(EVIDENCED_FIELDS),
                        },
                        "source_url": {"type": "string"},
                        "quote": {"type": "string"},
                    },
                    "required": ["field", "source_url", "quote"],
                    "additionalProperties": False,
                },
            },
            "contacts": {
                "type": "array",
                "description": (
                    "Named people, ONLY when the request asks for them. Public "
                    "professional information only: name, role, employer, "
                    "public profile URL. Never an email address, phone number "
                    "or address."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "full_name": {"type": "string"},
                        "role_title": {"type": "string"},
                        "employer": {"type": "string"},
                        "public_profile_url": {"type": ["string", "null"]},
                        "source_url": {"type": "string"},
                        "quote": {"type": "string"},
                    },
                    "required": [
                        "full_name", "role_title", "employer",
                        "public_profile_url", "source_url", "quote",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": [
            "company_name", "source_url", "one_liner", "domain",
            "employee_count_range", "industry", "hq_location",
            "incumbent_tooling", "match_reasons", "evidence", "contacts",
        ],
        "additionalProperties": False,
    },
}

_SYSTEM = (
    "You identify real companies in retrieved web sources and match them to a "
    "buyer archetype.\n\n"
    "Rules, in order of importance:\n"
    "1. Every company you record must appear in the sources provided. Never "
    "record a company you know of but cannot point to in a source.\n"
    "2. Every field other than the company name must be supported by a quote "
    "that appears word-for-word in one of the source summaries. If no source "
    "states a company's size, its size is null. A null field is correct; an "
    "estimated one is a defect.\n"
    "3. Record fewer companies rather than padding the list. Zero is a valid "
    "answer.\n"
    "4. Record no named people unless the request explicitly asks for "
    "contacts, and then only public professional information."
)


def _archetype_brief(archetype: ICPArchetype, profile: ICPProfile) -> str:
    """What the model needs about the archetype, from the ICP's own fields."""
    lines = [
        f"Product category: {profile.category or '(not stated in the ICP)'}",
        f"Product: {profile.product_summary or '(not stated in the ICP)'}",
        "",
        f"Buyer archetype: {archetype.label}",
        f"  role: {archetype.role}",
        f"  seniority: {archetype.seniority}",
        f"  budget authority: {archetype.budget_authority}",
        f"  switching cost: {archetype.switching_cost}",
    ]
    if archetype.incumbent_tooling:
        lines.append(f"  tools they already run: {', '.join(archetype.incumbent_tooling)}")
    if archetype.evaluation_criteria:
        lines.append(f"  evaluates on: {'; '.join(archetype.evaluation_criteria)}")
    if archetype.pains:
        lines.append(f"  pains: {'; '.join(archetype.pains)}")
    if archetype.goals:
        lines.append(f"  goals: {'; '.join(archetype.goals)}")
    return "\n".join(lines)


def _sources_block(results: list[SearchResult]) -> str:
    parts = []
    for index, result in enumerate(results, start=1):
        parts.append(
            f"[{index}] url: {result.url}\n"
            f"    title: {result.title}\n"
            f"    summary: {result.snippet or '(the provider returned no text for this page)'}"
        )
    return "\n\n".join(parts)


async def extract_candidates(
    results: list[SearchResult],
    archetype: ICPArchetype,
    profile: ICPProfile,
    *,
    query: str,
    angle: QueryAngle,
    include_contacts: bool = False,
    client: AsyncAnthropic | None = None,
    model: str | None = None,
) -> list[Candidate]:
    """Extract and verify candidates from one query's sources.

    Runs on the main model: deciding whether a company matches an archetype,
    and whether a claim is actually stated, is the judgment half of DECISIONS
    §14. The input is the digests rather than the pages, so this turn is a
    fraction of the search turn's size.
    """
    usable = [r for r in results if r.snippet.strip()]
    if not usable:
        log.info("gtm_extraction_skipped", query=query, reason="no_source_text")
        return []

    client = client or AsyncAnthropic(api_key=settings.anthropic_api_key)
    resolved = model or settings.llm_model

    contact_instruction = (
        "This organization has enabled contact discovery. You may record named "
        "people, but only public professional information (name, role, "
        "employer, public profile URL) and only when a source names them in a "
        "professional context."
        if include_contacts
        else "Do NOT record any named people. Leave `contacts` empty on every candidate."
    )

    prompt = (
        f"{_archetype_brief(archetype, profile)}\n\n"
        f"Search that produced these sources: {query}\n\n"
        f"Sources:\n\n{_sources_block(usable)}\n\n"
        f"{contact_instruction}\n\n"
        f"Call record_candidate once per matching company, at most "
        f"{MAX_CANDIDATES_PER_QUERY} times. Record none if none of these "
        f"sources names a company that matches the archetype."
    )

    try:
        response = await client.messages.create(
            model=resolved,
            max_tokens=_EXTRACTION_MAX_TOKENS,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            tools=[_CANDIDATE_TOOL],
        )
    except APIStatusError:
        # Not swallowed: the caller marks the query failed and the discovery
        # partial. A query that errored and a query that found nothing are
        # different facts and must not share an empty list at the run level.
        log.exception("gtm_extraction_call_failed", query=query, model=resolved)
        raise

    _record_usage(response, resolved)

    proposed: list[ProposedCandidate] = []
    malformed = 0
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) != "tool_use":
            continue
        if getattr(block, "name", None) != "record_candidate":
            continue
        try:
            proposed.append(ProposedCandidate.model_validate(block.input or {}))
        except ValidationError as exc:
            malformed += 1
            log.warning("gtm_candidate_malformed", query=query, errors=exc.errors()[:3])

    if malformed:
        log.warning("gtm_candidates_malformed_total", query=query, dropped=malformed)

    return verify_candidates(
        proposed[:MAX_CANDIDATES_PER_QUERY],
        usable,
        archetype,
        query=query,
        angle=angle,
        include_contacts=include_contacts,
        # Built from the same profile the compiler built it from, and by the
        # same pure function, so what the estimate promised to keep out is
        # exactly what is kept out here.
        exclusions=build_exclusions(profile),
    )


def _record_usage(response: Any, model: str) -> None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    try:
        record_llm_call(
            model=model,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        )
    except Exception:
        log.exception("gtm_extraction_usage_hook_failed", model=model)


# ---------------------------------------------------------------------------
# Verification — pure, no network, the part the tests pin
# ---------------------------------------------------------------------------

def _blocked_profile_url(url: str | None) -> bool:
    if not url:
        return False
    lowered = url.casefold()
    return any(f"//{d}/" in lowered or lowered.endswith(f"//{d}") or f".{d}/" in lowered
               for d in CONTACT_BLOCKED_DOMAINS)


def _verify_contacts(
    proposed: ProposedCandidate,
    by_url: dict[str, SearchResult],
    snippets: dict[str, str],
    rejections: dict[str, int],
) -> list[Contact]:
    contacts: list[Contact] = []
    for raw in proposed.contacts:
        snippet = snippets.get(raw.source_url)
        source = by_url.get(raw.source_url)
        if snippet is None or source is None:
            rejections["contact_unreturned_url"] += 1
            continue
        quote = normalise(raw.quote)
        if len(quote) < _MIN_QUOTE_CHARS or quote not in snippet:
            rejections["contact_unsupported_quote"] += 1
            continue
        if _blocked_profile_url(raw.public_profile_url):
            rejections["contact_blocked_profile_domain"] += 1
            continue

        payload = {
            "full_name": raw.full_name,
            "role_title": raw.role_title,
            "employer": raw.employer,
            "public_profile_url": raw.public_profile_url,
            "source_url": raw.source_url,
        }
        reason = rejects_as_personal_data(payload)
        if reason is not None:
            rejections["contact_personal_data"] += 1
            log.warning("gtm_contact_rejected", reason=reason, source_url=raw.source_url)
            continue
        if not raw.full_name.strip():
            rejections["contact_no_name"] += 1
            continue

        contacts.append(Contact(
            full_name=raw.full_name.strip(),
            role_title=raw.role_title.strip(),
            employer=raw.employer.strip(),
            public_profile_url=raw.public_profile_url,
            source_url=raw.source_url,
            # From the contact's own source, not the candidate's. A person and
            # the company they work for are often evidenced by different pages,
            # and an erasure request is answered against the page that named
            # the person.
            retrieved_at=source.retrieved_at,
        ))
    return contacts


def verify_candidates(
    proposed: list[ProposedCandidate],
    results: list[SearchResult],
    archetype: ICPArchetype,
    *,
    query: str,
    angle: QueryAngle,
    include_contacts: bool = False,
    exclusions: CategoryExclusions | None = None,
) -> list[Candidate]:
    """Keep what the sources support; blank what they do not.

    Pure. Given the same inputs it returns the same candidates, which is what
    makes "an unevidenced field is None rather than invented" a test rather
    than an intention.

    `exclusions` is the founder's own category — companies that sell what they
    sell, which the search returns because they match the query better than any
    buyer does. `None` means no set was supplied and nothing is excluded; that
    is reachable only from a direct call, since `extract_candidates` always
    builds one, and the outcome is recorded on `gtm_candidates_verified` so a
    run that filtered nothing cannot be mistaken for a run with nothing to
    filter.
    """
    by_url = {r.url: r for r in results}
    snippets = {r.url: normalise(r.snippet) for r in results}

    kept: list[Candidate] = []
    excluded_names: list[str] = []
    rejections: dict[str, int] = {
        "unreturned_source_url": 0,
        "sells_what_the_founder_sells": 0,
        "no_surviving_evidence": 0,
        "unknown_evidence_field": 0,
        "evidence_unreturned_url": 0,
        "evidence_unsupported_quote": 0,
        "no_company_name": 0,
        "contact_unreturned_url": 0,
        "contact_unsupported_quote": 0,
        "contact_blocked_profile_domain": 0,
        "contact_personal_data": 0,
        "contact_no_name": 0,
        "contacts_dropped_gate_off": 0,
    }

    for raw in proposed:
        if not raw.company_name.strip():
            rejections["no_company_name"] += 1
            continue

        # Checked before anything else, and against `raw.domain` rather than
        # the verified one. An unevidenced domain may not populate a field on a
        # stored record — that is the rule this module exists for — but it is
        # sound grounds for *removing* a row, because the cost of being wrong
        # runs the safe way: one lead lost, versus a competitor presented to
        # the founder as somebody to sell to.
        if exclusions is not None:
            hit = exclusions.match(raw.company_name, raw.domain)
            if hit is not None:
                rejections["sells_what_the_founder_sells"] += 1
                excluded_names.append(f"{raw.company_name.strip()}~{hit.name}")
                continue

        source = by_url.get(raw.source_url)
        if source is None:
            # The company was attributed to a page the search never returned.
            rejections["unreturned_source_url"] += 1
            continue

        surviving: list[EvidenceItem] = []
        for item in raw.evidence:
            if item.field not in EVIDENCED_FIELDS:
                rejections["unknown_evidence_field"] += 1
                continue
            snippet = snippets.get(item.source_url)
            if snippet is None:
                rejections["evidence_unreturned_url"] += 1
                continue
            quote = normalise(item.quote)
            if len(quote) < _MIN_QUOTE_CHARS or quote not in snippet:
                rejections["evidence_unsupported_quote"] += 1
                continue
            surviving.append(item)

        if not surviving:
            # Nothing about this company traces to a source. A name with no
            # supported claim is not a lead, it is a word.
            rejections["no_surviving_evidence"] += 1
            continue

        evidenced = {item.field for item in surviving}
        contacts: list[Contact] = []
        if include_contacts:
            contacts = _verify_contacts(raw, by_url, snippets, rejections)
        elif raw.contacts:
            # The gate is off and the model returned people anyway. Dropped
            # here as well as prompted against, because a prompt is not a
            # control: this is the line that makes "off" mean nothing personal
            # is stored, whatever the model does.
            rejections["contacts_dropped_gate_off"] += len(raw.contacts)

        kept.append(Candidate(
            company_name=raw.company_name.strip(),
            domain=raw.domain if "domain" in evidenced else None,
            one_liner=(raw.one_liner or "") if "one_liner" in evidenced else "",
            employee_count_range=(
                raw.employee_count_range if "employee_count_range" in evidenced else None
            ),
            industry=raw.industry if "industry" in evidenced else None,
            hq_location=raw.hq_location if "hq_location" in evidenced else None,
            incumbent_tooling=(
                list(raw.incumbent_tooling) if "incumbent_tooling" in evidenced else []
            ),
            archetype_id=archetype.id,
            archetype_label=archetype.label,
            angle=angle,
            query=query,
            match_reasons=[m for m in raw.match_reasons if m.strip()],
            source_url=source.url,
            source_title=source.title,
            retrieved_at=source.retrieved_at,
            evidence=surviving,
            contacts=contacts,
        ))

    dropped = {reason: count for reason, count in rejections.items() if count}
    log.info(
        "gtm_candidates_verified",
        query=query,
        archetype_id=archetype.id,
        proposed=len(proposed),
        kept=len(kept),
        # Present even when empty in the caller's aggregate, so a run that
        # stored four of twenty is legible as a source problem rather than as
        # a thin market.
        dropped=dropped,
        # `candidate~matched_exclusion` per drop, so a wrong exclusion is
        # traceable to the profile field that produced it rather than showing
        # up as a company that quietly never appeared.
        excluded_as_competitor=excluded_names,
        # False here on a live run means the post-filter did not run at all,
        # which is a different fact from "it ran and matched nothing".
        exclusions_applied=exclusions is not None,
        exclusions_available=len(exclusions.companies) if exclusions else 0,
    )
    return kept
