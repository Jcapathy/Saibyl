# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# build_exclusions(profile) -> CategoryExclusions
# CategoryExclusions, ExcludedCompany, ExclusionReason
# MAX_EXCLUSIONS_IN_QUERY, MIN_EXCLUDED_NAME_CHARS, MIN_DOMAIN_STEM_CHARS
# ─────────────────────────────────────────────────────────
"""Who sells what the founder sells, derived from the profile and nothing else.

Discovery went looking for buyers and returned vendors. `companies using Datadog
"observability tooling"` is a good query for finding Datadog's customers and an
even better one for finding Datadog, because Datadog is the single page on the
open web that most strongly matches both halves of it. The founder asked who
they could sell to and got a list of the people they are selling against.

**The exclusion set is derived, not curated.** A hardcoded list of vendor names
would be wrong for every founder outside the categories somebody thought to
type in, and it would rot. Two fields the profile already carries say who the
competitors are, and both say it about *this* founder:

    competitors[]        named in material the founder uploaded and marked as a
                         competitor's. `named_competitors` is the grounded
                         subset — see the note on grounding below.
    incumbent_tooling    what this archetype runs today. `icp_schema` calls it
                         "the single most load-bearing field in the profile: a
                         B2B buyer evaluates net of what they would have to rip
                         out" — and a company whose product would be ripped out
                         to make room for the founder's product is, by that
                         field's own definition, selling into the founder's
                         category. That is what makes the Datadog case fixable
                         without anybody naming Datadog in this file.

`category` is why the second derivation holds rather than a third source of
names. It describes what the founder sells; the makers of the incumbent tools
sell into it; so they are competitors. It is carried on `CategoryExclusions` so
the preview can say what the exclusions are *for*, and it is never negated as a
search term — the queries need it to find buyers.

**Two mechanisms, because one of them cannot be trusted alone.**

  * *Search operators.* `-"New Relic"` is appended to the query text. The
    Anthropic adapter hands the query to a model that then calls `web_search`
    (`search_adapter.py:217`), so a negative term is a strong instruction and
    not an enforced filter. It reduces what comes back; it does not decide.
  * *A post-filter on returned candidates.* `extraction.verify_candidates`
    drops a candidate that matches this set. This one is enforced, it is pure,
    and it is the reason the incumbent angle is safe at all — `companies using
    Datadog -Datadog` is a self-defeating query, so that angle *cannot* negate
    the vendor it is asking about and must catch it on the way back instead.

`blocked_domains` on the search tool (`search_adapter.py:205`) is the third,
hardest mechanism and is deliberately not used here: it takes domains, the
profile carries names, and deriving `datadoghq.com` from "Datadog" means
inventing a fact about a company. That is the one thing this codebase does not
do. Privacy's own domain list is hand-written for that reason.

**An ungrounded competitor is not excluded, and that is not an oversight.**
`icp_schema` rejects an adversarial archetype that names a company with no
source document, because a model asked about competitors will confabulate, and
`_build_profile` in `icp_synthesizer` already filters `mentioned_in` down to
documents marked `material_kind='competitor'`. An exclusion built here is
rendered back to the founder by name in the estimate preview, so excluding on
an ungrounded name would put a possibly-invented company in front of them under
the claim that it is their rival. DECISIONS §7 forbids relaxing that guardrail
to improve output. So ungrounded names are counted, logged with their names at
warning level, and reported to the founder as a count with a remedy — never as
a name.

**A false exclusion costs one lead; a false inclusion costs the list.** Where
this set has to guess — a tool in `incumbent_tooling` that the buyer uses but
would never rip out, say a chat app — it excludes. That is a real cost and the
answer to it is transparency rather than cleverness: every excluded company is
returned by `GET /gtm/estimate` with the reason it was excluded, before any
credits are spent, so a founder who sees a wrong name fixes the profile field
that produced it.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Literal

import structlog
from pydantic import BaseModel, Field, computed_field

from app.services.engine.personas.icp_schema import ICPProfile

log = structlog.get_logger()

# Negative terms appended to one query. Past a handful, the negatives outweigh
# the query they qualify and providers start dropping them or returning nothing
# — the same failure mode as `MAX_INCUMBENTS_IN_QUERY`. The post-filter enforces
# the whole set regardless, so this caps noise in the query and costs no safety.
MAX_EXCLUSIONS_IN_QUERY = 4

# A one- or two-character name matches far too much. "Excluded 'AI'" would drop
# most of a candidate list on a token match.
MIN_EXCLUDED_NAME_CHARS = 3

# Below this, a domain-stem prefix match is a coincidence rather than a signal.
MIN_DOMAIN_STEM_CHARS = 4

ExclusionReason = Literal["named_rival", "incumbent_tool"]

# Founder-facing. Says why this company is on the list, in the register of
# `AudienceReview.tsx`: no field names, no terms of art.
_REASON_NOTE: dict[str, str] = {
    "named_rival": "your uploaded material names them as a rival",
    "incumbent_tool": "makes a tool your buyers already run, so they sell what you sell",
}

# Dropped before matching so "Datadog" matches "Datadog, Inc." A suffix here can
# only make two names more likely to be judged the same company.
_LEGAL_SUFFIXES: frozenset[str] = frozenset({
    "ag", "bv", "co", "corp", "corporation", "company", "gmbh", "inc",
    "incorporated", "limited", "llc", "ltd", "nv", "oy", "plc", "pty", "sa",
    "sarl", "srl",
})

_NON_WORD = re.compile(r"[^a-z0-9]+")
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*://")


def _tokens(name: str) -> tuple[str, ...]:
    """Comparable word tokens for a company name, minus its legal suffix.

    Returns `()` for anything that normalises away to nothing, which is how a
    blank or punctuation-only name is kept out of the set rather than becoming
    a token that matches everything.
    """
    parts = [p for p in _NON_WORD.split(name.casefold()) if p]
    while parts and parts[-1] in _LEGAL_SUFFIXES:
        parts.pop()
    return tuple(parts)


def _compact(tokens: Iterable[str]) -> str:
    """"New Relic" -> "newrelic". The form a domain is written in."""
    return "".join(tokens)


def _domain_stems(domain: str | None) -> list[str]:
    """Host labels of `domain`, minus the final TLD.

    No public-suffix list, so `example.co.uk` yields `["example", "co"]` rather
    than `["example"]`. Harmless: an extra stem can only be compared against the
    exclusion names, and "co" is below `MIN_DOMAIN_STEM_CHARS`.
    """
    if not domain:
        return []
    host = _SCHEME.sub("", domain.casefold().strip())
    host = host.split("/", 1)[0].split("?", 1)[0].split("@")[-1].split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    labels = [label for label in host.split(".") if label]
    return labels[:-1] if len(labels) > 1 else labels


def _contains_run(haystack: tuple[str, ...], needle: tuple[str, ...]) -> bool:
    """True when `needle` appears in `haystack` as a contiguous token run.

    Token-level rather than substring, so "Datadog" matches "Datadog Cloud" and
    "Datadog, Inc." but not "Datadoghub"; and contiguous, so "New Relic" does
    not match a company that happens to use both words apart.
    """
    if not needle or len(needle) > len(haystack):
        return False
    span = len(needle)
    return any(
        haystack[i:i + span] == needle
        for i in range(len(haystack) - span + 1)
    )


class ExcludedCompany(BaseModel):
    """One company discovery will not return, and why.

    `note` is written for the founder rather than derived by the client, so the
    reason a name appears travels with the name instead of being reconstructed
    from `reason` by whatever renders it.
    """

    name: str
    reason: ExclusionReason
    note: str


class CategoryExclusions(BaseModel):
    """Everything discovery treats as a competitor for one profile.

    Deterministic from the profile: same profile, same list, same order. That is
    the same property `query_compiler` is built around and for the same reason —
    this is shown to the founder before they spend credits, and a list that
    varied between the preview and the run would not be a preview.
    """

    # What the founder sells. Present so the preview can say what the list is
    # for; never used as a negative search term, because the queries need it.
    category: str = ""
    companies: list[ExcludedCompany] = Field(default_factory=list)

    # Names on the profile that no uploaded document backs. Counted, not named
    # — see the module docstring on grounding.
    ungrounded_count: int = 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sentence(self) -> str:
        """What the founder reads. One sentence, no terms of art."""
        unusable = (
            f" {self.ungrounded_count} other name"
            f"{'' if self.ungrounded_count == 1 else 's'} on your profile can't "
            f"be used yet, because none of your uploaded files backs "
            f"{'it' if self.ungrounded_count == 1 else 'them'} up."
            if self.ungrounded_count
            else ""
        )

        if not self.companies:
            return (
                "Nothing is being left out. Your profile doesn't name a rival, "
                "and it doesn't list any tool your buyers already run — so "
                "there's nothing yet that tells us who sells what you sell."
                + unusable
            )

        names = [c.name for c in self.companies]
        listed = (
            names[0]
            if len(names) == 1
            else f"{', '.join(names[:-1])} and {names[-1]}"
        )
        count = f"{len(names)} compan{'y' if len(names) == 1 else 'ies'}"
        return (
            f"Leaving out {count} that sell what you sell, so they don't crowd "
            f"out real buyers: {listed}." + unusable
        )

    def negative_terms_for(self, positive_query: str) -> list[str]:
        """Names to negate in `positive_query`, in profile order.

        A name already asked for positively is never negated. `companies using
        Datadog -Datadog` returns nothing at all, which would turn the incumbent
        angle — the most load-bearing of the three — into a silent no-op. Those
        companies are still dropped, by the post-filter, on the way back.
        """
        asked_for = _tokens(positive_query)
        keep: list[str] = []
        for company in self.companies:
            tokens = _tokens(company.name)
            if _contains_run(asked_for, tokens):
                continue
            keep.append(company.name)
            if len(keep) >= MAX_EXCLUSIONS_IN_QUERY:
                break
        return keep

    def match(self, company_name: str, domain: str | None = None) -> ExcludedCompany | None:
        """The excluded company this candidate is, or None.

        Matches on the name as a contiguous token run, and on the domain stem as
        a prefix — "Datadog" against `datadoghq.com` is the shape the reported
        defect actually arrives in, and a name-only check misses it.
        """
        candidate_tokens = _tokens(company_name)
        stems = _domain_stems(domain)

        for company in self.companies:
            tokens = _tokens(company.name)
            if _contains_run(candidate_tokens, tokens):
                return company
            compact = _compact(tokens)
            if len(compact) >= MIN_DOMAIN_STEM_CHARS and any(
                stem.startswith(compact) for stem in stems
            ):
                return company
        return None


def build_exclusions(profile: ICPProfile) -> CategoryExclusions:
    """Derive one profile's competitor set. Pure, deterministic, no I/O.

    Order is the founder's own: competitors they named first, then the tools
    their archetypes run, in archetype order. Deduplicated on the comparable
    form of the name, first occurrence keeping its reason — so a company that is
    both a named rival and an incumbent tool reads as the former, which is the
    stronger and more legible statement.
    """
    companies: list[ExcludedCompany] = []
    seen: set[str] = set()
    too_short: list[str] = []

    def add(raw_name: str, reason: ExclusionReason) -> None:
        name = " ".join(raw_name.split())
        tokens = _tokens(name)
        compact = _compact(tokens)
        if not compact:
            return
        if len(compact) < MIN_EXCLUDED_NAME_CHARS:
            # Not dropped quietly: a two-letter product name is a real thing to
            # own, and a founder whose incumbent tool vanished from this list
            # should be able to find out why from the logs.
            too_short.append(name)
            return
        if compact in seen:
            return
        seen.add(compact)
        companies.append(ExcludedCompany(
            name=name, reason=reason, note=_REASON_NOTE[reason]
        ))

    for competitor in profile.named_competitors:
        add(competitor.name, "named_rival")

    for adversary in profile.adversarial:
        # Same grounding rule, already enforced at validation: a named
        # competitor here cannot exist without `grounded_in`.
        if adversary.competitor_name and adversary.grounded_in:
            add(adversary.competitor_name, "named_rival")

    for archetype in profile.archetypes:
        for tool in archetype.incumbent_tooling:
            add(tool, "incumbent_tool")

    ungrounded = [c.name for c in profile.competitors if not c.is_grounded]
    if ungrounded:
        log.warning(
            "gtm_exclusions_ungrounded_competitors",
            profile=profile.name,
            competitors=ungrounded,
            detail=(
                "named with no competitor-material document behind them, so they "
                "are not excluded and are not shown to the founder by name"
            ),
        )
    if too_short:
        log.info(
            "gtm_exclusions_name_too_short",
            profile=profile.name,
            names=too_short,
            min_chars=MIN_EXCLUDED_NAME_CHARS,
        )

    exclusions = CategoryExclusions(
        category=profile.category,
        companies=companies,
        ungrounded_count=len(ungrounded),
    )
    log.info(
        "gtm_exclusions_built",
        profile=profile.name,
        category=profile.category,
        # Zero here is a real state — a profile that names no rival and lists no
        # incumbent tooling — and it changes what a discovery returns. Logged as
        # a number so "nothing was excluded" is distinguishable from "exclusion
        # never ran", which is the failure this codebase keeps finding.
        excluded=len(companies),
        named_rivals=sum(1 for c in companies if c.reason == "named_rival"),
        incumbent_tools=sum(1 for c in companies if c.reason == "incumbent_tool"),
        ungrounded=len(ungrounded),
    )
    return exclusions
