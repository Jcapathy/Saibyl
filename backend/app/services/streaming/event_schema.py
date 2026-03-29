from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class PersonaActivityBucket(BaseModel):
    persona_type: str
    pack_id: str
    platform: str
    post_count: int
    comment_count: int
    avg_sentiment: float
    top_content_snippet: str


class PlatformActivitySummary(BaseModel):
    platform: str
    active_agent_count: int
    total_posts: int
    total_comments: int
    avg_sentiment: float
    trending_topics: list[str]


class HeatmapCell(BaseModel):
    persona_type: str
    platform: str
    intensity: float
    sentiment: float


class VisualizerSnapshot(BaseModel):
    simulation_id: str
    round_number: int
    total_events: int
    persona_activity: list[PersonaActivityBucket]
    platform_summary: list[PlatformActivitySummary]
    heatmap: list[HeatmapCell]
    sentiment_timeline: list[float]
    viral_posts: list[dict]
    active_agent_count: int


class SimulationStreamEvent(BaseModel):
    event_type: Literal[
        "agent_post",
        "agent_comment",
        "agent_react",
        "agent_dm",
        "round_complete",
        "simulation_complete",
        "simulation_stopped",
        "simulation_failed",
        "report_section_complete",
        "report_complete",
        "graph_build_progress",
        "agent_prep_progress",
    ]
    simulation_id: str
    timestamp: str
    variant: str = "a"
    round_number: int | None = None
    agent_username: str | None = None
    agent_persona_type: str | None = None
    platform: str | None = None
    content: str | None = None
    sentiment_score: float | None = None
    engagement_count: int | None = None
    visualizer_snapshot: VisualizerSnapshot | None = None
