# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# MATERIAL_KINDS                                  -> frozenset[str]
# MaterialSuggestion(kind, confidence, rationale)
# suggest_material_kind(text, *, filename, media_type) -> MaterialSuggestion | None
# ─────────────────────────────────────────────────────────
"""Propose what kind of material an upload is. A proposal, never a label.

## Why this exists

`documents.material_kind` (`own` / `competitor` / `market`) is what buckets an
upload for ICP synthesis, and nothing in the product can set it: the frontend
posts to `/documents/upload` without the parameter, so every row is `own` (or
NULL, which reads as `own`). `ProjectMaterial.competitor_ids` is therefore always
empty, so `_ground_adversarial` strips every competitor name the synthesis pass
proposes, and every adversarial archetype degrades to an unnamed skeptic. The
grounding machinery works; it has simply never had an input.

## Why the proposal is not the label — DECISIONS_V2 §7

Read this before making the classifier's output authoritative, because the
temptation is obvious and the consequence is not recoverable.

The guardrail chain is: `material_kind = 'competitor'` on a document is what puts
that document id into `ProjectMaterial.competitor_ids`; membership of that set is
the only thing that lets `AdversarialArchetype` keep a `competitor_name`; and the
schema refuses a `competitor_name` with an empty `grounded_in`. The invariant the
chain protects is **an unlabelled document can never license a name.**

If this classifier wrote `material_kind` directly, that invariant would become
"a model's guess can license a name". The failure is not a mislabelled row — it
is a founder reading a report in which a swarm of incumbent-aligned agents argue
against a *named real company*, on the strength of a cheap model having decided
that a blog post in the founder's own upload folder was competitor material.
Phase 2's live run already produced publishable copy containing an invented
dataset; this would produce a publishable comparison against a company that
never consented to the comparison and whose claimed behaviour came from model
memory. DECISIONS §7 says the guardrails do not get relaxed to improve output
quality, and this is precisely that relaxation wearing a convenience costume.

So: the suggestion is written to `material_kind_suggested` +
`material_kind_confidence`, `material_kind` stays human-set, and
`gather_material` buckets on `material_kind` alone. A human confirming the
suggestion is what grants naming rights. Confidence is recorded so the UI can
rank what to ask about first — not so a threshold can auto-promote it. **There
is no confidence at which this may write `material_kind`.**
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import structlog

from app.core.llm_client import _extract_json, llm_fast
from app.services.refs import enum_ref

logger = structlog.get_logger()

MATERIAL_KINDS: frozenset[str] = frozenset({"own", "competitor", "market"})

# Head and tail of the extracted text. A document says what it is in its opening
# and its conclusion; the middle is body. Sized to keep this a few-tenths-of-a-
# cent call on the fast model — DECISIONS §14 routes volume work to Haiku, and
# this runs once per upload.
_SAMPLE_HEAD_CHARS = 4_000
_SAMPLE_TAIL_CHARS = 1_500

# Below this there is nothing to classify. Returned as `None` (a miss the caller
# counts), not as a low-confidence `own`, so "too short to judge" and "judged to
# be the founder's own material" stay distinguishable.
_MIN_TEXT_CHARS = 200

_MAX_TOKENS = 400


@dataclass(frozen=True)
class MaterialSuggestion:
    """A proposal about one upload. Consumed by a human, not by the guardrail."""

    kind: str
    confidence: float
    rationale: str


def _sample(text: str) -> str:
    if len(text) <= _SAMPLE_HEAD_CHARS + _SAMPLE_TAIL_CHARS:
        return text
    return (
        f"{text[:_SAMPLE_HEAD_CHARS]}\n\n[… {len(text) - _SAMPLE_HEAD_CHARS - _SAMPLE_TAIL_CHARS} "
        f"characters omitted …]\n\n{text[-_SAMPLE_TAIL_CHARS:]}"
    )


def _prompt(text: str, filename: str, media_type: str) -> str:
    return f"""Classify one uploaded file by whose material it is. The team
uploading it is building a product and is assembling the material that describes
their market.

FILE: {filename}
KIND OF FILE: {media_type}

CONTENT (may be truncated in the middle):
{_sample(text)}

Choose exactly one:
- "own" — produced by the team itself about their own product: PRD, landing
  page, deck, pricing, roadmap, changelog, their own customer list or CRM
  export, their own demo video.
- "competitor" — produced by, or entirely about, a *different company's*
  product: a rival's pricing page, docs, marketing site, a head-to-head
  comparison written by someone else.
- "market" — category or industry context owned by nobody in particular: an
  analyst report, a news article about the category, a survey, a standards
  document.

Judge by whose product the document is *about*, not by what it mentions. A
team's own deck naming three rivals is still "own". A rival's pricing page is
"competitor" even if it never names anyone.

If it is genuinely ambiguous, say so with a low confidence rather than picking
confidently. A wrong "competitor" is more costly than an unsure "own".

Return ONLY JSON:
{{"kind": "own|competitor|market",
  "confidence": 0.0-1.0,
  "rationale": "one sentence citing what in the content decided it"}}"""


async def suggest_material_kind(
    text: str,
    *,
    filename: str,
    media_type: str,
) -> MaterialSuggestion | None:
    """Propose a material kind for one upload, or `None` when it cannot.

    `None` on: too little text, an unparseable answer, a kind outside the
    vocabulary, or a failed call. Every one of those is logged with its own
    event, because "the classifier had nothing to say" and "the classifier was
    never asked" reaching the database as the same NULL is the defect class this
    codebase keeps shipping — a health check would report every document
    classified and every column would be empty.
    """
    if len(text.strip()) < _MIN_TEXT_CHARS:
        logger.info(
            "material_kind_not_classified",
            filename=filename,
            media_type=media_type,
            chars=len(text.strip()),
            reason="below the minimum text length to judge",
        )
        return None

    try:
        raw = await llm_fast(
            messages=[{"role": "user", "content": _prompt(text, filename, media_type)}],
            max_tokens=_MAX_TOKENS,
            temperature=0.0,
        )
        data = json.loads(_extract_json(raw))
    except Exception as exc:
        logger.warning(
            "material_kind_classification_failed",
            filename=filename,
            media_type=media_type,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return None

    # The three kinds are rendered to the model as a bulleted list, so they come
    # back quoted, cased and decorated — the copy-back pressure `services/refs`
    # exists for. `enum_ref` returns None on a genuine miss so the miss is
    # countable rather than becoming a confident "own".
    kind = enum_ref(data.get("kind"), MATERIAL_KINDS)
    if kind is None:
        logger.warning(
            "material_kind_unrecognised",
            filename=filename,
            returned=str(data.get("kind"))[:60],
            allowed=sorted(MATERIAL_KINDS),
        )
        return None

    try:
        confidence = max(0.0, min(1.0, float(data.get("confidence"))))
    except (TypeError, ValueError):
        # A kind with no confidence is still useful to a human reviewer; a
        # fabricated 1.0 would not be. Zero reads as "unrated" in the ordering
        # the UI will apply, and the miss is on the record.
        logger.info(
            "material_kind_confidence_missing",
            filename=filename,
            returned=str(data.get("confidence"))[:40],
        )
        confidence = 0.0

    suggestion = MaterialSuggestion(
        kind=kind,
        confidence=confidence,
        rationale=str(data.get("rationale") or "").strip()[:400],
    )
    logger.info(
        "material_kind_suggested",
        filename=filename,
        media_type=media_type,
        suggested=suggestion.kind,
        confidence=suggestion.confidence,
        # Stated on every line so a future reader of the logs cannot mistake
        # this for the label itself. See the module docstring, DECISIONS §7.
        detail="proposal only; material_kind stays human-set and no confidence promotes it",
    )
    return suggestion
