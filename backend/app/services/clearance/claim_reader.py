# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# read_claims(item, ref, claims_text) -> ClaimReading      [async]
# ClaimReading
# ─────────────────────────────────────────────────────────
"""Reads one reference's claims against the founder's item.

One LLM call per deep-read reference, on the main model rather than the fast
one. This is the judgment tier of the model policy (DECISIONS §14, the same
call `subject_brief._distil` makes): a claim read decides the per-reference
risk tier, the risk tiers roll up into the report's headline, and a wrong
headline is the product being wrong — not one sentence in it being clumsy.
Deep reads are 3–7 per run, so routing them to the main model costs cents.

The reading works ONLY from text the client fetched. The claims text arrives
as an argument, the reference's own metadata rides along for context, and the
prompt forbids outside knowledge — the skill's never-fabricate rule applied at
the one stage where a model could plausibly "remember" a patent.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel

from app.core.config import settings
from app.core.llm_client import llm_structured
from app.services.billing.usage_ledger import usage_context

if TYPE_CHECKING:  # runtime never constructs one here — it only reads attributes
    from app.services.clearance.uspto_client import AppRecord

logger = structlog.get_logger()

RISK_TIERS = ("GREEN", "YELLOW", "RED")

# Claims text is pasted into the prompt, so it needs a ceiling. Independent
# claims come first in a claim set, and 24k characters is roughly 40 claims —
# past any independent claim that matters. Truncation is flagged in the prompt
# so the model never treats a cut-off claim as a complete one.
MAX_CLAIMS_CHARS = 24_000


class ClaimReading(BaseModel):
    claim_requirements: str  # what the independent claims REQUIRE, paraphrased
    differences: str  # elements the founder's item does not share
    risk: str  # GREEN | YELLOW | RED
    rationale: str  # one sentence


_PROMPT = """You are reading a patent reference's claims against an item a founder \
described, for a clearance report.

THE FOUNDER'S ITEM:
{item}

THE REFERENCE (metadata from the USPTO record):
- Number: {number}
- Title: {title}
- Assignee: {assignee}
- Filed: {filed}
- Status: {status}

THE REFERENCE'S CLAIMS (text fetched from the USPTO — the ONLY claim text you may \
rely on{truncation_note}):
{claims_text}

RULES
- Work only from the claim text above and the metadata block. You have no other
  knowledge of this reference; anything you "remember" about it is fabrication.
- Independent claims are the ones that matter: a claim that does not reference
  another claim. Dependent claims only narrow them.
- A claim covers the item only if the item has EVERY required element of that
  claim. A missing element means that claim does not cover it.

Return JSON with exactly these fields:
- "claim_requirements": a paraphrase of what the independent claim(s) REQUIRE —
  every required element, as a compact list in prose.
- "differences": the required elements the founder's item, as described, does NOT
  share. These are the design-around room. Empty string only if the item appears
  to have every element.
- "risk": one of:
  - "GREEN" — the independent claims do not plausibly cover the item as described,
    or this reference is dead (abandoned/expired: still prior art, but it blocks
    nothing).
  - "YELLOW" — a live reference with conceptual overlap; differences exist but a
    claim-level review by counsel is warranted.
  - "RED" — a live reference whose independent claims appear to read on the item
    as described (the item appears to have every required element).
- "rationale": ONE sentence saying why, naming the deciding element(s).

No commentary outside the JSON."""


def _normalize_risk(risk: str, rationale: str) -> tuple[str, str]:
    """Clamp the model's risk to the three tiers; unknown becomes YELLOW.

    YELLOW, not GREEN: an unparseable tier means the reading could not be
    trusted, and the honest default for an unread live reference is "counsel
    should look", never "clear".
    """
    cleaned = (risk or "").strip().upper()
    if cleaned in RISK_TIERS:
        return cleaned, rationale
    logger.warning("claim_reading_risk_unrecognized", returned=risk[:40])
    return "YELLOW", (
        f"{rationale} [risk tier returned as {risk!r} was not one of "
        "GREEN/YELLOW/RED; treated as YELLOW]"
    ).strip()


async def read_claims(
    item: str,
    ref: AppRecord,
    claims_text: str,
    *,
    organization_id: str | None = None,
) -> ClaimReading:
    """One main-model read of a reference's independent claims against the item.

    Attributed to the cost ledger as `ip_clearance_claim_reading`.
    """
    truncated = len(claims_text) > MAX_CLAIMS_CHARS
    text = claims_text[:MAX_CLAIMS_CHARS]
    truncation_note = (
        "; the text was truncated at a length cap, so treat any final "
        "incomplete claim as unreadable rather than complete"
        if truncated
        else ""
    )

    with usage_context("ip_clearance_claim_reading", organization_id=organization_id):
        raw = await llm_structured(
            messages=[
                {
                    "role": "user",
                    "content": _PROMPT.format(
                        item=item,
                        number=ref.grant_number or ref.publication_number or ref.app_number,
                        title=ref.title or "(no title in record)",
                        assignee=ref.assignee or "(not stated)",
                        filed=ref.filed or "(not stated)",
                        status=ref.status or "(not stated)",
                        truncation_note=truncation_note,
                        claims_text=text,
                    ),
                }
            ],
            schema=ClaimReading,
            model=f"{settings.llm_provider}/{settings.llm_model}",
        )

    risk, rationale = _normalize_risk(raw.risk, raw.rationale)
    reading = ClaimReading(
        claim_requirements=raw.claim_requirements.strip(),
        differences=raw.differences.strip(),
        risk=risk,
        rationale=rationale.strip(),
    )
    logger.info(
        "claim_reference_read",
        app_number=ref.app_number,
        risk=reading.risk,
        claims_chars=len(claims_text),
        truncated=truncated,
    )
    return reading
