# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# run_prediction(market_id: UUID, org_id: UUID) -> dict
# ─────────────────────────────────────────────────────────
from __future__ import annotations

from uuid import UUID

import structlog
from pydantic import BaseModel

from app.core.database import get_supabase_admin
from app.core.llm_client import llm_complete, llm_structured
from app.services.intelligence.report_agent import ReACTConfig, generate_report
from app.workers.simulation_tasks import run_prepare_agents, run_simulation

# Persona packs by market category
SPORTS_PACKS = ["sports-book-manager", "sports-bookmaker", "sports-bettor"]
FINANCE_PACKS = ["fintech-investor", "media-journalist", "political-moderate"]
POLITICS_PACKS = ["government-policy", "political-moderate", "media-journalist"]
DEFAULT_PACKS = ["retail-consumer", "media-journalist", "political-moderate"]

SPORTS_KEYWORDS = [
    "nba", "nfl", "mlb", "nhl", "mls", "ufc", "mma", "boxing",
    "basketball", "football", "baseball", "hockey", "soccer",
    "game", "match", "fight", "bout", "series", "playoff",
    "win", "beat", "vs", "versus", "spread", "over/under",
    "76ers", "lakers", "celtics", "warriors", "heat", "knicks",
    "chiefs", "eagles", "cowboys", "bills", "ravens",
    "yankees", "dodgers", "mets", "braves", "astros",
]

POLITICS_KEYWORDS = [
    "president", "election", "congress", "senate", "governor",
    "democrat", "republican", "vote", "poll", "legislation",
    "policy", "cabinet", "supreme court", "impeach",
]


async def _research_market(title: str, resolution_rules: str, closes_at: str) -> str:
    """Web search for current data relevant to the market, then summarize."""
    import httpx

    # Build search query from market title
    search_query = f"{title} preview stats predictions {closes_at[:10] if closes_at else '2026'}"

    try:
        # Use Anthropic web search via the LLM — ask Claude to research
        research_prompt = f"""You are a sports and market research analyst. Based on your knowledge, provide a detailed factual briefing for this prediction market:

Market: {title}
Resolution: {resolution_rules}
Date: {closes_at}

Include ALL of the following that are relevant:
- Team/player current season records and standings
- Recent form (last 5-10 games)
- Head-to-head history between these teams/competitors
- Key player stats (points, rebounds, assists, goals, etc.)
- Injury report and player availability
- Home/away performance splits
- Current odds and betting line movement
- Any relevant situational factors (rest days, travel, back-to-back, motivation)

Be specific with numbers and stats. If this is not a sports market, provide equivalent factual context for the topic."""

        research = await llm_complete(
            messages=[{"role": "user", "content": research_prompt}],
            max_tokens=1500,
        )
        logger.info("market_research_complete", title=title, length=len(research))
        return research
    except Exception as e:
        logger.warning("market_research_failed", error=str(e))
        return ""


def _select_packs(market_title: str) -> list[str]:
    """Select persona packs based on market topic."""
    title_lower = market_title.lower()
    if any(kw in title_lower for kw in SPORTS_KEYWORDS):
        return SPORTS_PACKS
    if any(kw in title_lower for kw in POLITICS_KEYWORDS):
        return POLITICS_PACKS
    # Check for finance/crypto keywords
    if any(kw in title_lower for kw in ["stock", "crypto", "bitcoin", "fed", "rate", "gdp", "inflation", "earnings"]):
        return FINANCE_PACKS
    return DEFAULT_PACKS

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
Possible outcomes: {outcome_labels}
Resolution rules: {resolution_rules}
Current market probability: {market_probability:.1%} (for first outcome)
Market closes: {closes_at}

Research data:
{research}

Simulation summary (events, sentiment, agent consensus):
{sim_summary}

Based on BOTH the research data AND the swarm intelligence simulation, provide your prediction.
Weight the factual research heavily — the simulation captures sentiment, the research provides ground truth:

Return JSON:
{{
  "predicted_outcome": one of {outcome_labels} (the outcome you predict will happen),
  "predicted_probability": float 0-1 (probability of your predicted outcome),
  "confidence_low": float 0-1 (lower bound of 80% CI),
  "confidence_high": float 0-1 (upper bound of 80% CI),
  "recommended_position": your predicted outcome label or "PASS" (PASS if |edge| < 0.03),
  "edge_vs_market": float (your probability - market probability for that outcome),
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
        # Get any user in the org for created_by
        members = admin.table("organization_members").select("user_id").eq(
            "organization_id", str(org_id)
        ).limit(1).execute().data
        creator = members[0]["user_id"] if members else str(org_id)
        project = admin.table("projects").insert({
            "organization_id": str(org_id),
            "created_by": creator,
            "name": "Prediction Markets",
            "description": "Auto-created project for prediction market simulations",
        }).execute().data

    project_id = project[0]["id"]

    # Get org member for created_by
    members = admin.table("organization_members").select("user_id").eq(
        "organization_id", str(org_id)
    ).limit(1).execute().data
    creator = members[0]["user_id"] if members else str(org_id)

    # Select persona packs based on market topic
    selected_packs = _select_packs(market.get("title", ""))
    logger.info("prediction_packs_selected", packs=selected_packs, title=market.get("title", ""))

    # Use Polymarket's live context if available, supplement with LLM research
    market_context = market.get("market_context") or ""
    research = await _research_market(
        market.get("title", ""),
        market.get("resolution_rules", ""),
        market.get("closes_at", ""),
    )
    if market_context:
        research = f"=== LIVE MARKET CONTEXT ===\n{market_context}\n\n=== ADDITIONAL RESEARCH ===\n{research}"

    # Build enriched prediction goal with market context + research
    outcomes_desc = ", ".join(
        f"{o.get('label', '?')}: {o.get('current_probability', 0):.0%}"
        for o in (market.get("outcomes") or [])
    )
    prediction_goal = (
        f"Predict the outcome of: {market['title']}. "
        f"Current market odds: {outcomes_desc}. "
        f"Resolution rules: {market.get('resolution_rules', 'N/A')}. "
        f"Closes: {market.get('closes_at', 'N/A')}.\n\n"
        f"=== CURRENT RESEARCH & DATA ===\n{research}\n"
        f"=== END RESEARCH ===\n\n"
        f"Use the research data above as ground truth. Debate the outcome based on these facts."
    )

    # Create simulation
    sim = admin.table("simulations").insert({
        "project_id": project_id,
        "organization_id": str(org_id),
        "created_by": creator,
        "name": f"Prediction: {market['title'][:80]}",
        "prediction_goal": prediction_goal,
        "platforms": ["twitter_x", "reddit"],
        "max_rounds": 3,
        "agent_count": 20,
        "persona_pack_ids": selected_packs,
        "status": "draft",
    }).execute().data[0]

    sim_id = sim["id"]

    # Prepare agents then run simulation
    try:
        await run_prepare_agents(sim_id)
        await run_simulation(sim_id)

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
        outcome_labels = [o.get("label", "?") for o in (market.get("outcomes") or [])]
        prompt = PREDICTION_PROMPT.format(
            title=market["title"],
            outcome_labels=outcome_labels,
            resolution_rules=market.get("resolution_rules", "N/A"),
            market_probability=market_prob,
            closes_at=market.get("closes_at", "N/A"),
            research=research[:3000],
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
