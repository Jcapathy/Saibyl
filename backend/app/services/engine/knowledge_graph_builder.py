# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# build_graph(project_id: UUID, ontology_id: UUID) -> dict
# get_graph_stats(graph_id: UUID) -> GraphStats
# search_graph(graph_id: UUID, query: str, limit: int = 10) -> list[GraphNode]
# get_all_nodes(graph_id: UUID) -> list[GraphNode]
# get_all_edges(graph_id: UUID) -> list[GraphEdge]
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

import structlog
from pydantic import BaseModel

from app.core.config import settings
from app.core.database import get_supabase_admin
from app.services.engine.document_processor import chunk_text, get_project_text

logger = structlog.get_logger()

BATCH_SIZE = 10


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


# ── LLM entity/relationship extraction ─────────────────

EXTRACT_PROMPT = """\
You are an entity and relationship extractor. Given the following text chunk, \
extract all named entities and the relationships between them.

Return valid JSON with this exact structure:
{
  "entities": [
    {"name": "...", "labels": ["Person", "Organization", ...], "summary": "one-line description", "attributes": {}}
  ],
  "relationships": [
    {"source": "entity name", "target": "entity name", "type": "WORKS_FOR", "facts": ["supporting fact"]}
  ]
}

Rules:
- Entity names must be consistent (same entity = same name)
- Labels should be general categories (Person, Organization, Technology, Concept, Location, Event, etc.)
- Relationship types should be UPPER_SNAKE_CASE
- Only extract what is explicitly stated, do not infer

Text chunk:
---
{chunk}
---"""


async def _extract_entities_and_relationships(chunks: list[str]) -> tuple[list[dict], list[dict]]:
    """Use Claude to extract entities and relationships from text chunks."""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    all_entities: dict[str, dict] = {}  # dedupe by name
    all_relationships: list[dict] = []

    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        for chunk in batch:
            try:
                response = await client.messages.create(
                    model=settings.llm_fast_model,
                    max_tokens=2048,
                    messages=[{"role": "user", "content": EXTRACT_PROMPT.format(chunk=chunk)}],
                )
                text = response.content[0].text
                # Parse JSON from response (handle markdown code blocks)
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0]
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0]
                data = json.loads(text.strip())

                for entity in data.get("entities", []):
                    name = entity["name"]
                    if name in all_entities:
                        # Merge: keep richer version
                        existing = all_entities[name]
                        existing["labels"] = list(set(existing["labels"] + entity.get("labels", [])))
                        existing["attributes"].update(entity.get("attributes", {}))
                    else:
                        all_entities[name] = entity

                all_relationships.extend(data.get("relationships", []))
            except Exception:
                logger.warning("entity_extraction_failed", chunk_index=i)
                continue

        logger.info("extraction_batch_done", processed=min(i + BATCH_SIZE, len(chunks)), total=len(chunks))

    return list(all_entities.values()), all_relationships


# ── Graph storage (Supabase-native) ────────────────────

async def _store_graph(
    kg_id: str,
    entities: list[dict],
    relationships: list[dict],
) -> tuple[int, int]:
    """Store extracted entities and relationships in Supabase graph tables."""
    admin = get_supabase_admin()

    # Insert nodes
    node_rows = []
    name_to_id: dict[str, str] = {}
    for entity in entities:
        row = {
            "knowledge_graph_id": kg_id,
            "name": entity["name"],
            "labels": entity.get("labels", []),
            "summary": entity.get("summary", ""),
            "attributes": entity.get("attributes", {}),
        }
        node_rows.append(row)

    if node_rows:
        result = admin.table("graph_nodes").insert(node_rows).execute()
        for row in result.data:
            name_to_id[row["name"]] = row["id"]

    # Insert edges
    edge_rows = []
    for rel in relationships:
        source_id = name_to_id.get(rel["source"])
        target_id = name_to_id.get(rel["target"])
        if source_id and target_id:
            edge_rows.append({
                "knowledge_graph_id": kg_id,
                "source_node_id": source_id,
                "target_node_id": target_id,
                "relationship_type": rel.get("type", "RELATED_TO"),
                "facts": rel.get("facts", []),
            })

    if edge_rows:
        admin.table("graph_edges").insert(edge_rows).execute()

    return len(node_rows), len(edge_rows)


# ── Public API ──────────────────────────────────────────

async def build_graph(project_id: UUID, ontology_id: UUID) -> dict:
    """Build a knowledge graph from project documents using Claude + Supabase."""
    admin = get_supabase_admin()

    # Fetch ontology (validates it exists)
    admin.table("ontologies").select("id").eq("id", str(ontology_id)).single().execute()

    # Create knowledge_graphs record
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
        # Get project text and chunk it
        text = await get_project_text(project_id)
        chunks = chunk_text(text, chunk_size=1000, overlap=100)

        # Extract entities and relationships with Claude
        entities, relationships = await _extract_entities_and_relationships(chunks)

        # Store in Supabase
        node_count, edge_count = await _store_graph(kg_id, entities, relationships)

        # Update knowledge_graphs record
        admin.table("knowledge_graphs").update({
            "node_count": node_count,
            "edge_count": edge_count,
            "build_status": "complete",
            "built_at": datetime.now().isoformat(),
        }).eq("id", kg_id).execute()

        logger.info("graph_built", kg_id=kg_id, nodes=node_count, edges=edge_count)
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
        .select("id, node_count, edge_count, build_status")
        .eq("id", str(graph_id))
        .single()
        .execute()
    )
    data = result.data
    return GraphStats(
        graph_id=str(data["id"]),
        node_count=data["node_count"],
        edge_count=data["edge_count"],
        build_status=data["build_status"],
    )


async def search_graph(
    graph_id: UUID, query: str, limit: int = 10
) -> list[GraphNode]:
    """Search the knowledge graph by text match against node names/summaries."""
    admin = get_supabase_admin()

    # Full-text search on node name and summary
    results = (
        admin.table("graph_nodes")
        .select("*")
        .eq("knowledge_graph_id", str(graph_id))
        .or_(f"name.ilike.%{query}%,summary.ilike.%{query}%")
        .limit(limit)
        .execute()
    )

    return [
        GraphNode(
            uuid=row["id"],
            name=row["name"],
            labels=row.get("labels", []),
            summary=row.get("summary", ""),
            attributes=row.get("attributes", {}),
            created_at=row.get("created_at"),
        )
        for row in results.data
    ]


async def get_all_nodes(graph_id: UUID) -> list[GraphNode]:
    """Retrieve all nodes from the knowledge graph."""
    admin = get_supabase_admin()
    results = (
        admin.table("graph_nodes")
        .select("*")
        .eq("knowledge_graph_id", str(graph_id))
        .limit(1000)
        .execute()
    )
    return [
        GraphNode(
            uuid=row["id"],
            name=row["name"],
            labels=row.get("labels", []),
            summary=row.get("summary", ""),
            attributes=row.get("attributes", {}),
            created_at=row.get("created_at"),
        )
        for row in results.data
    ]


async def get_all_edges(graph_id: UUID) -> list[GraphEdge]:
    """Retrieve all edges from the knowledge graph."""
    admin = get_supabase_admin()
    results = (
        admin.table("graph_edges")
        .select("*")
        .eq("knowledge_graph_id", str(graph_id))
        .limit(1000)
        .execute()
    )
    return [
        GraphEdge(
            uuid=row["id"],
            source_uuid=row["source_node_id"],
            target_uuid=row["target_node_id"],
            relationship_type=row["relationship_type"],
            facts=row.get("facts", []),
        )
        for row in results.data
    ]
