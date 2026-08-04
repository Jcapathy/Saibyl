from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_org
from app.core.database import fetch_all, get_supabase_admin
from app.core.llm_client import llm_complete
from app.services.intelligence.analysis_data import load_run_data, mean_interval

log = structlog.get_logger()

router = APIRouter(tags=["comparison"])


class CompareSimsBody(BaseModel):
    simulation_ids: list[str]


def _sentiment_line(summary: dict) -> str:
    """How a run's sentiment is described to the comparison writer.

    A run with nothing measured is stated as unmeasured rather than shown as
    0.0, which the writer would otherwise compare against its neighbours as a
    neutral result.
    """
    if summary["avg_sentiment"] is None:
        return "Avg sentiment: not measured for this run — do not compare it on sentiment"
    return (
        f"Avg sentiment: {summary['avg_sentiment']} "
        f"(95% CI {summary['sentiment_ci'][0]} to {summary['sentiment_ci'][1]}, "
        f"{summary['sentiment_agents']} agents)"
    )


@router.post("")
async def compare_simulations(body: CompareSimsBody, auth: dict = Depends(get_current_org)):
    """Compare multiple simulation runs side-by-side with LLM analysis."""
    if len(body.simulation_ids) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 simulations to compare")
    if len(body.simulation_ids) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 simulations per comparison")

    admin = get_supabase_admin()
    summaries = []

    for sim_id in body.simulation_ids:
        sim = admin.table("simulations").select("*").eq(
            "id", sim_id
        ).eq("organization_id", auth["org_id"]).single().execute()
        if not sim.data:
            raise HTTPException(status_code=404, detail=f"Simulation {sim_id} not found")

        # Structural counts cover every event, measured or not. Paged, because
        # a comparison computed over the first 1,000 events of a 2,500-event run
        # looks entirely plausible and is wrong.
        events = fetch_all(
            admin.table("simulation_events")
            .select("event_type, platform")
            .eq("simulation_id", sim_id)
            .order("id")
        )

        platforms: dict[str, int] = {}
        event_types: dict[str, int] = {}
        for e in events:
            p = e.get("platform", "unknown")
            platforms[p] = platforms.get(p, 0) + 1
            et = e.get("event_type", "unknown")
            event_types[et] = event_types.get(et, 0) + 1

        # Sentiment comes from measured valence, not from the metadata
        # "sentiment" key — that key was written by the drift formula removed in
        # Phase 1 and is absent on every run measured since, so this comparison
        # reported 0.0 for both runs and called them identical.
        valence = mean_interval(load_run_data(sim_id).scored_events)
        if valence.n == 0:
            log.warning("comparison_run_unmeasured", simulation_id=sim_id)

        top_platform = max(platforms, key=platforms.get) if platforms else "N/A"

        packs = sim.data.get("persona_pack_ids") or []

        summaries.append({
            "simulation_id": sim_id,
            "name": sim.data.get("name", ""),
            "prediction_goal": sim.data.get("prediction_goal", ""),
            "persona_packs": packs,
            "platforms": sim.data.get("platforms", []),
            "agent_count": sim.data.get("agent_count", 0),
            "max_rounds": sim.data.get("max_rounds", 0),
            "total_events": len(events),
            # None, never 0.0: an unmeasured run has no sentiment, and a zero
            # renders as a neutral verdict nobody measured.
            "avg_sentiment": valence.mean if valence.n else None,
            "sentiment_ci": [valence.lower, valence.upper] if valence.n else None,
            "sentiment_agents": valence.n,
            "top_platform": top_platform,
            "event_breakdown": event_types,
            "platform_breakdown": platforms,
        })

    # LLM comparison analysis
    sim_descriptions = "\n\n".join(
        f"Simulation: {s['name']}\n"
        f"Persona packs: {', '.join(s['persona_packs'])}\n"
        f"Platforms: {', '.join(s['platforms'])}\n"
        f"Agents: {s['agent_count']}, Rounds: {s['max_rounds']}\n"
        f"Total events: {s['total_events']}\n"
        f"{_sentiment_line(s)}\n"
        f"Top platform: {s['top_platform']}\n"
        f"Events by type: {s['event_breakdown']}"
        for s in summaries
    )

    analysis = await llm_complete(
        messages=[{"role": "user", "content": f"""Compare these simulation runs and provide insights:

{sim_descriptions}

Write a 3-4 paragraph analysis covering:
1. Key differences in outcomes between the simulations
2. How persona pack choices affected sentiment and engagement
3. Which simulation configuration produced the most realistic/useful results
4. Recommendations for future simulation design"""}],
        max_tokens=800,
    )

    return {
        "simulations": summaries,
        "analysis": analysis,
    }
