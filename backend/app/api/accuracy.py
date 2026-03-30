from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_org
from app.core.database import get_supabase_admin
from app.core.llm_client import llm_complete

log = structlog.get_logger()

router = APIRouter(tags=["prediction-accuracy"])


class SubmitOutcomeBody(BaseModel):
    simulation_id: str
    actual_sentiment: float | None = None
    actual_engagement: str | None = None
    actual_outcomes: dict | None = None
    notes: str | None = None


class ScoreResponse(BaseModel):
    accuracy_score: float
    predicted_sentiment: float
    actual_sentiment: float
    analysis: str


@router.post("/score")
async def score_prediction(body: SubmitOutcomeBody, auth: dict = Depends(get_current_org)):
    """Submit actual outcomes and get an accuracy score for a simulation's predictions."""
    log.info("score_prediction", simulation_id=body.simulation_id, org_id=auth["org_id"])
    admin = get_supabase_admin()

    # Get simulation
    sim = (
        admin.table("simulations")
        .select("*")
        .eq("id", body.simulation_id)
        .eq("organization_id", auth["org_id"])
        .single()
        .execute()
    )
    if not sim.data:
        raise HTTPException(status_code=404, detail="Simulation not found")

    # Get simulation events to calculate predicted sentiment
    events = (
        admin.table("simulation_events")
        .select("metadata")
        .eq("simulation_id", body.simulation_id)
        .execute()
    ).data or []

    sentiments = []
    for e in events:
        meta = e.get("metadata") or {}
        s = meta.get("sentiment")
        if s is not None:
            sentiments.append(float(s))

    predicted_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0.0
    actual_sentiment = body.actual_sentiment if body.actual_sentiment is not None else 0.0

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

Predicted average sentiment: {predicted_sentiment:.3f}
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
