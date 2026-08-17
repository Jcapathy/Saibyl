# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# build_query_plan(item, type_hint, field, competitors) -> QueryPlan   [async]
# QueryPlan, TrackQuery
# ─────────────────────────────────────────────────────────
"""Stage 0 + Stage 1 of the clearance search: classify, decompose, translate.

One structured LLM call turns a founder's free-text item into the search
program the tracks execute: a classification (name / invention / both — with
the inference recorded as an assumption when no hint was given), 3–6 USPTO
Open Data Portal query strings per relevant axis in BOTH the founder's product
language and patent-ese, candidate CPC class prefixes, and the trademark marks
to check (the name, its spelling and phonetic alternatives, and the name minus
generic suffixes).

This runs on the main model, not the fast one. It is one call per run and it
decides everything downstream: a query program that misses the mechanism's
patent-ese register makes every later track search the wrong literature, and a
wrong classification skips a whole track. That is the judgment tier of the
DECISIONS §14 model policy, the same reasoning `subject_brief._distil` and
`objection_canonicalizer` document.
"""
from __future__ import annotations

import structlog
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.llm_client import llm_structured
from app.services.billing.usage_ledger import usage_context

logger = structlog.get_logger()

CLASSIFICATIONS = ("name", "invention", "both")
AXES = ("FUNCTION", "STRUCTURE", "DOMAIN")

# Ceilings on what a plan may carry, applied after the model call. The tracks
# execute every query in the plan against the live API, so an unbounded plan is
# an unbounded number of API round trips.
MAX_QUERIES_PER_AXIS = 6
MAX_CPC_PREFIXES = 6
MAX_MARKS = 8


class TrackQuery(BaseModel):
    track: str  # "patents" — Track A works from marks_to_check, not queries
    query: str  # ODP query string
    axis: str  # FUNCTION | STRUCTURE | DOMAIN


class QueryPlan(BaseModel):
    classification: str  # name | invention | both
    assumptions: list[str] = Field(default_factory=list)
    queries: list[TrackQuery] = Field(default_factory=list)
    candidate_cpc: list[str] = Field(default_factory=list)
    marks_to_check: list[str] = Field(default_factory=list)


# The translation table and per-field examples from the skill's
# query-patterns reference, embedded verbatim so the model generates queries in
# both registers. Patent titles rarely use market language; a sweep that only
# speaks the founder's words misses the art that matters.
_TRANSLATION_TABLE = """\
| Product language | Patent-ese equivalents |
|---|---|
| app, platform, tool | system, method, apparatus, computer-implemented method |
| smart X | X + "machine learning", "adaptive", "automated", "sensor-based" |
| AI-powered | "artificial intelligence", "neural network", "language model", "generative" |
| tracks / monitors | monitoring, detecting, sensing, measuring, surveillance |
| blocks / stops | preventing, mitigating, inhibiting, filtering, intercepting |
| recommends | "recommendation", "personalization", "ranking", "selection" |
| secure / safety | security, authentication, tamper, integrity, protection |
| eco-friendly | biodegradable, recyclable, "reduced emission", sustainable |
| instant / fast | "real-time", "low-latency", "on-demand" |
| brandable coined words | strip them — search the mechanism, not the name |"""

_FIELD_EXAMPLES = """\
- Software/AI: "chatbot guardrail" -> language model + (filter OR moderation OR policy);
  "prompt firewall" -> prompt + (injection OR malicious OR sanitization).
- Mechanical/consumer products: "no-spill travel mug" -> container + (spill OR leak) +
  (valve OR seal OR closure); "quick-release mount" -> coupling/latch + release mechanism.
- Food tech: "high-protein meal kit personalization" -> "meal planning" OR "nutrition" +
  (personalized OR dietary) + method; formulations -> composition + ingredient terms."""

# Condensed from the skill's cpc-field-map reference — enough for the model to
# pick 2-6 candidate class prefixes for any field. Exact prefixes only; the ODP
# API's CPC field does not take wildcards reliably.
_CPC_GUIDANCE = """\
A01 agriculture/agtech · A21/A23 foods & food processing (A23L prepared foods) ·
A41-A45 apparel/footwear · A47 furniture/kitchenware · A61 medical (A61B devices,
A61K pharma) · A63 sports/games/toys · B25J robotics · B29/B33Y plastics & 3D
printing · B60-B64 vehicles (B64U drones) · B65 packaging/logistics · C02 water
treatment · C07 organic chemistry · C08 polymers · C09 coatings/adhesives · C11
detergents/cosmetics bases · C12 biotech/fermentation · D01-D06 textiles ·
E04 building structures/modular construction · F16 machine elements (valves,
couplings) · F24F HVAC · G01 sensors/measurement · G02 optics · G05 control
(G05D autonomous) · G06F digital data processing (G06F 21 security) · G06N AI/ML
(G06N 3 neural nets, G06N 20 ML) · G06Q business methods (20 payments, 30
commerce) · G06T image processing · G06V image recognition · G09B teaching
devices · G10L speech · G16H health informatics · H01M batteries · H02J/H02S
power/solar · H04L networks & network security (H04L 9 crypto) · H04N
video/streaming · H04W wireless · H05K PCBs.
Cross-cutting AI-security note: LLM/AI-security items typically classify under
G06F 21 + G06N 3, often with H04L 9 — sweep all three."""

_PROMPT = """You are planning a USPTO clearance search for an item a founder submitted.

ITEM: {item}
FIELD/INDUSTRY: {field}
TYPE HINT: {type_hint}
COMPETITORS NAMED: {competitors}

STEP 1 — CLASSIFY the item as exactly one of:
- "name" — looks like a brand/product name (short, coined, capitalized, no mechanism described)
- "invention" — describes a mechanism, method, composition, or design; no brandable name present
- "both" — a name AND a described mechanism are both present
{hint_rule}

STEP 2 — DECOMPOSE the item into three axes:
1. FUNCTION — what it does (verbs, outcomes)
2. STRUCTURE — what it is / how it is built (components, architecture, ingredients)
3. DOMAIN — field of use (industry, environment, user)

STEP 3 — GENERATE QUERIES. For each relevant axis, write 3 to 6 query strings for
the USPTO Open Data Portal patent-application search. Use plain keywords and quoted
phrases joined with AND / OR, e.g.:
  prompt AND (injection OR sanitization)
  "meal planning" AND personalized AND method
Generate them in BOTH registers — the founder's product language AND patent-ese —
using this translation table:

{translation_table}

Per-field examples of the translation habit (pattern, not exhaustive):
{field_examples}

Rules for queries:
- If the item is classified "name" with no described function, generate few or no
  patent queries — a coined name is not a mechanism. If any function is described,
  search that function.
- Strip coined/brandable words from patent queries — search the mechanism, not the name.
- Start broad enough to find foundational art; the search runner narrows or broadens
  by hit count, so do not pre-qualify every query with the DOMAIN axis.

STEP 4 — CANDIDATE CPC CLASSES. Pick 2 to 6 CPC class/subclass prefixes (exact
prefixes such as "G06N" or "A23L", never wildcards) that this item would classify
under, guided by:
{cpc_guidance}

STEP 5 — MARKS TO CHECK. If a name is present (classification "name" or "both"),
list the trademark strings to check: the exact name, obvious spelling alternatives
and phonetic equivalents, and the name minus generic suffixes such as "AI", "Labs",
"Pro", "App", "Inc". If classification is "invention", return an empty list.

STEP 6 — ASSUMPTIONS. Record every inference you made that the founder did not
state: the classification (if no type hint was given), the field (if you inferred
one), what you took the mechanism to be. Empty list only if nothing was inferred.

Return ONLY JSON:
{{"classification": "name|invention|both",
  "assumptions": ["..."],
  "queries": [{{"track": "patents", "query": "...", "axis": "FUNCTION|STRUCTURE|DOMAIN"}}],
  "candidate_cpc": ["G06N"],
  "marks_to_check": ["..."]}}"""

_HINT_GIVEN = (
    'The caller supplied the type hint "{type_hint}" — use it as the '
    "classification. Do not second-guess it."
)
_HINT_ABSENT = (
    "No type hint was supplied — infer the classification from the item and "
    "record the inference in assumptions."
)


def _dedupe(values: list[str]) -> list[str]:
    """Order-preserving dedupe, case-insensitive, empties dropped."""
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        cleaned = value.strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            out.append(cleaned)
    return out


def _normalize(plan: QueryPlan, item: str, type_hint: str | None) -> QueryPlan:
    """Clamp the model's plan to the contract the tracks execute against.

    Everything here is a bound or a consistency rule, not a judgment: the
    judgment already happened in the call. A type hint from the caller always
    wins over the model's classification — the input contract says so — and an
    inferred classification always leaves a trace in assumptions, because the
    skill requires programmatic runs to state their assumptions instead of
    asking questions.
    """
    hint = (type_hint or "").strip().lower()
    classification = (plan.classification or "").strip().lower()
    assumptions = [a.strip() for a in plan.assumptions if a.strip()]

    if hint in CLASSIFICATIONS:
        classification = hint
    elif classification not in CLASSIFICATIONS:
        classification = "both"
        assumptions.append(
            "the item could not be confidently classified as a name or an "
            "invention, so it was treated as both and all tracks were run"
        )
    if hint not in CLASSIFICATIONS and not any(
        classification in a.lower() for a in assumptions
    ):
        assumptions.append(
            f'no type hint was given; the item was read as "{classification}"'
        )

    per_axis: dict[str, int] = {}
    queries: list[TrackQuery] = []
    seen_queries: set[str] = set()
    for q in plan.queries:
        text = q.query.strip()
        axis = q.axis.strip().upper()
        if not text or axis not in AXES:
            continue
        if text.lower() in seen_queries:
            continue
        if per_axis.get(axis, 0) >= MAX_QUERIES_PER_AXIS:
            continue
        seen_queries.add(text.lower())
        per_axis[axis] = per_axis.get(axis, 0) + 1
        queries.append(TrackQuery(track="patents", query=text, axis=axis))

    marks = _dedupe(plan.marks_to_check)[:MAX_MARKS]
    if classification == "invention":
        # No name present — a mark check would be checking a string the
        # founder never submitted as a name.
        marks = []
    elif not marks:
        # A name is present but the model returned nothing to check; the exact
        # item is the one mark that is always safe to check.
        marks = [item.strip()][:MAX_MARKS]

    cpc = _dedupe([c.upper().replace(" ", "") for c in plan.candidate_cpc])
    cpc = [c for c in cpc if 3 <= len(c) <= 12][:MAX_CPC_PREFIXES]

    return QueryPlan(
        classification=classification,
        assumptions=assumptions,
        queries=queries,
        candidate_cpc=cpc,
        marks_to_check=marks,
    )


async def build_query_plan(
    item: str,
    type_hint: str | None,
    field: str | None,
    competitors: list[str],
    *,
    organization_id: str | None = None,
) -> QueryPlan:
    """Classify the item and compile the search program the tracks execute.

    One `llm_structured` call on the main model (judgment tier — see module
    docstring), attributed to the cost ledger as `ip_clearance_query_plan`.
    """
    hint = (type_hint or "").strip().lower()
    hint_rule = (
        _HINT_GIVEN.format(type_hint=hint) if hint in CLASSIFICATIONS else _HINT_ABSENT
    )

    with usage_context("ip_clearance_query_plan", organization_id=organization_id):
        raw = await llm_structured(
            messages=[
                {
                    "role": "user",
                    "content": _PROMPT.format(
                        item=item,
                        field=field or "(not stated — infer)",
                        type_hint=hint if hint in CLASSIFICATIONS else "(none)",
                        competitors=", ".join(competitors) or "(none)",
                        hint_rule=hint_rule,
                        translation_table=_TRANSLATION_TABLE,
                        field_examples=_FIELD_EXAMPLES,
                        cpc_guidance=_CPC_GUIDANCE,
                    ),
                }
            ],
            schema=QueryPlan,
            model=f"{settings.llm_provider}/{settings.llm_model}",
        )

    plan = _normalize(raw, item, type_hint)
    logger.info(
        "ip_clearance_query_plan_built",
        classification=plan.classification,
        queries=len(plan.queries),
        candidate_cpc=plan.candidate_cpc,
        marks_to_check=len(plan.marks_to_check),
        assumptions=len(plan.assumptions),
    )
    return plan
