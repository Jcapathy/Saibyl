# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# curation_queries(sectors=None, firm_types=None) -> list[str]
# propose_firms(results, *, query, now, client=None, model=None)
#                                              -> list[ProposedFirm]   [async]
# verify_firms(proposed, results, *, now, known_domains=None) -> Verified
# run_curation(*, adapter, queries=None, now=None, client=None) -> Curation
#                                                                      [async]
# ProposedFirm, Verified, Curation, CurationUnavailableError
# MIN_QUOTE_CHARS
# ─────────────────────────────────────────────────────────
"""Fill the family-office bank by searching and reading, never by crawling.

Route (b), as the founder chose it: we build the bank rather than license one.
`CAPITAL_MODULE.md` argues why — the matching is the moat, and it is cheaper to
prove with fifty well-evidenced firms than with five thousand thin ones. A
licensed feed would buy coverage and rent the part that is not the product.

**This is a curation job, not a customer job.** `family_offices` grants read to
any signed-in member and grants write to nobody, so only the service role can
fill it: a recommendation carries Saido Labs' name, which makes deciding what
enters an editorial act. Nothing here is charged, nothing here runs in a
founder's request, and no founder input reaches it. That is the opposite shape
from `gtm/discovery`, which is per-project, charged, and inline — and the
difference is deliberate rather than an omission.

**The two halves, and why they are split.** `propose_firms` makes the model
call. `verify_firms` is pure, takes no network, and decides what survives. So
"a field must be evidenced" is settled by assertion in a test rather than by
watching a live run — the same split `gtm/extraction` uses, for the same
reason.

**The rule.** A firm enters the bank only if its `source_url` is one the search
provider actually returned and its inbound route cites a returned URL too. A
*field* is populated only when an evidence item names it, cites a returned URL,
and quotes text appearing verbatim in that URL's snippet. Everything else is
left empty — not a plausible band, not "typically $1–5M". A founder who finds
one invented cheque range has no reason to believe any other field, and this
list goes out with our name on it.

**What this module does not do.** No crawling, no authenticated fetches, no
paywalled sources, no blocked domains. If a firm publishes nothing, it does not
go in the bank. `schema.FamilyOffice` then rejects anything carrying personal
data or missing its freshness window, so the last gate is a type rather than a
habit — this module cannot talk its way past it.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from anthropic import APIStatusError, AsyncAnthropic
from pydantic import BaseModel, Field, ValidationError

from app.core.config import settings
from app.services.billing.usage_ledger import record_llm_call
from app.services.capital.schema import (
    FamilyOffice,
    InboundPath,
    default_stale_after,
)
from app.services.gtm.extraction import normalise
from app.services.gtm.schema import SearchResult
from app.services.gtm.search_adapter import (
    SearchAdapter,
    SearchUnavailableError,
)

log = structlog.get_logger()

# The shortest quote that can support a field. Borrowed from `extraction`, and
# for its reason: a three-character quote appears in almost any snippet, so a
# short one is not evidence, it is a coincidence waiting to be counted as one.
MIN_QUOTE_CHARS = 24

_MODEL = "claude-sonnet-5"

# Generous on purpose. At 4,000 the first live pass spent the whole budget in
# extended thinking and stopped at `max_tokens` having emitted no tool call at
# all — which reads downstream exactly like "the web contains no family
# offices". A truncated turn must not be able to impersonate an empty web.
_MAX_TOKENS = 16_000
_MAX_SOURCES_PER_PROPOSAL = 12


class CurationUnavailableError(RuntimeError):
    """The search provider is unusable, so no query could have succeeded.

    Deliberately not the same state as "found nothing". A curation run that
    reports zero firms because the provider was down would, on the next run,
    look like a bank that legitimately has nothing to add.
    """


# ---------------------------------------------------------------------------
# What we ask the web
# ---------------------------------------------------------------------------

# Firms that publish a thesis are the only firms this bank can hold, so the
# queries look for published positions rather than for names. A list of family
# offices is easy to find and useless here: a name with no stated thesis cannot
# be matched against a founder's material, and matching is the product.
#
# **Every template is first-person on purpose**, and that is the whole design.
# The obvious phrasing — `"family office" "investment thesis" healthcare` —
# was tried against the live web first and returned eight think-pieces: CNBC,
# a trade magazine, a competitor's blog. Journalists write *about* family
# offices in the third person; a firm writes "we are a single family office".
# So the first person is the cheapest available discriminator between a page
# that describes the category and a page that IS a firm.
_QUERY_TEMPLATES = (
    '"we are a single family office" invest {sector}',
    '"our family office" "we invest in" {sector}',
    '"we are a family office" "investment criteria" {sector}',
    '"family office" "investment criteria" "submit" {sector} -news -magazine',
    '"private investment office" "we back" {sector} founders',
    '"family office" "our portfolio" "{sector}" "get in touch"',
)

_DEFAULT_SECTORS = (
    "healthcare",
    "fintech",
    "enterprise software",
    "cybersecurity",
    "climate",
    "consumer",
)


def curation_queries(
    sectors: list[str] | None = None,
    firm_types: list[str] | None = None,
) -> list[str]:
    """The search queries one curation pass will run.

    Sector-parameterised so the bank can be grown deliberately — a founder in
    clinical software is served by a bank with health firms in it, and the
    honest way to get there is to go looking for them rather than to hope a
    general sweep found some.
    """
    chosen = [s.strip() for s in (sectors or _DEFAULT_SECTORS) if s and s.strip()]
    queries = [
        template.format(sector=sector)
        for sector in chosen
        for template in _QUERY_TEMPLATES
    ]
    for firm_type in firm_types or []:
        label = firm_type.replace("_", " ")
        queries.append(f'"{label}" investment thesis direct investments')
    # Order-stable dedupe: two sectors can compose the same query text.
    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique.append(q)
    return unique


# ---------------------------------------------------------------------------
# What the model is allowed to say
# ---------------------------------------------------------------------------

_FIRM_TOOL: dict[str, Any] = {
    "name": "record_family_office",
    "description": (
        "Record one real family office, foundation, or multi-family office "
        "found in the provided sources. Leave any field null unless one of "
        "the sources states it. Do not record a firm that publishes no "
        "investment thesis."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "firm_name": {"type": "string"},
            "domain": {"type": ["string", "null"]},
            "firm_type": {
                "type": "string",
                "enum": ["single_family", "multi_family", "foundation"],
            },
            "thesis": {
                "type": "string",
                "description": (
                    "The firm's own published words about what it invests in, "
                    "quoted rather than paraphrased."
                ),
            },
            "sectors": {"type": "array", "items": {"type": "string"}},
            "stages": {"type": "array", "items": {"type": "string"}},
            "check_size_low": {"type": ["integer", "null"]},
            "check_size_high": {"type": ["integer", "null"]},
            "geography": {"type": "array", "items": {"type": "string"}},
            "notable_investments": {"type": "array", "items": {"type": "string"}},
            "inbound_kind": {
                "type": "string",
                "enum": [
                    "submission_form",
                    "firm_address",
                    "warm_intro_only",
                    "no_inbound",
                ],
                "description": (
                    "The firm's OWN published position on unsolicited "
                    "approaches. Use warm_intro_only or no_inbound when the "
                    "firm says so; those carry no value."
                ),
            },
            "inbound_value": {
                "type": ["string", "null"],
                "description": (
                    "The submission URL, or a role address the firm publishes "
                    "for submissions. Null for warm_intro_only and no_inbound."
                ),
            },
            "inbound_source_url": {"type": "string"},
            "source_url": {"type": "string"},
            "source_title": {"type": "string"},
            "evidence": {
                "type": "array",
                "description": (
                    "One entry per field you populated other than firm_name, "
                    "firm_type and source_url. The quote must appear "
                    "word-for-word in that URL's provided text."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string"},
                        "source_url": {"type": "string"},
                        "quote": {"type": "string"},
                    },
                    "required": ["field", "source_url", "quote"],
                    "additionalProperties": False,
                },
            },
        },
        "required": [
            "firm_name",
            "domain",
            "firm_type",
            "thesis",
            "sectors",
            "stages",
            "check_size_low",
            "check_size_high",
            "geography",
            "notable_investments",
            "inbound_kind",
            "inbound_value",
            "inbound_source_url",
            "source_url",
            "source_title",
            "evidence",
        ],
        "additionalProperties": False,
    },
}

_SYSTEM = (
    "You read search results about private investment firms and record only "
    "what those results actually say.\n"
    "1. Record a firm only if the sources include a page ON THAT FIRM'S OWN "
    "SITE stating what it invests in, and set `domain` to that site. A news "
    "article, a directory entry, or another company's blog post describing a "
    "firm is not that firm's published thesis, however accurate it may be — "
    "do not record a firm you have only read about second-hand. Quote the "
    "thesis from the firm's own page.\n"
    "2. Every field other than firm_name, firm_type and source_url must be "
    "supported by a quote that appears word-for-word in the provided text for "
    "the URL you cite. If no source states a firm's cheque size, its cheque "
    "size is null. A null field is correct; an invented one is not.\n"
    "3. Record the firm's own published position on inbound. Many family "
    "offices state that they take no unsolicited approaches — that is a real "
    "and useful answer, so record it as no_inbound or warm_intro_only rather "
    "than omitting the firm or guessing a route.\n"
    "4. Never record an individual person's email address or phone number, in "
    "any field. A firm's published submissions address is acceptable; a named "
    "person's address is not.\n"
    "5. If the sources contain no firm that meets these rules, record nothing."
)


# ---------------------------------------------------------------------------
# Stage one: names, from wherever names are
# ---------------------------------------------------------------------------

# The category queries return directories, trade journalism and competitors'
# listicles — measured, not assumed: the first live pass returned seven such
# pages and one genuine firm site. That is what ranks for these phrases, and no
# amount of query tuning changes it.
#
# So the pipeline stops fighting it and uses each kind of page for what it is
# actually good at. A listicle is a reliable source of *names* and an
# unacceptable source of *theses* — it paraphrases, and a paraphrase cannot be
# quoted back to a founder as "here is what they say they fund". Stage one
# harvests names from anything. Stage two goes to each firm's own site and
# builds the record there, or does not build one at all.
_NAME_TOOL: dict[str, Any] = {
    "name": "record_firm_name",
    "description": (
        "Record the name of one private investment firm, family office or "
        "foundation that these sources name as an active direct investor."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "firm_name": {"type": "string"},
            "why": {
                "type": "string",
                "description": "The phrase in the sources that names it as one.",
            },
        },
        "required": ["firm_name", "why"],
        "additionalProperties": False,
    },
}

_NAME_SYSTEM = (
    "You read pages about private investment and list the firms they name.\n"
    "Record only firms the sources present as family offices, private "
    "investment offices, or foundations making direct investments. Do not "
    "record banks, funds-of-funds, listed asset managers, or the publisher of "
    "the page. Do not invent names. One tool call per firm."
)

# Their own site says what they fund; a directory says what someone thinks they
# fund. These queries look for the former, by name.
_FIRM_SITE_TEMPLATES = (
    '{name} family office "investment criteria"',
    '{name} "what we invest in" OR "our approach" official site',
)

_MAX_NAMES_PER_QUERY = 8


class _Evidence(BaseModel):
    field: str
    source_url: str
    quote: str


class ProposedFirm(BaseModel):
    """What the model claimed, before anything has been checked."""

    firm_name: str
    domain: str | None = None
    firm_type: str
    thesis: str = ""
    sectors: list[str] = Field(default_factory=list)
    stages: list[str] = Field(default_factory=list)
    check_size_low: int | None = None
    check_size_high: int | None = None
    geography: list[str] = Field(default_factory=list)
    notable_investments: list[str] = Field(default_factory=list)
    inbound_kind: str
    inbound_value: str | None = None
    inbound_source_url: str = ""
    source_url: str
    source_title: str = ""
    evidence: list[_Evidence] = Field(default_factory=list)


@dataclass
class Verified:
    """What survived, and every reason something did not.

    Rejections are counted rather than logged and forgotten, because a
    curation pass that quietly discards nine of ten proposals is either a
    working gate or a broken prompt, and the counts are what tell them apart.
    """

    firms: list[FamilyOffice] = field(default_factory=list)
    rejections: Counter = field(default_factory=Counter)


@dataclass
class Curation:
    """One full pass: what was searched, what entered, what did not."""

    firms: list[FamilyOffice] = field(default_factory=list)
    rejections: Counter = field(default_factory=Counter)
    queries_run: int = 0
    queries_failed: int = 0
    sources_seen: int = 0
    # Stage one's yield. The gap between this and `len(firms)` is the honest
    # cost of the firm's-own-site rule, and it is worth being able to see:
    # many family offices publish no thesis anywhere, and those are firms we
    # decline to recommend rather than firms we failed to find.
    names_found: int = 0


# ---------------------------------------------------------------------------
# Half one: the model call
# ---------------------------------------------------------------------------

def _sources_block(results: list[SearchResult]) -> str:
    blocks = []
    for r in results[:_MAX_SOURCES_PER_PROPOSAL]:
        blocks.append(
            f"URL: {r.url}\nTITLE: {r.title}\nTEXT:\n{r.snippet}\n"
        )
    return "\n---\n".join(blocks)


async def propose_firms(
    results: list[SearchResult],
    *,
    query: str,
    now: datetime | None = None,
    client: Any | None = None,
    model: str = _MODEL,
) -> list[ProposedFirm]:
    """Ask the model which firms these sources describe. Checked afterwards."""
    usable = [r for r in results if (r.snippet or "").strip()]
    if not usable:
        # An empty snippet is a real state: the provider gave no text, so no
        # field could be evidenced from it and there is nothing to ask about.
        return []

    client = client or AsyncAnthropic(api_key=settings.anthropic_api_key)

    try:
        response = await client.messages.create(
            model=model,
            max_tokens=_MAX_TOKENS,
            system=_SYSTEM,
            tools=[_FIRM_TOOL],
            messages=[{
                "role": "user",
                "content": (
                    f"Search query that returned these sources: {query}\n\n"
                    f"{_sources_block(usable)}\n\n"
                    "Record every firm these sources show publishes an "
                    "investment thesis. Call the tool once per firm."
                ),
            }],
        )
    except APIStatusError:
        # Raised, not swallowed: the caller counts the query failed. A query
        # that errored and a query that found nothing are different facts.
        log.exception("capital_proposal_call_failed", query=query, model=model)
        raise

    _record_usage(response, model)

    # A turn that ran out of tokens mid-answer and a turn that found nothing
    # both arrive here as an empty list. They are different facts and the
    # difference is worth a log line: the first live pass of this module spent
    # its whole budget thinking and emitted no tool call, which read all the
    # way up the stack as "the web contains no family offices".
    stop_reason = getattr(response, "stop_reason", None)
    if stop_reason == "max_tokens":
        log.warning(
            "capital_proposal_truncated",
            query=query,
            model=model,
            max_tokens=_MAX_TOKENS,
        )

    proposed: list[ProposedFirm] = []
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) != "tool_use":
            continue
        if getattr(block, "name", None) != _FIRM_TOOL["name"]:
            continue
        raw = getattr(block, "input", None)
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                log.warning("capital_proposal_unparseable", query=query)
                continue
        if not isinstance(raw, dict):
            continue
        try:
            proposed.append(ProposedFirm.model_validate(raw))
        except ValidationError as exc:
            log.warning(
                "capital_proposal_malformed", query=query, errors=exc.errors()[:3]
            )

    log.info(
        "capital_proposals",
        query=query,
        sources=len(usable),
        proposed=len(proposed),
        stop_reason=stop_reason,
    )
    return proposed


async def harvest_names(
    results: list[SearchResult],
    *,
    query: str,
    client: Any | None = None,
    model: str = _MODEL,
) -> list[str]:
    """Firm names from any page that names firms. Nothing else is taken."""
    usable = [r for r in results if (r.snippet or "").strip()]
    if not usable:
        return []

    client = client or AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        response = await client.messages.create(
            model=model,
            max_tokens=_MAX_TOKENS,
            system=_NAME_SYSTEM,
            tools=[_NAME_TOOL],
            messages=[{
                "role": "user",
                "content": (
                    f"Query: {query}\n\n{_sources_block(usable)}\n\n"
                    "List every family office, private investment office or "
                    "foundation these sources name."
                ),
            }],
        )
    except APIStatusError:
        log.exception("capital_name_harvest_failed", query=query)
        raise

    _record_usage(response, model)

    names: list[str] = []
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) != "tool_use":
            continue
        if getattr(block, "name", None) != _NAME_TOOL["name"]:
            continue
        raw = getattr(block, "input", None) or {}
        name = str(raw.get("firm_name") or "").strip() if isinstance(raw, dict) else ""
        if name and name.lower() not in {n.lower() for n in names}:
            names.append(name)

    log.info(
        "capital_names_harvested",
        query=query,
        sources=len(usable),
        names=len(names),
        stop_reason=getattr(response, "stop_reason", None),
    )
    return names[:_MAX_NAMES_PER_QUERY]


def _record_usage(response: Any, model: str) -> None:
    """Curation is unbilled to founders but not free to us — it still lands
    in the cost ledger, or the margin on every other artifact is fiction."""
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
    except Exception:  # noqa: BLE001
        log.exception("capital_curation_usage_hook_failed", model=model)


# ---------------------------------------------------------------------------
# Half two: pure verification
# ---------------------------------------------------------------------------

_QUOTED_FIELDS = (
    "thesis",
    "sectors",
    "stages",
    "check_size_low",
    "check_size_high",
    "geography",
    "notable_investments",
    "inbound_kind",
    "inbound_value",
)

_DOMAIN = re.compile(r"^(?:https?://)?(?:www\.)?([^/:?#]+)", re.I)


def _domain_of(url: str) -> str:
    match = _DOMAIN.match((url or "").strip())
    return match.group(1).lower() if match else ""


def _same_site(url: str, domain: str) -> bool:
    """Is this URL on the firm's own site, or a subdomain of it?

    `about.ashgrove.example` is Ash Grove. `ashgrove.example.directory.com` is
    not, which is why this compares labels rather than asking whether one
    string ends with the other.
    """
    host = _domain_of(url)
    if not host or not domain:
        return False
    return host == domain or host.endswith("." + domain)


def _dedupe_key(firm: ProposedFirm) -> str:
    """Firms are the same firm when their domain is, or their name is.

    Domain first: the same office appears under 'Acme Capital' and 'Acme
    Capital LLC' across two directories, and a bank that lists it twice tells
    a founder to approach it twice.
    """
    domain = _domain_of(firm.domain or "") or _domain_of(firm.source_url)
    return domain or normalise(firm.firm_name)


def verify_firms(
    proposed: list[ProposedFirm],
    results: list[SearchResult],
    *,
    now: datetime | None = None,
    known_domains: set[str] | None = None,
) -> Verified:
    """Decide what enters the bank. Pure — no network, no clock beyond `now`."""
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    snippets = {r.url: normalise(r.snippet) for r in results}
    returned_urls = set(snippets)
    seen: set[str] = set(known_domains or set())

    out = Verified()

    for firm in proposed:
        if firm.source_url not in returned_urls:
            # The model can write any URL it likes. It cannot write one the
            # provider returned without the provider having returned it.
            out.rejections["source_url_not_returned"] += 1
            continue

        key = _dedupe_key(firm)
        if key in seen:
            out.rejections["duplicate_firm"] += 1
            continue

        # Which fields survived their evidence — collected before the record is
        # built, so an unsupported field is absent rather than corrected later.
        supported: set[str] = set()
        for item in firm.evidence:
            if item.field not in _QUOTED_FIELDS:
                out.rejections["unknown_evidence_field"] += 1
                continue
            snippet = snippets.get(item.source_url)
            if snippet is None:
                out.rejections["evidence_cites_unreturned_url"] += 1
                continue
            quote = normalise(item.quote)
            if len(quote) < MIN_QUOTE_CHARS or quote not in snippet:
                out.rejections["unsupported_quote"] += 1
                continue
            supported.add(item.field)

        if "thesis" not in supported or not firm.thesis.strip():
            # The thesis is the mechanism of the match. A firm whose thesis is
            # unevidenced is a name, and a name cannot be matched to anything.
            out.rejections["thesis_unevidenced"] += 1
            continue

        # The thesis must be the firm's OWN published words, from the firm's own
        # site. The first live pass proved why: the top results for the obvious
        # queries were trade journalism and a competitor's listicle, and the
        # model dutifully quoted a third party's *summary* of a firm as that
        # firm's thesis. A paraphrase of a paraphrase cannot be quoted back to
        # a founder as "here is what they say they fund", which is the entire
        # mechanism this bank sells.
        #
        # This costs coverage and keeps credibility, which is the trade
        # CAPITAL_MODULE.md already made: fifty well-evidenced firms beat five
        # thousand thin ones.
        firm_domain = _domain_of(firm.domain or "")
        if not firm_domain:
            out.rejections["firm_site_unknown"] += 1
            continue
        if not any(
            _same_site(item.source_url, firm_domain)
            for item in firm.evidence
            if item.field == "thesis" and item.source_url in returned_urls
        ):
            out.rejections["thesis_not_from_firm_site"] += 1
            continue

        inbound_kind = firm.inbound_kind
        inbound_value = firm.inbound_value
        if "inbound_kind" not in supported:
            # We will not guess a firm's posture toward strangers. Unstated
            # becomes the most conservative real answer the schema has.
            inbound_kind, inbound_value = "no_inbound", None
            out.rejections["inbound_unevidenced_defaulted"] += 1
        elif inbound_kind in ("warm_intro_only", "no_inbound"):
            inbound_value = None
        elif "inbound_value" not in supported:
            inbound_kind, inbound_value = "no_inbound", None
            out.rejections["inbound_route_unevidenced"] += 1

        inbound_source = (
            firm.inbound_source_url
            if firm.inbound_source_url in returned_urls
            else firm.source_url
        )

        def _kept(name: str, value: Any) -> Any:
            return value if name in supported else ([] if isinstance(value, list) else None)

        try:
            record = FamilyOffice(
                firm_name=firm.firm_name.strip(),
                domain=(firm.domain or None),
                firm_type=firm.firm_type,
                thesis=firm.thesis.strip(),
                sectors=_kept("sectors", firm.sectors) or [],
                stages=_kept("stages", firm.stages) or [],
                check_size_low=_kept("check_size_low", firm.check_size_low),
                check_size_high=_kept("check_size_high", firm.check_size_high),
                geography=_kept("geography", firm.geography) or [],
                notable_investments=(
                    _kept("notable_investments", firm.notable_investments) or []
                ),
                inbound_path=InboundPath(
                    kind=inbound_kind,
                    value=inbound_value,
                    source_url=inbound_source,
                ),
                people=[],
                source_url=firm.source_url,
                source_title=firm.source_title.strip(),
                retrieved_at=moment,
                verified_at=moment,
                stale_after=default_stale_after(moment),
            )
        except Exception as exc:  # noqa: BLE001 - the schema is the last gate
            # Privacy, freshness and the role-address allowlist all land here.
            # A rejection at this line is the type doing its job, not a bug.
            out.rejections["schema_refused"] += 1
            log.info(
                "capital_firm_refused_by_schema",
                firm=firm.firm_name[:80],
                reason=str(exc)[:200],
            )
            continue

        seen.add(key)
        out.firms.append(record)

    return out


# ---------------------------------------------------------------------------
# One pass
# ---------------------------------------------------------------------------

async def run_curation(
    *,
    adapter: SearchAdapter,
    queries: list[str] | None = None,
    now: datetime | None = None,
    client: Any | None = None,
    known_domains: set[str] | None = None,
) -> Curation:
    """Search, propose, verify — one editorial pass over the open web.

    Queries run in sequence rather than in parallel. This is an ops job nobody
    is waiting on, and the provider's rate limit is the real constraint; the
    concurrency `gtm/discovery` needs exists because a founder is sitting in
    the request, which is not true here.
    """
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    plan = queries if queries is not None else curation_queries()
    outcome = Curation()
    seen = set(known_domains or set())
    provider_failures = 0

    async def _search(query: str) -> list[SearchResult] | None:
        nonlocal provider_failures
        try:
            return await adapter.search(query, max_results=10)
        except SearchUnavailableError:
            provider_failures += 1
            outcome.queries_failed += 1
            log.warning("capital_curation_search_unavailable", query=query)
        except Exception:  # noqa: BLE001 - one query never sinks the pass
            outcome.queries_failed += 1
            log.exception("capital_curation_query_failed", query=query)
        return None

    # ── Stage one: names ────────────────────────────────────────────────────
    names: list[str] = []
    for query in plan:
        results = await _search(query)
        if results is None:
            continue
        outcome.queries_run += 1
        outcome.sources_seen += len(results)
        try:
            found = await harvest_names(results, query=query, client=client)
        except Exception:  # noqa: BLE001
            log.exception("capital_curation_names_failed", query=query)
            continue
        for name in found:
            if name.lower() not in {n.lower() for n in names}:
                names.append(name)

    outcome.names_found = len(names)
    log.info("capital_curation_names", names=len(names))

    # ── Stage two: each firm's own site, or no record ───────────────────────
    for name in names:
        for template in _FIRM_SITE_TEMPLATES:
            site_query = template.format(name=name)
            results = await _search(site_query)
            if results is None:
                continue
            outcome.queries_run += 1
            outcome.sources_seen += len(results)

            try:
                proposed = await propose_firms(
                    results, query=site_query, now=moment, client=client
                )
            except Exception:  # noqa: BLE001
                log.exception("capital_curation_proposal_failed", query=site_query)
                continue

            verified = verify_firms(
                proposed, results, now=moment, known_domains=seen
            )
            outcome.rejections.update(verified.rejections)
            if verified.firms:
                outcome.firms.extend(verified.firms)
                seen.update(_dedupe_key_of(f) for f in verified.firms)
                # Its own site answered. The second template would only spend
                # another search to re-find the same firm.
                break

    if provider_failures and outcome.queries_run == 0:
        # Every query failed for the same reason. Reporting "no firms found"
        # here would let a dead provider look like an exhausted web.
        raise CurationUnavailableError(
            "The search provider was unavailable, so no query ran. This is not "
            "the same as finding nothing."
        )

    log.info(
        "capital_curation_complete",
        firms=len(outcome.firms),
        queries_run=outcome.queries_run,
        queries_failed=outcome.queries_failed,
        sources=outcome.sources_seen,
        rejections=dict(outcome.rejections),
    )
    return outcome


def _dedupe_key_of(firm: FamilyOffice) -> str:
    domain = _domain_of(firm.domain or "") or _domain_of(firm.source_url)
    return domain or normalise(firm.firm_name)
