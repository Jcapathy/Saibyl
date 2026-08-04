# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# score_candidates(candidates, archetype) -> list[Candidate]   [sorted, scored]
# score_components(candidate, archetype) -> dict[str, float]
# SCORE_WEIGHTS
# ─────────────────────────────────────────────────────────
"""Rank candidates against the archetype that found them.

**This is a rank ordering, not a probability.** `match_score` says "look at
this one before that one". It does not say a company is 74% likely to buy, and
nothing in the product may render it as though it did. The five components are
returned alongside it so the founder sees the arithmetic rather than a number
with no referent — which is the same reason `simulation_analysis` carries the
quotes behind every figure.

**The weights below are declared priors and are labelled as such.** This
codebase's §2a sweep names "a number invented rather than measured" as a failure
class, and it is right: `viral_but_off_message` compared takeaway accuracy to an
absolute 0.25 when the live distribution was 0.07–0.14, so a flag meant to be
rare fired on two of three variants. These weights have the same character —
there is no measurement behind them, because there is no outcome data yet. What
stops them repeating that defect is that they do not *gate* anything. They order
a list the founder reads top to bottom; nothing is hidden, nothing fires, and no
threshold is crossed. The moment there is qualification feedback — a founder
marking a candidate as a real prospect or as noise — these get derived from it,
and the components are recorded per candidate so that derivation has data to
work from on day one.

The ordering of the weights *is* argued, even if the magnitudes are not:

  incumbent_overlap (0.35)          `icp_schema` calls incumbent tooling the
                                    single most load-bearing field in the
                                    profile, because a B2B buyer evaluates net
                                    of what they would have to rip out. A
                                    company evidenced to run the incumbent is
                                    the strongest signal available from a
                                    search result.
  evidence_density (0.25)           How much of this candidate traces to a
                                    source. Ranking a thinly-evidenced company
                                    above a well-evidenced one wastes the
                                    founder's first ten minutes, and the
                                    founder's first ten minutes are the whole
                                    retention argument for this feature.
  firmographic_completeness (0.15)  Whether the record is actionable at all.
  criteria_signal (0.15)            Whether what they say about themselves
                                    touches what this archetype evaluates on.
  pain_signal (0.10)                Weakest of the five: a pain phrase matching
                                    a company page is as often marketing copy
                                    as it is a real problem.
"""
from __future__ import annotations

import re

import structlog

from app.services.engine.personas.icp_schema import ICPArchetype
from app.services.gtm.schema import EVIDENCED_FIELDS, Candidate

log = structlog.get_logger()

SCORE_WEIGHTS: dict[str, float] = {
    "incumbent_overlap": 0.35,
    "evidence_density": 0.25,
    "firmographic_completeness": 0.15,
    "criteria_signal": 0.15,
    "pain_signal": 0.10,
}

# Fields that make a candidate actionable without further research.
_FIRMOGRAPHIC_FIELDS = ("employee_count_range", "industry", "hq_location")

# Tokens shorter than this carry no signal ("the", "and", "for") and match
# everything, which would push every candidate's text components toward 1.0.
_MIN_TOKEN_CHARS = 4

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall((text or "").casefold()) if len(t) >= _MIN_TOKEN_CHARS}


def _phrase_hit_rate(phrases: list[str], haystack: set[str]) -> float:
    """Share of phrases at least half of whose content tokens appear.

    Half rather than all, because an ICP criterion is written as a sentence
    ("must not require a rip-and-replace migration") and a company page will
    never contain all of it. Half rather than any, because one shared token is
    a coincidence at this vocabulary size.
    """
    scored = 0
    considered = 0
    for phrase in phrases:
        tokens = _tokens(phrase)
        if not tokens:
            continue
        considered += 1
        overlap = len(tokens & haystack)
        if overlap * 2 >= len(tokens):
            scored += 1
    if considered == 0:
        # No criteria in the ICP is not evidence for or against a candidate.
        # Returning 0 would penalise every candidate equally, which is the same
        # as returning 0.0 for all — but it would also read as "matched
        # nothing" in the components the founder sees. 0.0 with the component
        # marked absent is handled by the caller omitting it.
        return 0.0
    return scored / considered


def score_components(candidate: Candidate, archetype: ICPArchetype) -> dict[str, float]:
    """The five components, each 0..1, for one candidate."""
    haystack = _tokens(" ".join([
        candidate.one_liner,
        candidate.industry or "",
        " ".join(candidate.match_reasons),
        " ".join(item.quote for item in candidate.evidence),
    ]))

    wanted_tools = {t.casefold().strip() for t in archetype.incumbent_tooling if t.strip()}
    if wanted_tools:
        found = {t.casefold().strip() for t in candidate.incumbent_tooling}
        overlap = len(wanted_tools & found) / len(wanted_tools)
    else:
        # The archetype names no incumbent. There is nothing to overlap with,
        # so this component cannot discriminate — every candidate scores 0 on
        # it and the remaining components decide the order.
        overlap = 0.0

    evidenced = candidate.evidenced_fields & EVIDENCED_FIELDS
    evidence_density = len(evidenced) / len(EVIDENCED_FIELDS)

    present = sum(
        1 for field in _FIRMOGRAPHIC_FIELDS if getattr(candidate, field, None)
    )
    completeness = present / len(_FIRMOGRAPHIC_FIELDS)

    return {
        "incumbent_overlap": round(overlap, 4),
        "evidence_density": round(evidence_density, 4),
        "firmographic_completeness": round(completeness, 4),
        "criteria_signal": round(_phrase_hit_rate(archetype.evaluation_criteria, haystack), 4),
        "pain_signal": round(_phrase_hit_rate(archetype.pains, haystack), 4),
    }


def score_candidates(
    candidates: list[Candidate],
    archetype: ICPArchetype,
) -> list[Candidate]:
    """Score and order candidates for one archetype.

    Returns new `Candidate` objects rather than mutating in place, and sorts by
    score then company name so a tie has one answer rather than whichever order
    the sources happened to arrive in.
    """
    scored: list[Candidate] = []
    for candidate in candidates:
        components = score_components(candidate, archetype)
        total = sum(SCORE_WEIGHTS[name] * value for name, value in components.items())
        scored.append(candidate.model_copy(update={
            "match_score": round(total, 4),
            "score_components": components,
        }))

    scored.sort(key=lambda c: (-c.match_score, c.company_name.casefold()))
    if scored:
        log.info(
            "gtm_candidates_scored",
            archetype_id=archetype.id,
            count=len(scored),
            top_score=scored[0].match_score,
            bottom_score=scored[-1].match_score,
        )
    return scored
