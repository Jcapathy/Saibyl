# PUBLIC INTERFACE
# ---------------------------------------------------------
# GET  /api/score/{simulation_id}  -> ScoreResponse
# POST /api/score/batch            -> list[ScoreResponse]
# ---------------------------------------------------------
from __future__ import annotations

import math
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.core.auth import verify_api_key
from app.core.database import get_supabase, get_supabase_admin
from app.core.llm_client import llm_complete

logger = structlog.get_logger()

router = APIRouter(tags=["score"])

# ---------------------------------------------------------------------------
# Auth: accept either JWT bearer token OR X-API-Key header
# ---------------------------------------------------------------------------
_bearer = HTTPBearer(auto_error=False)
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def _get_org_id(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
    api_key: str | None = Security(_api_key_header),
) -> str:
    """Resolve org_id from whichever credential is present."""
    if api_key:
        key_auth = await verify_api_key(api_key)
        return key_auth["org_id"]
    if credentials:
        supabase = get_supabase()
        try:
            response = supabase.auth.get_user(token)
            if response.user is None:
                raise HTTPException(status_code=401, detail="Invalid token")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=401, detail="Authentication failed")

        admin = get_supabase_admin()
        result = (
            admin.table("organization_members")
            .select("organization_id")
            .eq("user_id", response.user.id)
            .limit(1)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=403, detail="No organization found")
        return result.data[0]["organization_id"]

    raise HTTPException(status_code=401, detail="Provide X-API-Key or Bearer token")


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------
class ScoreResponse(BaseModel):
    score: int
    summary: str
    simulation_id: str
    category: str
    headline: str
    generated_at: str


class BatchRequest(BaseModel):
    simulation_ids: list[str]


# ---------------------------------------------------------------------------
# Core scoring logic
# ---------------------------------------------------------------------------
async def _compute_score(simulation_id: str, org_id: str) -> ScoreResponse:
    admin = get_supabase_admin()

    # Verify simulation exists and belongs to org
    sim = (
        admin.table("simulations")
        .select("id, name, prediction_goal, status")
        .eq("id", simulation_id)
        .eq("organization_id", org_id)
        .limit(1)
        .execute()
    ).data
    if not sim:
        raise HTTPException(status_code=404, detail=f"Simulation {simulation_id} not found")
    sim = sim[0]

    if sim["status"] not in ("completed", "running"):
        raise HTTPException(
            status_code=422,
            detail=f"Simulation is '{sim['status']}' — score requires 'running' or 'completed'",
        )

    # Pull sentiment values from events
    events = (
        admin.table("simulation_events")
        .select("metadata")
        .eq("simulation_id", simulation_id)
        .execute()
    ).data or []

    sentiments: list[float] = []
    for e in events:
        meta = e.get("metadata") or {}
        s = meta.get("sentiment")
        if s is not None:
            sentiments.append(float(s))

    if not sentiments:
        raise HTTPException(
            status_code=422,
            detail="No sentiment data available for this simulation",
        )

    # Score = normalized average sentiment (0-100)
    avg_sentiment = sum(sentiments) / len(sentiments)
    score = round((avg_sentiment + 1) / 2 * 100)

    # Controversy boost: high std_dev means polarized = viral
    if len(sentiments) >= 2:
        variance = sum((s - avg_sentiment) ** 2 for s in sentiments) / len(sentiments)
        std_dev = math.sqrt(variance)
        if std_dev > 0.5:
            score = min(100, score + 10)
    score = max(0, min(100, score))

    # Categorize
    if score >= 80:
        category = "strong_positive"
    elif score >= 60:
        category = "positive"
    elif score >= 40:
        category = "mixed"
    elif score >= 20:
        category = "negative"
    else:
        category = "strong_negative"

    # Generate punchy summary via LLM (fast model)
    headline = sim.get("name") or sim.get("prediction_goal", "Simulation")
    summary_prompt = (
        f"You are a concise intelligence analyst. Write a 1-2 sentence summary of this prediction result.\n\n"
        f"Topic: {headline}\n"
        f"Goal: {sim.get('prediction_goal', 'N/A')}\n"
        f"Saibyl Score: {score}/100 ({category.replace('_', ' ')})\n"
        f"Average sentiment: {avg_sentiment:.2f} (range -1 to 1)\n"
        f"Sample size: {len(sentiments)} agent responses\n\n"
        f"Write in punchy, shareable language. No hedging. State the verdict clearly."
    )

    try:
        summary = await llm_complete(
            messages=[{"role": "user", "content": summary_prompt}],
            model=f"anthropic/claude-haiku-4-5-20251001",
            max_tokens=150,
            temperature=0.6,
        )
        summary = summary.strip().strip('"')
    except Exception as exc:
        logger.warning("score_summary_llm_failed", error=str(exc), simulation_id=simulation_id)
        summary = f"Saibyl Score {score}/100 — {category.replace('_', ' ')} outlook based on {len(sentiments)} agent responses."

    generated_at = datetime.now(UTC).isoformat()

    logger.info(
        "saibyl_score_computed",
        simulation_id=simulation_id,
        score=score,
        category=category,
        n_sentiments=len(sentiments),
    )

    return ScoreResponse(
        score=score,
        summary=summary,
        simulation_id=simulation_id,
        category=category,
        headline=headline,
        generated_at=generated_at,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/{simulation_id}")
async def get_score(simulation_id: str, org_id: str = Depends(_get_org_id)) -> ScoreResponse:
    """Compute and return the Saibyl Score for a single simulation."""
    return await _compute_score(simulation_id, org_id)


@router.post("/batch")
async def get_scores_batch(
    body: BatchRequest, org_id: str = Depends(_get_org_id),
) -> list[ScoreResponse]:
    """Compute Saibyl Scores for multiple simulations."""
    if len(body.simulation_ids) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 simulations per batch request")

    results: list[ScoreResponse] = []
    errors: list[dict] = []

    for sim_id in body.simulation_ids:
        try:
            result = await _compute_score(sim_id, org_id)
            results.append(result)
        except HTTPException as exc:
            errors.append({"simulation_id": sim_id, "error": exc.detail})
            logger.warning("batch_score_skip", simulation_id=sim_id, error=exc.detail)

    if not results and errors:
        raise HTTPException(status_code=422, detail={"message": "All simulations failed", "errors": errors})

    return results
