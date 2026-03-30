from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_org
from app.core.database import get_supabase_admin
from app.core.llm_client import llm_complete

log = structlog.get_logger()

router = APIRouter(tags=["comparison"])


class CompareSimsBody(BaseModel):
    simulation_ids: list[str]


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

        events = admin.table("simulation_events").select(
            "metadata, event_type, platform"
        ).eq("simulation_id", sim_id).execute().data or []

        sentiments = []
        platforms = {}
        event_types = {}
        for e in events:
            meta = e.get("metadata") or {}
            s = meta.get("sentiment")
            if s is not None:
                sentiments.append(float(s))
            p = e.get("platform", "unknown")
            platforms[p] = platforms.get(p, 0) + 1
            et = e.get("event_type", "unknown")
            event_types[et] = event_types.get(et, 0) + 1

        avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0.0
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
            "avg_sentiment": round(avg_sentiment, 3),
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
        f"Avg sentiment: {s['avg_sentiment']}\n"
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
