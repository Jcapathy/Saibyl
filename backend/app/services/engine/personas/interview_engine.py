# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# interview_agent(simulation_id, agent_id, prompt) -> InterviewResponse
# interview_batch(simulation_id, agent_ids, prompt) -> list[InterviewResponse]
# interview_all(simulation_id, prompt) -> list[InterviewResponse]
# interview_by_persona_type(simulation_id, persona_type, prompt) -> list[InterviewResponse]
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import structlog
from pydantic import BaseModel

from app.core.database import get_supabase_admin
from app.core.llm_client import llm_complete

logger = structlog.get_logger()

MAX_CONCURRENT_INTERVIEWS = 5


class InterviewResponse(BaseModel):
    agent_id: UUID
    agent_username: str
    persona_type: str
    prompt: str
    response: str
    sentiment_score: float
    created_at: datetime


INTERVIEW_PROMPT = """You are role-playing as {display_name}, a {persona_type}.

Profile:
- Age: {age}, Gender: {gender}, Country: {country}
- Profession: {profession}
- MBTI: {mbti}, Political lean: {political_lean}
- Bio: {bio}
- Backstory: {backstory}
- Interests: {interests}

Recent activity context:
{recent_events}

Stay fully in character. Answer the following question from your perspective:

{user_prompt}"""

SENTIMENT_PROMPT = """Rate the sentiment of this text on a scale from -1.0 (very negative) to 1.0 (very positive).
Return ONLY a single number.

Text: {text}"""


async def _get_agent_context(agent: dict, simulation_id: UUID | str) -> str:
    """Build context string from agent's recent simulation events."""
    admin = get_supabase_admin()
    events = (
        admin.table("simulation_events")
        .select("event_type, content, created_at")
        .eq("simulation_id", str(simulation_id))
        .eq("agent_id", agent["id"])
        .order("created_at", desc=True)
        .limit(10)
        .execute()
    ).data

    if not events:
        return "No recent activity."

    lines = []
    for e in events:
        lines.append(f"[{e['event_type']}] {e.get('content', '')[:200]}")
    return "\n".join(lines)


async def _run_interview(
    agent: dict,
    simulation_id: UUID | str,
    user_prompt: str,
    semaphore: asyncio.Semaphore,
) -> InterviewResponse:
    """Run a single agent interview."""
    profile = agent.get("profile", {})
    context = await _get_agent_context(agent, simulation_id)

    interests = profile.get("interests", [])
    if isinstance(interests, list):
        interests_str = ", ".join(str(i) for i in interests)
    else:
        interests_str = str(interests) if interests else ""

    prompt = INTERVIEW_PROMPT.format(
        display_name=profile.get("display_name", agent.get("entity_name", "")),
        persona_type=profile.get("persona_type", ""),
        age=profile.get("age", "unknown"),
        gender=profile.get("gender", "unknown"),
        country=profile.get("country", "unknown"),
        profession=profile.get("profession", "unknown"),
        mbti=profile.get("mbti", "unknown"),
        political_lean=profile.get("political_lean", "moderate"),
        bio=profile.get("bio", ""),
        backstory=profile.get("backstory", ""),
        interests=interests_str,
        recent_events=context,
        user_prompt=user_prompt,
    )

    async with semaphore:
        response_text = await llm_complete(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
        )

    # Quick sentiment estimation
    try:
        sent_prompt = SENTIMENT_PROMPT.format(text=response_text[:500])
        sent_raw = await llm_complete(
            messages=[{"role": "user", "content": sent_prompt}],
            max_tokens=10,
        )
        sentiment = float(sent_raw.strip())
        sentiment = max(-1.0, min(1.0, sentiment))
    except (ValueError, TypeError):
        sentiment = 0.0

    return InterviewResponse(
        agent_id=agent["id"],
        agent_username=agent.get("username", ""),
        persona_type=profile.get("persona_type", ""),
        prompt=user_prompt,
        response=response_text,
        sentiment_score=sentiment,
        created_at=datetime.now(UTC),
    )


async def interview_agent(
    simulation_id: UUID | str, agent_id: UUID | str, prompt: str
) -> InterviewResponse:
    """Interview a single agent."""
    admin = get_supabase_admin()
    agent = (
        admin.table("simulation_agents")
        .select("*")
        .eq("id", str(agent_id))
        .single()
        .execute()
    ).data

    semaphore = asyncio.Semaphore(1)
    return await _run_interview(agent, simulation_id, prompt, semaphore)


async def interview_batch(
    simulation_id: UUID | str, agent_ids: list[UUID | str], prompt: str
) -> list[InterviewResponse]:
    """Interview multiple specific agents in parallel."""
    admin = get_supabase_admin()
    agents = (
        admin.table("simulation_agents")
        .select("*")
        .in_("id", [str(a) for a in agent_ids])
        .execute()
    ).data

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_INTERVIEWS)
    tasks = [_run_interview(a, simulation_id, prompt, semaphore) for a in agents]
    return await asyncio.gather(*tasks)


async def interview_all(
    simulation_id: UUID | str, prompt: str
) -> list[InterviewResponse]:
    """Interview all agents in a simulation."""
    admin = get_supabase_admin()
    agents = (
        admin.table("simulation_agents")
        .select("*")
        .eq("simulation_id", str(simulation_id))
        .execute()
    ).data

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_INTERVIEWS)
    tasks = [_run_interview(a, simulation_id, prompt, semaphore) for a in agents]
    return await asyncio.gather(*tasks)


async def interview_by_persona_type(
    simulation_id: UUID | str, persona_type: str, prompt: str
) -> list[InterviewResponse]:
    """Interview all agents of a specific persona type."""
    admin = get_supabase_admin()
    agents = (
        admin.table("simulation_agents")
        .select("*")
        .eq("simulation_id", str(simulation_id))
        .execute()
    ).data

    # Filter by persona type in the profile JSONB
    matching = [
        a for a in agents
        if a.get("profile", {}).get("persona_type", "").lower() == persona_type.lower()
    ]

    if not matching:
        logger.warning("no_matching_agents", persona_type=persona_type)
        return []

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_INTERVIEWS)
    tasks = [_run_interview(a, simulation_id, prompt, semaphore) for a in matching]
    return await asyncio.gather(*tasks)
