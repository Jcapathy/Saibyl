# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# compute_snapshot(simulation_id, round_number) -> VisualizerSnapshot
# ─────────────────────────────────────────────────────────
from __future__ import annotations

from uuid import UUID

import structlog

from app.core.database import get_supabase_admin
from app.services.streaming.event_schema import (
    HeatmapCell,
    PersonaActivityBucket,
    PlatformActivitySummary,
    VisualizerSnapshot,
)

logger = structlog.get_logger()


async def compute_snapshot(simulation_id: UUID, round_number: int) -> VisualizerSnapshot:
    """Compute a full visualizer snapshot after a round completes."""
    admin = get_supabase_admin()
    sim_id = str(simulation_id)

    # Fetch all events up to this round
    events = admin.table("simulation_events").select("*").eq(
        "simulation_id", sim_id
    ).lte("round_number", round_number).execute().data

    # Fetch agents for persona type mapping
    agents = admin.table("simulation_agents").select(
        "id, username, profile, platform"
    ).eq("simulation_id", sim_id).execute().data

    agent_map = {}
    for a in agents:
        agent_map[a["id"]] = {
            "username": a["username"],
            "persona_type": (a.get("profile") or {}).get("persona_type", "unknown"),
            "pack_id": (a.get("profile") or {}).get("pack_id", ""),
            "platform": a.get("platform", "unknown"),
        }

    # Compute persona activity buckets
    persona_data: dict[tuple[str, str], dict] = {}  # (persona_type, platform) -> stats
    for e in events:
        info = agent_map.get(e.get("agent_id"), {})
        key = (info.get("persona_type", "unknown"), e.get("platform", "unknown"))
        bucket = persona_data.setdefault(key, {
            "posts": 0, "comments": 0, "sentiments": [], "content": "",
        })
        if e["event_type"] == "post":
            bucket["posts"] += 1
            if not bucket["content"]:
                bucket["content"] = (e.get("content") or "")[:100]
        elif e["event_type"] == "comment":
            bucket["comments"] += 1
        sent = (e.get("metadata") or {}).get("sentiment")
        if sent is not None:
            bucket["sentiments"].append(float(sent))

    persona_activity = []
    for (ptype, platform), data in persona_data.items():
        sents = data["sentiments"]
        persona_activity.append(PersonaActivityBucket(
            persona_type=ptype,
            pack_id="",
            platform=platform,
            post_count=data["posts"],
            comment_count=data["comments"],
            avg_sentiment=sum(sents) / len(sents) if sents else 0.0,
            top_content_snippet=data["content"],
        ))

    # Compute platform summaries
    platform_data: dict[str, dict] = {}
    for e in events:
        p = e.get("platform", "unknown")
        pd = platform_data.setdefault(p, {
            "agents": set(), "posts": 0, "comments": 0, "sentiments": [], "topics": [],
        })
        if e.get("agent_id"):
            pd["agents"].add(e["agent_id"])
        if e["event_type"] == "post":
            pd["posts"] += 1
        elif e["event_type"] == "comment":
            pd["comments"] += 1
        sent = (e.get("metadata") or {}).get("sentiment")
        if sent is not None:
            pd["sentiments"].append(float(sent))

    platform_summary = []
    for platform, data in platform_data.items():
        sents = data["sentiments"]
        platform_summary.append(PlatformActivitySummary(
            platform=platform,
            active_agent_count=len(data["agents"]),
            total_posts=data["posts"],
            total_comments=data["comments"],
            avg_sentiment=sum(sents) / len(sents) if sents else 0.0,
            trending_topics=data["topics"][:5],
        ))

    # Compute heatmap (persona x platform)
    heatmap = []
    max_activity = max(
        (d["posts"] + d["comments"] for d in persona_data.values()), default=1
    ) or 1
    for (ptype, platform), data in persona_data.items():
        activity = data["posts"] + data["comments"]
        sents = data["sentiments"]
        heatmap.append(HeatmapCell(
            persona_type=ptype,
            platform=platform,
            intensity=min(1.0, activity / max_activity),
            sentiment=sum(sents) / len(sents) if sents else 0.0,
        ))

    # Sentiment timeline (avg per round)
    by_round: dict[int, list[float]] = {}
    for e in events:
        rn = e.get("round_number", 0)
        sent = (e.get("metadata") or {}).get("sentiment")
        if sent is not None:
            by_round.setdefault(rn, []).append(float(sent))
    sentiment_timeline = [
        sum(v) / len(v) for _, v in sorted(by_round.items())
    ]

    # Top viral posts
    post_engagement: dict[str, dict] = {}
    for e in events:
        if e["event_type"] == "post":
            post_engagement[e["id"]] = {
                "id": e["id"], "content": (e.get("content") or "")[:150],
                "platform": e.get("platform"), "engagement": 0,
            }
        elif e["event_type"] in ("comment", "react"):
            target = (e.get("metadata") or {}).get("post_id")
            if target and target in post_engagement:
                post_engagement[target]["engagement"] += 1

    viral = sorted(post_engagement.values(), key=lambda x: x["engagement"], reverse=True)[:3]

    unique_agents = {e.get("agent_id") for e in events if e.get("agent_id")}

    return VisualizerSnapshot(
        simulation_id=sim_id,
        round_number=round_number,
        total_events=len(events),
        persona_activity=persona_activity,
        platform_summary=platform_summary,
        heatmap=heatmap,
        sentiment_timeline=sentiment_timeline,
        viral_posts=viral,
        active_agent_count=len(unique_agents),
    )
