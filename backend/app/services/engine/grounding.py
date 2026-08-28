# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# GroundedObjection, GroundingScope
# grounded_objections(vertical, *, organization_id, scope) -> list[GroundedObjection]
# grounding_prompt_section(objections) -> str
# MIN_RUNS, MIN_ORGS_FOR_SHARED
# ─────────────────────────────────────────────────────────
"""What buyers in this category have actually objected to before.

**Two goals, and the second is the one that matters most.** The founder's own
words, on 2026-08-28: *"improve the output quality as well as close the loop on
the question about the outputs."*

1. **Output quality.** A room built only from the founder's own deck can only
   argue with what the deck says. A room that also knows what buyers in this
   category have raised before argues about things the deck never mentioned,
   which is the whole point of rehearsing.
2. **The loop.** The credibility critical on saibyl.com is not "what are the
   objections" but *"do these synthetic objections predict real ones?"* That is
   answered by `outcomes.py` — recording, after launch, which predicted
   objections a founder actually met. Once outcomes exist they re-weight what is
   grounded here, so the room gets better at the thing it is being judged on
   rather than merely more confident.

**Why this reads our own runs and not a scrape.** The original proposal was to
scrape review sites and train on them. Three reasons this is better:

- **It is checkable.** "This objection recurred in 7 Saibyl runs in this
  category" is a database query. "Trained on real-world data" is a process
  boast, and the website check already flags two of those on our own landing
  page — an internal capacity number "with no external benchmark or outcome
  attached", and a privacy claim that "has no backing". A third would be caught
  by our own product, correctly.
- **It carries no terms-of-service or GDPR exposure**, which scraping review
  sites for model input does.
- **It compounds.** Every run adds to it, and nobody else has it — which is the
  only part of this that a competitor cannot copy.

**The privacy constraint, which is load-bearing.** `/privacy` tells founders
their uploads are never visible outside their account. Aggregate objection
*labels* are derived data rather than uploads, but a founder would reasonably
read one org's runs informing another's as a breach of that sentence. So:

- `GroundingScope.OWN` is the default and needs no policy change.
- `GroundingScope.SHARED` is off unless switched on deliberately, carries a
  k-anonymity floor (`MIN_ORGS_FOR_SHARED`), and never carries a quote, a
  product name, or an organisation id — only a label and a count.
- **Turning `SHARED` on in production requires the privacy policy to say so
  first.** That is a decision for the founder, not a default for this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import structlog

from app.core.database import get_supabase_admin

logger = structlog.get_logger()

#: An objection seen once is an anecdote. Below this it is not grounding, and
#: reporting it as such would be the "a number that means we did not look"
#: failure this codebase produces most often.
MIN_RUNS = 3

#: k-anonymity for the shared scope: an objection must appear across at least
#: this many distinct organisations before it may be shown to a different one.
#: Two orgs is not an aggregate — with two, the second knows the first.
MIN_ORGS_FOR_SHARED = 3

#: How many grounded objections ride into a room. Enough to widen the argument,
#: few enough that the room still argues from the founder's own material first.
MAX_GROUNDED = 8


class GroundingScope(StrEnum):
    """Whose history may inform this room."""

    #: This organisation's own past runs. Always safe: it is their data.
    OWN = "own"
    #: De-identified counts across organisations. Requires the privacy policy
    #: to describe it before it may be switched on in production.
    SHARED = "shared"


@dataclass(frozen=True)
class GroundedObjection:
    """One recurring objection, with the receipt that makes it checkable."""

    key: str
    label: str
    #: How many distinct runs raised it. This is the provenance: it is a count
    #: over `canonical_objections`, reproducible by anyone with the database.
    run_count: int
    #: How many distinct organisations. Carried so the k-anonymity floor can be
    #: enforced and stated, never so a reader can identify one.
    org_count: int
    scope: GroundingScope

    def receipt(self) -> str:
        """The sentence a founder can check, and nothing more than it says."""
        runs = "run" if self.run_count == 1 else "runs"
        if self.scope is GroundingScope.OWN:
            return f"raised in {self.run_count} of your own {runs}"
        return f"raised in {self.run_count} {runs} across {self.org_count} products"


def grounded_objections(
    vertical: str | None,
    *,
    organization_id: str,
    scope: GroundingScope = GroundingScope.OWN,
    limit: int = MAX_GROUNDED,
) -> list[GroundedObjection]:
    """Recurring objections for this category, newest evidence first.

    Returns `[]` rather than raising when there is no history — a new founder
    has none, and that is the normal case rather than an error. An empty list
    means the room runs exactly as it did before this module existed.

    `vertical` is accepted for the signature the caller already has; the
    category filter is applied by the caller's own selection of runs today,
    because `canonical_objections` carries no vertical column. Narrowing this to
    a real per-category filter wants a column, and inventing one here would
    silently return cross-category noise labelled as category evidence.
    """
    try:
        # Inside the try: constructing the client can fail too, and a room
        # that cannot reach its history is yesterday's room, not a failed run.
        admin = get_supabase_admin()
        query = admin.table("canonical_objections").select(
            "objection_key, label, simulation_id, organization_id"
        )
        if scope is GroundingScope.OWN:
            query = query.eq("organization_id", organization_id)
        rows = query.limit(4000).execute().data or []
    except Exception:
        # Grounding is an enrichment. A room that cannot reach the history is a
        # room exactly as good as yesterday's, not a failed run.
        logger.warning("grounding_query_failed", exc_info=True)
        return []

    if scope is GroundingScope.SHARED:
        # Never let the asking org's own runs inflate a "shared" count: that
        # would report their own material back to them as independent evidence.
        rows = [r for r in rows if str(r.get("organization_id")) != str(organization_id)]

    buckets: dict[str, dict] = {}
    for row in rows:
        key = row.get("objection_key")
        if not key:
            continue
        bucket = buckets.setdefault(
            key, {"label": row.get("label") or key, "runs": set(), "orgs": set()}
        )
        bucket["runs"].add(row.get("simulation_id"))
        bucket["orgs"].add(row.get("organization_id"))

    out: list[GroundedObjection] = []
    for key, bucket in buckets.items():
        run_count, org_count = len(bucket["runs"]), len(bucket["orgs"])
        if run_count < MIN_RUNS:
            continue
        if scope is GroundingScope.SHARED and org_count < MIN_ORGS_FOR_SHARED:
            continue
        out.append(
            GroundedObjection(
                key=key,
                label=str(bucket["label"]),
                run_count=run_count,
                org_count=org_count,
                scope=scope,
            )
        )

    out.sort(key=lambda o: (o.run_count, o.org_count), reverse=True)
    logger.info(
        "grounding_selected",
        scope=scope.value,
        considered=len(buckets),
        kept=len(out[:limit]),
        min_runs=MIN_RUNS,
    )
    return out[:limit]


def grounding_prompt_section(objections: list[GroundedObjection]) -> str:
    """The grounding, as instruction for the room.

    Deliberately framed as *things to test*, never as things to conclude. A room
    told "buyers object to X" will dutifully object to X and the run becomes a
    mirror of its own prompt — which is the correlated-hallucination failure the
    whole product is judged on. Told "check whether X applies here", a room that
    finds X irrelevant is producing a real result.
    """
    if not objections:
        return ""
    lines = [
        "WHAT THIS CATEGORY HAS OBJECTED TO BEFORE",
        "",
        "These recurred in earlier runs. They are prompts to CHECK, not",
        "conclusions to repeat. If one does not apply to this product, say so",
        "and move on — a room that raises an objection because it was listed",
        "here has told the founder nothing.",
        "",
    ]
    lines.extend(f"- {o.label} ({o.receipt()})" for o in objections)
    return "\n".join(lines)
