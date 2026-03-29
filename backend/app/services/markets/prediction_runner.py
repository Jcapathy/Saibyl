# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# run_prediction(market_id: UUID, org_id: UUID) -> dict
# ─────────────────────────────────────────────────────────
from __future__ import annotations

from uuid import UUID

import structlog
from pydantic import BaseModel

from app.core.database import get_supabase_admin
from app.core.llm_client import llm_structured
from app.services.intelligence.report_agent import ReACTConfig, generate_report
from app.services.platforms.simulation_runner import run_simulation

logger = structlog.get_logger()


class PredictionResult(BaseModel):
    predicted_outcome: str
    predicted_probability: float
    confidence_low: float
    confidence_high: float
    recommended_position: str
    edge_vs_market: float
    reasoning_summary: str
    key_drivers: list[str]
    contra_indicators: list[str]


PREDICTION_PROMPT = """Analyze the results of a swarm simulation targeting this prediction market:

Market: {title}
Resolution rules: {resolution_rules}
Current market probability: {market_probability:.1%}
Market closes: {closes_at}

Simulation summary (events, sentiment, agent consensus):
{sim_summary}

Based on the swarm intelligence simulation, provide your prediction:

Return JSON:
{{
  "predicted_outcome": "Yes" or "No",
  "predicted_probability": float 0-1 (your TRUE probability estimate),
  "confidence_low": float 0-1 (lower bound of 80% CI),
  "confidence_high": float 0-1 (upper bound of 80% CI),
  "recommended_position": "YES" or "NO" or "PASS" (PASS if |edge| < 0.03),
  "edge_vs_market": float (your probability - market probability, positive = YES, negative = NO),
  "reasoning_summary": "2-3 sentence summary",
  "key_drivers": ["driver1", "driver2", ...] (top 5),
  "contra_indicators": ["contra1", "contra2", ...] (top 3)
}}"""


async def run_prediction(market_id: UUID, org_id: UUID) -> dict:
    """Run a prediction market simulation and generate prediction."""
    admin = get_supabase_admin()

    market = admin.table("prediction_markets").select("*").eq(
        "id", str(market_id)
    ).single().execute().data

    # Get current market price
    yes_outcome = next(
        (o for o in (market.get("outcomes") or []) if o.get("label", "").lower() == "yes"),
        {"current_probability": 0.5},
    )
    market_prob = yes_outcome.get("current_probability", 0.5)

    # Create a simulation for this prediction
    # Find or create a project for market predictions
    project = admin.table("projects").select("id").eq(
        "organization_id", str(org_id)
    ).eq("name", "Prediction Markets").execute().data

    if not project:
        project = admin.table("projects").insert({
            "organization_id": str(org_id),
            "created_by": str(org_id),  # system-created
            "name": "Prediction Markets",
            "description": "Auto-created project for prediction market simulations",
        }).execute().data

    project_id = project[0]["id"]

    # Create simulation
    sim = admin.table("simulations").insert({
        "project_id": project_id,
        "organization_id": str(org_id),
        "created_by": str(org_id),
        "name": f"Prediction: {market['title'][:80]}",
        "prediction_goal": f"Determine the TRUE probability of: {market['title']}. Resolution: {market.get('resolution_rules', 'N/A')}. Current market: {market_prob:.0%}.",
        "platforms": ["twitter_x", "reddit"],
        "max_rounds": 5,
        "agent_count": 500,
    }).execute().data[0]

    sim_id = sim["id"]

    # Run simulation
    try:
        await run_simulation(UUID(sim_id))

        # Get simulation events summary
        events = admin.table("simulation_events").select(
            "event_type, content, metadata", count="exact"
        ).eq("simulation_id", sim_id).execute()

        sim_summary = f"Total events: {events.count or 0}. "
        posts = [e for e in (events.data or []) if e["event_type"] == "post"]
        sim_summary += f"Posts: {len(posts)}. "
        if posts:
            sentiments = [
                (e.get("metadata") or {}).get("sentiment", 0)
                for e in (events.data or [])
                if (e.get("metadata") or {}).get("sentiment") is not None
            ]
            if sentiments:
                avg_sent = sum(sentiments) / len(sentiments)
                sim_summary += f"Avg sentiment: {avg_sent:.2f}. "

        # Generate prediction via LLM
        prompt = PREDICTION_PROMPT.format(
            title=market["title"],
            resolution_rules=market.get("resolution_rules", "N/A"),
            market_probability=market_prob,
            closes_at=market.get("closes_at", "N/A"),
            sim_summary=sim_summary,
        )

        prediction = await llm_structured(
            messages=[{"role": "user", "content": prompt}],
            schema=PredictionResult,
        )

        # Generate full report
        config = ReACTConfig(evidence_depth="deep", section_count=5)
        report = await generate_report(UUID(sim_id), config)

        # Store prediction
        pred_record = admin.table("market_predictions").insert({
            "organization_id": str(org_id),
            "market_id": str(market_id),
            "simulation_id": sim_id,
            "report_id": report["id"],
            "predicted_outcome": prediction.predicted_outcome,
            "predicted_probability": prediction.predicted_probability,
            "confidence_interval": f"[{prediction.confidence_low},{prediction.confidence_high}]",
            "recommended_position": prediction.recommended_position,
            "edge_vs_market": prediction.edge_vs_market,
            "reasoning_summary": prediction.reasoning_summary,
            "market_price_at_prediction": market_prob,
            "full_report_json": {
                "key_drivers": prediction.key_drivers,
                "contra_indicators": prediction.contra_indicators,
                "sim_events": events.count or 0,
            },
        }).execute().data[0]

        logger.info(
            "prediction_complete",
            market_id=str(market_id),
            predicted=prediction.predicted_probability,
            edge=prediction.edge_vs_market,
            position=prediction.recommended_position,
        )
        return pred_record

    except Exception as e:
        admin.table("simulations").update({"status": "failed"}).eq("id", sim_id).execute()
        logger.error("prediction_failed", market_id=str(market_id), error=str(e))
        raise
