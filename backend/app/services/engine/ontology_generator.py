# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# generate_ontology(project_id: UUID) -> Ontology
# refine_ontology(ontology_id: UUID, feedback: str) -> Ontology
# approve_ontology(ontology_id: UUID, user_id: UUID) -> Ontology
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

import structlog
from pydantic import BaseModel

from app.core.database import get_supabase_admin
from app.core.llm_client import llm_structured
from app.services.engine.document_processor import get_project_text

logger = structlog.get_logger()

MAX_LLM_CHARS = 50_000


class EntityType(BaseModel):
    name: str
    description: str
    example_entities: list[str]
    social_media_suitable: bool


class RelationshipType(BaseModel):
    name: str
    source_entity_type: str
    target_entity_type: str
    description: str


class OntologySchema(BaseModel):
    entity_types: list[EntityType]
    relationship_types: list[RelationshipType]


GENERATION_PROMPT = """You are an ontology extraction specialist. Analyze the following document text and extract a structured ontology suitable for social media simulation.

Requirements:
- Entity types should represent people, organizations, concepts, products, or groups that would interact on social media
- Mark each entity type as social_media_suitable=true if it represents something that would post/comment on social platforms
- Relationship types should capture how entities relate (influences, competes_with, supports, etc.)
- Include 2-5 example entities for each type
- Focus on entities and relationships that would produce interesting simulation dynamics

Document text (first {char_limit} chars):
---
{text}
---

Return a JSON object with keys "entity_types" and "relationship_types" matching this schema:
- entity_types: [{{"name": str, "description": str, "example_entities": [str], "social_media_suitable": bool}}]
- relationship_types: [{{"name": str, "source_entity_type": str, "target_entity_type": str, "description": str}}]"""

CRITIQUE_PROMPT = """You are an ontology quality reviewer. Critique the following ontology for use in social media simulation.

Current ontology:
{ontology_json}

Check for:
1. Are entity types distinct enough? Merge any that overlap.
2. Are relationships bidirectional where they should be?
3. Are there enough social_media_suitable entities for a meaningful simulation?
4. Are example entities realistic and diverse?
5. Are there missing entity types or relationships that would improve simulation quality?

Return an improved JSON object with the same schema. Make concrete improvements, don't just describe what could be better."""

FEEDBACK_PROMPT = """You are an ontology refinement specialist. The user has reviewed the ontology and provided feedback.

Current ontology:
{ontology_json}

User feedback:
{feedback}

Incorporate the user's feedback and return an improved JSON object with the same schema:
- entity_types: [{{"name": str, "description": str, "example_entities": [str], "social_media_suitable": bool}}]
- relationship_types: [{{"name": str, "source_entity_type": str, "target_entity_type": str, "description": str}}]"""


def _generate_pydantic_code(ontology: OntologySchema) -> str:
    """Auto-generate Pydantic validation models from entity types."""
    lines = [
        "from pydantic import BaseModel",
        "",
    ]
    for et in ontology.entity_types:
        class_name = et.name.replace(" ", "").replace("-", "").replace("_", "")
        lines.append(f"class {class_name}Entity(BaseModel):")
        lines.append(f'    """Generated from ontology: {et.description}"""')
        lines.append("    name: str")
        lines.append(f"    entity_type: str = {et.name!r}")
        lines.append(f"    social_media_suitable: bool = {et.social_media_suitable}")
        lines.append("    attributes: dict = {}")
        lines.append("")
    return "\n".join(lines)


async def generate_ontology(project_id: UUID) -> dict:
    """Generate initial ontology from project documents (Pass 1 + Pass 2)."""
    admin = get_supabase_admin()

    # Get project text
    text = await get_project_text(project_id)
    if not text.strip():
        raise ValueError("No processed documents found for this project")

    # Fetch org_id from project
    project = (
        admin.table("projects")
        .select("organization_id")
        .eq("id", str(project_id))
        .single()
        .execute()
    )
    org_id = project.data["organization_id"]

    # Pass 1: Generate with full model
    truncated = text[:MAX_LLM_CHARS]
    prompt = GENERATION_PROMPT.format(text=truncated, char_limit=MAX_LLM_CHARS)

    ontology = await llm_structured(
        messages=[{"role": "user", "content": prompt}],
        schema=OntologySchema,
        model=None,  # uses default full model via llm_structured override below
    )

    # Pass 2: Self-critique with fast model
    critique_prompt = CRITIQUE_PROMPT.format(ontology_json=ontology.model_dump_json(indent=2))
    refined = await llm_structured(
        messages=[{"role": "user", "content": critique_prompt}],
        schema=OntologySchema,
    )

    # Generate Pydantic code
    pydantic_code = _generate_pydantic_code(refined)

    # Store in DB
    result = (
        admin.table("ontologies")
        .insert({
            "project_id": str(project_id),
            "organization_id": org_id,
            "entity_types": json.loads(refined.model_dump_json())["entity_types"],
            "relationship_types": json.loads(refined.model_dump_json())["relationship_types"],
            "pydantic_models": pydantic_code,
            "refinement_round": 2,
        })
        .execute()
    )

    logger.info(
        "ontology_generated",
        project_id=str(project_id),
        entities=len(refined.entity_types),
        relationships=len(refined.relationship_types),
    )
    return result.data[0]


async def refine_ontology(ontology_id: UUID, feedback: str) -> dict:
    """Refine ontology based on user feedback (Pass 3)."""
    admin = get_supabase_admin()

    # Fetch current ontology
    current = (
        admin.table("ontologies")
        .select("*")
        .eq("id", str(ontology_id))
        .single()
        .execute()
    )
    data = current.data
    current_schema = OntologySchema(
        entity_types=data["entity_types"],
        relationship_types=data["relationship_types"],
    )

    # Refine with user feedback using full model
    prompt = FEEDBACK_PROMPT.format(
        ontology_json=current_schema.model_dump_json(indent=2),
        feedback=feedback,
    )
    refined = await llm_structured(
        messages=[{"role": "user", "content": prompt}],
        schema=OntologySchema,
    )

    pydantic_code = _generate_pydantic_code(refined)

    result = (
        admin.table("ontologies")
        .update({
            "entity_types": json.loads(refined.model_dump_json())["entity_types"],
            "relationship_types": json.loads(refined.model_dump_json())["relationship_types"],
            "pydantic_models": pydantic_code,
            "refinement_round": data["refinement_round"] + 1,
        })
        .eq("id", str(ontology_id))
        .execute()
    )

    logger.info("ontology_refined", ontology_id=str(ontology_id), round=data["refinement_round"] + 1)
    return result.data[0]


async def approve_ontology(ontology_id: UUID, user_id: UUID) -> dict:
    """Mark ontology as human-approved."""
    admin = get_supabase_admin()

    result = (
        admin.table("ontologies")
        .update({
            "human_approved": True,
            "approved_by": str(user_id),
            "approved_at": datetime.now(UTC).isoformat(),
        })
        .eq("id", str(ontology_id))
        .execute()
    )

    logger.info("ontology_approved", ontology_id=str(ontology_id), user_id=str(user_id))
    return result.data[0]
