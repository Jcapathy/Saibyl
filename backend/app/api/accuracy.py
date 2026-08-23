from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_org, require_can_spend
from app.core.database import get_supabase_admin, maybe_one
from app.core.llm_client import llm_complete
from app.services.intelligence.analysis_data import load_run_data, mean_interval

log = structlog.get_logger()

router = APIRouter(tags=["prediction-accuracy"])


class SubmitOutcomeBody(BaseModel):
    simulation_id: str
    actual_sentiment: float | None = None
    actual_engagement: str | None = None
    actual_outcomes: dict | None = None
    notes: str | None = None


@router.post("/score")
async def score_prediction(body: SubmitOutcomeBody, auth: dict = Depends(require_can_spend)):
    """Submit actual outcomes and get an accuracy score for a simulation's predictions.

    **Gated**: this calls `llm_complete` and writes a `prediction_accuracy` row,
    and it took `get_current_org` alone. It reaches no `deduct_credits`, so the
    ledger scan could not see it — the same blind spot that left `/api/compare`
    and `/api/persona-packs/custom` open. A viewer's grant is to read, and this
    both spends and writes.
    """
    log.info("score_prediction", simulation_id=body.simulation_id, org_id=auth["org_id"])
    admin = get_supabase_admin()

    # Scoring a prediction against an outcome nobody reported is not scoring
    # anything. This used to substitute 0.0, which stored — and told the
    # customer — that the run had been validated against a neutral result.
    if body.actual_sentiment is None:
        raise HTTPException(
            status_code=400,
            detail="actual_sentiment is required to score a prediction against an outcome",
        )

    # Get simulation
    sim = maybe_one(
        admin.table("simulations")
        .select("*")
        .eq("id", body.simulation_id)
        .eq("organization_id", auth["org_id"])
    )
    if not sim.data:
        raise HTTPException(status_code=404, detail="Simulation not found")

    # What the run actually predicted, read from measured valence. The metadata
    # "sentiment" key this used to average was written by the drift formula
    # removed in Phase 1, and an unmeasured run fell through to 0.0 — scoring a
    # prediction the simulation never made.
    run = load_run_data(body.simulation_id)
    predicted = mean_interval(run.scored_events)
    if predicted.n == 0:
        log.warning(
            "accuracy_no_measured_sentiment",
            simulation_id=body.simulation_id,
            events_total=run.events_total,
            events_measured=run.events_measured,
        )
        raise HTTPException(
            status_code=422,
            detail=(
                "This simulation has no measured sentiment, so there is no "
                "prediction to score against the reported outcome."
            ),
        )

    predicted_sentiment = predicted.mean
    actual_sentiment = body.actual_sentiment

    # Calculate accuracy: 1.0 - normalized distance between predicted and actual
    sentiment_distance = abs(predicted_sentiment - actual_sentiment) / 2.0  # scale is -1 to 1, range is 2
    accuracy_score = round(max(0.0, 1.0 - sentiment_distance), 3)

    # Get report for context
    report = (
        admin.table("reports")
        .select("markdown_content")
        .eq("simulation_id", body.simulation_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    ).data

    report_summary = ""
    if report:
        report_summary = (report[0].get("markdown_content") or "")[:3000]

    # LLM analysis of prediction accuracy
    analysis_prompt = f"""Compare a simulation's predictions against actual outcomes.

Simulation: {sim.data.get('name', '')}
Prediction goal: {sim.data.get('prediction_goal', '')}

Predicted average sentiment: {predicted_sentiment:.3f} \
(95% CI {predicted.lower:.3f} to {predicted.upper:.3f}, from {predicted.n} agents)
Actual sentiment reported: {actual_sentiment:.3f}
Accuracy score: {accuracy_score:.1%}

Report summary:
{report_summary[:2000]}

User notes on actual outcome: {body.notes or 'None provided'}
Additional outcomes: {body.actual_outcomes or {}}

Write a 2-3 paragraph analysis of:
1. How accurate the simulation's predictions were
2. What the simulation got right and wrong
3. What factors the simulation may have missed"""

    analysis = await llm_complete(
        messages=[{"role": "user", "content": analysis_prompt}],
        max_tokens=600,
    )

    # Store the accuracy record
    admin.table("prediction_accuracy").insert({
        "simulation_id": body.simulation_id,
        "organization_id": auth["org_id"],
        "created_by": auth["user"]["id"],
        "predicted_sentiment": predicted_sentiment,
        "actual_sentiment": actual_sentiment,
        "predicted_engagement": body.actual_engagement,
        "actual_engagement": body.actual_engagement,
        "accuracy_score": accuracy_score,
        "notes": body.notes,
        "actual_outcomes": body.actual_outcomes or {},
    }).execute()

    return {
        "accuracy_score": accuracy_score,
        "predicted_sentiment": round(predicted_sentiment, 3),
        "actual_sentiment": round(actual_sentiment, 3),
        "analysis": analysis,
    }


@router.get("/{simulation_id}")
async def get_accuracy(simulation_id: str, auth: dict = Depends(get_current_org)):
    """Get accuracy records for a simulation."""
    admin = get_supabase_admin()
    result = (
        admin.table("prediction_accuracy")
        .select("*")
        .eq("simulation_id", simulation_id)
        .eq("organization_id", auth["org_id"])
        .order("created_at", desc=True)
        .execute()
    )
    return result.data
