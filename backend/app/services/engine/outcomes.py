# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# OutcomeVerdict, PredictionAccuracy
# record_outcome(...) -> None
# accuracy_for(organization_id=None) -> PredictionAccuracy
# MIN_ANSWERS_TO_REPORT
# ─────────────────────────────────────────────────────────
"""Whether the room was right, measured rather than asserted.

**This module exists to answer one question, and it is the question the company
turns on.** Two independent evaluations of saibyl.com made the same finding
their most severe: nothing on the page shows that synthetic objections predict
real ones. Saibyl's own check calls it a critical — *"the team controls both the
input and the AI output"* — and the outside review called it the elephant in the
room.

No copy change closes that. The sentence that closes it is
*"Saibyl predicted this objection; 17 of 24 real prospects raised it"*, and the
only way to earn that sentence is to ask founders afterwards and count.

**Three rules, and each one exists because the obvious alternative lies:**

1. **Unanswered is not wrong.** `occurred IS NULL` means asked-and-not-yet-
   answered. Counting it as a miss would make accuracy fall every time somebody
   ignored the email, which measures our follow-up rate and calls it prediction
   quality.
2. **Nothing is reported below `MIN_ANSWERS_TO_REPORT`.** An accuracy computed
   from four answers is noise with a decimal point, and putting it on a landing
   page would be precisely the unbacked claim the check already flags us for
   twice.
3. **`accuracy_for` returns `None` rather than 0 when there is nothing to
   report.** A zero that means "we have not measured" is the defect this
   codebase produces more than any other, and this is the one number where it
   would be actively dishonest.
"""
from __future__ import annotations

from dataclasses import dataclass

import structlog

from app.core.database import get_supabase_admin

logger = structlog.get_logger()

#: Below this many answered predictions there is no number worth printing.
#: Chosen to be embarrassing rather than flattering: a founder asking "on how
#: much?" should get an answer that survives being asked twice.
MIN_ANSWERS_TO_REPORT = 30


@dataclass(frozen=True)
class OutcomeVerdict:
    simulation_id: str
    objection_key: str
    occurred: bool | None
    evidence: str | None = None
    observed_count: int | None = None


@dataclass(frozen=True)
class PredictionAccuracy:
    """What we can honestly say about how often the room was right."""

    answered: int
    confirmed: int
    #: `None` until `MIN_ANSWERS_TO_REPORT` answers exist. Not 0.
    rate: float | None
    #: Asked but not yet answered. Reported so the rate is always readable
    #: alongside how much of the asking it rests on.
    pending: int

    @property
    def sentence(self) -> str:
        """The claim, in the only form that is defensible."""
        if self.rate is None:
            return (
                f"Not enough answers yet to state a rate "
                f"({self.answered} of {MIN_ANSWERS_TO_REPORT} needed)."
            )
        return (
            f"{self.confirmed} of {self.answered} predicted objections were "
            f"raised by real buyers ({self.rate:.0%})."
        )


def record_outcome(
    *,
    organization_id: str,
    verdict: OutcomeVerdict,
    answered_by: str | None = None,
) -> None:
    """Store one founder verdict, replacing any earlier one for that objection.

    Upserted on `(simulation_id, objection_key)`: a founder who learns more and
    corrects themselves must not create a second contradictory row, because two
    verdicts for one prediction make the rate unanswerable.
    """
    row = {
        "organization_id": organization_id,
        "simulation_id": verdict.simulation_id,
        "objection_key": verdict.objection_key,
        "occurred": verdict.occurred,
        "evidence": verdict.evidence,
        "observed_count": verdict.observed_count,
        "answered_by": answered_by,
    }
    if verdict.occurred is not None:
        row["answered_at"] = "now()"

    get_supabase_admin().table("objection_outcomes").upsert(
        row, on_conflict="simulation_id,objection_key"
    ).execute()
    logger.info(
        "objection_outcome_recorded",
        organization_id=organization_id,
        simulation_id=verdict.simulation_id,
        objection_key=verdict.objection_key,
        occurred=verdict.occurred,
    )


def accuracy_for(organization_id: str | None = None) -> PredictionAccuracy:
    """How often the room was right — for one org, or across all of them.

    Passing `None` computes the figure we would put on the landing page. It is
    computed from the same rows a founder can see for their own account, so the
    public number and the private one cannot disagree.
    """
    try:
        # Inside the try for the same reason as `grounding`: constructing the
        # client is itself a thing that can fail.
        admin = get_supabase_admin()
        query = admin.table("objection_outcomes").select("occurred")
        if organization_id is not None:
            query = query.eq("organization_id", organization_id)
        rows = query.limit(10000).execute().data or []
    except Exception:
        logger.warning("outcome_query_failed", exc_info=True)
        return PredictionAccuracy(answered=0, confirmed=0, rate=None, pending=0)

    answered = [r for r in rows if r.get("occurred") is not None]
    confirmed = sum(1 for r in answered if r.get("occurred") is True)
    pending = len(rows) - len(answered)

    rate = (
        confirmed / len(answered)
        if len(answered) >= MIN_ANSWERS_TO_REPORT
        else None
    )
    return PredictionAccuracy(
        answered=len(answered), confirmed=confirmed, rate=rate, pending=pending
    )
