# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# build_graph(project_id: UUID, ontology_id: UUID) -> dict
# get_graph_stats(graph_id: UUID) -> GraphStats
# search_graph(graph_id: UUID, query: str, limit: int = 10) -> list[GraphNode]
# get_all_nodes(graph_id: UUID) -> list[GraphNode]
# get_all_edges(graph_id: UUID) -> list[GraphEdge]
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import UUID

import structlog
from pydantic import BaseModel

from app.core.config import settings
from app.core.database import get_supabase_admin
from app.services.engine.document_processor import chunk_text, get_project_text

logger = structlog.get_logger()

BATCH_SIZE = 10
POLL_INTERVAL = 3  # seconds


class GraphNode(BaseModel):
    uuid: str
    name: str
    labels: list[str]
    summary: str
    attributes: dict
    created_at: datetime | None = None


class GraphEdge(BaseModel):
    uuid: str
    source_uuid: str
    target_uuid: str
    relationship_type: str
    facts: list[str]
    valid_at: datetime | None = None
    invalid_at: datetime | None = None
    is_expired: bool = False


class GraphStats(BaseModel):
    graph_id: str
    node_count: int
    edge_count: int
    build_status: str


def _get_zep_client():
    """Lazy-load Zep client."""
    from zep_cloud import AsyncZep

    return AsyncZep(api_key=settings.zep_api_key)


async def build_graph(project_id: UUID, ontology_id: UUID) -> dict:
    """Build a knowledge graph in Zep Cloud from project documents."""
    admin = get_supabase_admin()

    # Fetch ontology (validates it exists)
    admin.table("ontologies").select("id").eq("id", str(ontology_id)).single().execute()

    # Create or update knowledge_graphs record
    kg_result = (
        admin.table("knowledge_graphs")
        .insert({
            "project_id": str(project_id),
            "organization_id": (
                admin.table("projects")
                .select("organization_id")
                .eq("id", str(project_id))
                .single()
                .execute()
            ).data["organization_id"],
            "build_status": "building",
        })
        .execute()
    )
    kg_id = kg_result.data[0]["id"]

    try:
        zep = _get_zep_client()

        # Get project text and chunk it
        text = await get_project_text(project_id)
        chunks = chunk_text(text, chunk_size=1000, overlap=100)

        # Create a Zep graph for this project
        graph_id = f"saibyl-{project_id}"

        # Process chunks in batches
        total_processed = 0
        for i in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[i : i + BATCH_SIZE]
            for chunk in batch:
                await zep.graph.add(
                    group_id=graph_id,
                    type="text",
                    data=chunk,
                )
            total_processed += len(batch)
            logger.info(
                "graph_batch_ingested",
                graph_id=graph_id,
                processed=total_processed,
                total=len(chunks),
            )

        # Poll for completion
        for _ in range(120):  # max 6 minutes
            await asyncio.sleep(POLL_INTERVAL)
            try:
                await zep.graph.search(group_id=graph_id, query="*", limit=1)
                break
            except Exception:
                continue

        # Get final stats
        nodes_result = await zep.graph.search(group_id=graph_id, query="*", limit=1000)
        node_count = len(nodes_result) if nodes_result else 0

        # Update knowledge_graphs record
        admin.table("knowledge_graphs").update({
            "zep_graph_id": graph_id,
            "node_count": node_count,
            "edge_count": 0,  # updated when edges are queryable
            "build_status": "complete",
            "built_at": datetime.now().isoformat(),
        }).eq("id", kg_id).execute()

        logger.info("graph_built", graph_id=graph_id, nodes=node_count)
        return admin.table("knowledge_graphs").select("*").eq("id", kg_id).single().execute().data

    except Exception as e:
        admin.table("knowledge_graphs").update({
            "build_status": "failed",
        }).eq("id", kg_id).execute()
        logger.error("graph_build_failed", error=str(e))
        raise


async def get_graph_stats(graph_id: UUID) -> GraphStats:
    """Get node/edge counts for a knowledge graph."""
    admin = get_supabase_admin()
    result = (
        admin.table("knowledge_graphs")
        .select("zep_graph_id, node_count, edge_count, build_status")
        .eq("id", str(graph_id))
        .single()
        .execute()
    )
    data = result.data
    return GraphStats(
        graph_id=data["zep_graph_id"] or str(graph_id),
        node_count=data["node_count"],
        edge_count=data["edge_count"],
        build_status=data["build_status"],
    )


async def search_graph(
    graph_id: UUID, query: str, limit: int = 10
) -> list[GraphNode]:
    """Search the knowledge graph by natural language query."""
    admin = get_supabase_admin()
    kg = (
        admin.table("knowledge_graphs")
        .select("zep_graph_id")
        .eq("id", str(graph_id))
        .single()
        .execute()
    )
    zep_id = kg.data["zep_graph_id"]
    if not zep_id:
        return []

    zep = _get_zep_client()
    results = await zep.graph.search(group_id=zep_id, query=query, limit=limit)

    return [
        GraphNode(
            uuid=str(r.uuid) if hasattr(r, "uuid") else "",
            name=getattr(r, "name", ""),
            labels=getattr(r, "labels", []),
            summary=getattr(r, "summary", ""),
            attributes=getattr(r, "attributes", {}),
        )
        for r in (results or [])
    ]


async def get_all_nodes(graph_id: UUID) -> list[GraphNode]:
    """Retrieve all nodes from the knowledge graph."""
    return await search_graph(graph_id, query="*", limit=1000)


async def get_all_edges(graph_id: UUID) -> list[GraphEdge]:
    """Retrieve all edges from the knowledge graph."""
    admin = get_supabase_admin()
    kg = (
        admin.table("knowledge_graphs")
        .select("zep_graph_id")
        .eq("id", str(graph_id))
        .single()
        .execute()
    )
    zep_id = kg.data["zep_graph_id"]
    if not zep_id:
        return []

    zep = _get_zep_client()
    try:
        edges = await zep.graph.search(group_id=zep_id, query="*", limit=1000)
        return [
            GraphEdge(
                uuid=str(getattr(e, "uuid", "")),
                source_uuid=str(getattr(e, "source_uuid", "")),
                target_uuid=str(getattr(e, "target_uuid", "")),
                relationship_type=getattr(e, "relationship_type", ""),
                facts=getattr(e, "facts", []),
            )
            for e in (edges or [])
        ]
    except Exception:
        return []
