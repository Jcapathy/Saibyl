# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# insight_forge(graph_id, query, ...) -> InsightResult
# panorama_search(graph_id, category) -> PanoramaResult
# quick_search(graph_id, query, limit) -> list[SearchResult]
# simulation_analytics(simulation_id, analysis_type, ...) -> AnalyticsResult
# agent_interview_tool(simulation_id, prompt, ...) -> list[InterviewResponse]
# ─────────────────────────────────────────────────────────
from __future__ import annotations

from typing import Literal
from uuid import UUID

import structlog
from pydantic import BaseModel

from app.core.database import get_supabase_admin
from app.services.engine.knowledge_graph_builder import get_all_edges, get_all_nodes, search_graph
from app.services.engine.personas.interview_engine import (
    InterviewResponse,
    interview_all,
    interview_by_persona_type,
)

logger = structlog.get_logger()


# ── Result models ────────────────────────────────────────

class InsightResult(BaseModel):
    query: str
    entities: list[dict]
    relationships: list[dict]
    facts: list[str]
    total_results: int


class PanoramaResult(BaseModel):
    category: str
    node_count: int
    edge_count: int
    entity_summaries: list[dict]
    relationship_summaries: list[dict]


class SearchResult(BaseModel):
    name: str
    summary: str
    labels: list[str]
    score: float


class AnalyticsResult(BaseModel):
    analysis_type: str
    variant: str
    data: dict
    summary: str


# ── Tool 1: InsightForge ─────────────────────────────────

async def insight_forge(
    graph_id: str,
    query: str,
    entity_types: list[str] | None = None,
    include_relationships: bool = True,
    depth: int = 2,
) -> InsightResult:
    """Deep semantic search of knowledge graph with relationship traversal."""
    nodes = await search_graph(UUID(graph_id), query, limit=depth * 10)

    # Filter by entity types if specified
    if entity_types:
        nodes = [n for n in nodes if any(t in n.labels for t in entity_types)]

    entities = [{"name": n.name, "summary": n.summary, "labels": n.labels} for n in nodes]
    relationships = []
    facts = []

    if include_relationships:
        edges = await get_all_edges(UUID(graph_id))
        node_uuids = {n.uuid for n in nodes}
        for edge in edges:
            if edge.source_uuid in node_uuids or edge.target_uuid in node_uuids:
                relationships.append({
                    "type": edge.relationship_type,
                    "source": edge.source_uuid,
                    "target": edge.target_uuid,
                    "facts": edge.facts,
                })
                facts.extend(edge.facts)

    return InsightResult(
        query=query,
        entities=entities,
        relationships=relationships,
        facts=facts,
        total_results=len(entities),
    )


# ── Tool 2: PanoramaSearch ───────────────────────────────

async def panorama_search(
    graph_id: str,
    category: Literal["all", "active", "historical", "entities", "relationships"] = "all",
) -> PanoramaResult:
    """Breadth-first retrieval of all entities and edges."""
    nodes = await get_all_nodes(UUID(graph_id))
    edges = await get_all_edges(UUID(graph_id))

    entity_summaries = [
        {"name": n.name, "summary": n.summary, "labels": n.labels}
        for n in nodes
    ]
    relationship_summaries = [
        {"type": e.relationship_type, "facts": e.facts, "expired": e.is_expired}
        for e in edges
    ]

    if category == "entities":
        relationship_summaries = []
    elif category == "relationships":
        entity_summaries = []
    elif category == "active":
        relationship_summaries = [r for r in relationship_summaries if not r["expired"]]
    elif category == "historical":
        relationship_summaries = [r for r in relationship_summaries if r["expired"]]

    return PanoramaResult(
        category=category,
        node_count=len(entity_summaries),
        edge_count=len(relationship_summaries),
        entity_summaries=entity_summaries,
        relationship_summaries=relationship_summaries,
    )


# ── Tool 3: QuickSearch ──────────────────────────────────

async def quick_search(
    graph_id: str,
    query: str,
    limit: int = 10,
) -> list[SearchResult]:
    """Fast keyword + semantic search for specific facts."""
    nodes = await search_graph(UUID(graph_id), query, limit=limit)
    return [
        SearchResult(
            name=n.name,
            summary=n.summary,
            labels=n.labels,
            score=1.0 / (i + 1),  # rank-based score
        )
        for i, n in enumerate(nodes)
    ]


# ── Tool 4: SimulationAnalytics ──────────────────────────

async def simulation_analytics(
    simulation_id: UUID,
    analysis_type: Literal[
        "top_posts",
        "sentiment_over_time",
        "viral_moments",
        "agent_activity",
        "platform_comparison",
        "persona_breakdown",
        "ab_comparison",
    ],
    variant: str = "a",
    platform: str | None = None,
) -> AnalyticsResult:
    """Analyze simulation event data."""
    admin = get_supabase_admin()
    sim_id = str(simulation_id)

    # Base query
    query = admin.table("simulation_events").select("*").eq("simulation_id", sim_id)
    if variant != "all":
        query = query.eq("variant", variant)
    if platform:
        query = query.eq("platform", platform)
    events = query.order("created_at").execute().data

    data: dict = {}
    summary = ""

    if analysis_type == "top_posts":
        posts = [e for e in events if e["event_type"] == "post"]
        # Count comments per post
        post_engagement: dict[str, int] = {}
        for e in events:
            if e["event_type"] in ("comment", "react") and e.get("metadata", {}).get("post_id"):
                pid = e["metadata"]["post_id"]
                post_engagement[pid] = post_engagement.get(pid, 0) + 1
        top = sorted(posts, key=lambda p: post_engagement.get(p["id"], 0), reverse=True)[:10]
        data = {"posts": [{"id": p["id"], "content": p.get("content", "")[:200],
                           "engagement": post_engagement.get(p["id"], 0)} for p in top]}
        summary = f"Top {len(top)} posts by engagement out of {len(posts)} total"

    elif analysis_type == "sentiment_over_time":
        by_round: dict[int, list] = {}
        for e in events:
            rn = e.get("round_number", 0)
            sent = (e.get("metadata") or {}).get("sentiment", 0)
            by_round.setdefault(rn, []).append(sent)
        curve = {r: sum(v) / len(v) if v else 0 for r, v in sorted(by_round.items())}
        data = {"sentiment_curve": curve}
        summary = f"Sentiment tracked across {len(curve)} rounds"

    elif analysis_type == "viral_moments":
        posts = [e for e in events if e["event_type"] == "post"]
        viral = [p for p in posts if (p.get("metadata") or {}).get("viral", False)]
        data = {"viral_posts": [{"content": p.get("content", "")[:200],
                                 "round": p.get("round_number")} for p in viral[:10]]}
        summary = f"{len(viral)} viral moments detected"

    elif analysis_type == "agent_activity":
        by_agent: dict[str, int] = {}
        for e in events:
            uid = e.get("agent_id", "unknown")
            by_agent[uid] = by_agent.get(uid, 0) + 1
        top_agents = sorted(by_agent.items(), key=lambda x: x[1], reverse=True)[:20]
        data = {"agent_activity": [{"agent_id": a, "events": c} for a, c in top_agents]}
        summary = f"{len(by_agent)} unique agents, top agent has {top_agents[0][1] if top_agents else 0} events"

    elif analysis_type == "platform_comparison":
        by_platform: dict[str, int] = {}
        for e in events:
            p = e.get("platform", "unknown")
            by_platform[p] = by_platform.get(p, 0) + 1
        data = {"platform_events": by_platform}
        summary = f"Events across {len(by_platform)} platforms"

    elif analysis_type == "persona_breakdown":
        # Need to join with agents
        agents = admin.table("simulation_agents").select("id, profile").eq(
            "simulation_id", sim_id).execute().data
        agent_types = {a["id"]: (a.get("profile") or {}).get("persona_type", "unknown") for a in agents}
        by_type: dict[str, int] = {}
        for e in events:
            ptype = agent_types.get(e.get("agent_id"), "unknown")
            by_type[ptype] = by_type.get(ptype, 0) + 1
        data = {"persona_events": by_type}
        summary = f"{len(by_type)} persona types active"

    elif analysis_type == "ab_comparison":
        variant_a = [e for e in events if e.get("variant") == "a"]
        variant_b_events = admin.table("simulation_events").select("*").eq(
            "simulation_id", sim_id).eq("variant", "b").execute().data
        data = {
            "variant_a": {"total_events": len(variant_a),
                          "posts": len([e for e in variant_a if e["event_type"] == "post"]),
                          "comments": len([e for e in variant_a if e["event_type"] == "comment"])},
            "variant_b": {"total_events": len(variant_b_events),
                          "posts": len([e for e in variant_b_events if e["event_type"] == "post"]),
                          "comments": len([e for e in variant_b_events if e["event_type"] == "comment"])},
        }
        summary = f"A: {data['variant_a']['total_events']} events, B: {data['variant_b']['total_events']} events"

    return AnalyticsResult(
        analysis_type=analysis_type,
        variant=variant,
        data=data,
        summary=summary,
    )


# ── Tool 5: AgentInterview ───────────────────────────────

async def agent_interview_tool(
    simulation_id: UUID,
    prompt: str,
    agent_filter: dict | None = None,
    sample_size: int = 5,
    variant: str = "a",
) -> list[InterviewResponse]:
    """Query simulation agents for their perspective."""
    if agent_filter and "persona_type" in agent_filter:
        responses = await interview_by_persona_type(
            simulation_id, agent_filter["persona_type"], prompt
        )
    else:
        responses = await interview_all(simulation_id, prompt)

    # Sample down to requested size
    if len(responses) > sample_size:
        import random
        responses = random.sample(responses, sample_size)

    return responses
