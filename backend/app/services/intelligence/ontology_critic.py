# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# critique_ontology(ontology_id, document_sample) -> OntologyCritique
# apply_critique(ontology_id, critique) -> dict
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import json
from uuid import UUID

import structlog
from pydantic import BaseModel, Field

from app.core.database import get_supabase_admin
from app.core.llm_client import llm_structured
from app.services.engine.ontology_generator import refine_ontology

logger = structlog.get_logger()

CRITIQUE_PROMPT = """\
You are an expert ontology reviewer. Analyse the following ontology and a sample \
of the source documents it was derived from.

Ontology (JSON):
{ontology_json}

Document sample:
{document_sample}

Produce a thorough critique as JSON with these fields:
- entity_type_issues: list of problems with existing entity types
- relationship_issues: list of problems with existing relationships
- missing_types: entity or relationship types that should be added
- suggestions: actionable improvement suggestions
- overall_score: a float between 0 and 1 (1 = perfect)
"""


class OntologyCritique(BaseModel):
    entity_type_issues: list[str] = Field(default_factory=list)
    relationship_issues: list[str] = Field(default_factory=list)
    missing_types: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    overall_score: float = Field(ge=0, le=1)


async def critique_ontology(
    ontology_id: UUID,
    document_sample: str,
) -> OntologyCritique:
    """Generate a structured critique of an ontology against source documents."""
    admin = get_supabase_admin()

    ontology = (
        admin.table("ontologies")
        .select("entity_types, relationship_types")
        .eq("id", str(ontology_id))
        .single()
        .execute()
    )
    data = ontology.data
    ontology_json = {
        "entity_types": data["entity_types"],
        "relationship_types": data["relationship_types"],
    }

    prompt = CRITIQUE_PROMPT.format(
        ontology_json=json.dumps(ontology_json, indent=2),
        document_sample=document_sample[:6000],
    )

    critique = await llm_structured(
        messages=[{"role": "user", "content": prompt}],
        schema=OntologyCritique,
    )

    logger.info(
        "ontology_critiqued",
        ontology_id=str(ontology_id),
        overall_score=critique.overall_score,
        issues=len(critique.entity_type_issues) + len(critique.relationship_issues),
    )
    return critique


async def apply_critique(ontology_id: UUID, critique: OntologyCritique) -> dict:
    """Apply a critique by calling refine_ontology with formatted feedback."""
    feedback_parts: list[str] = []

    if critique.entity_type_issues:
        feedback_parts.append(
            "Entity type issues:\n- " + "\n- ".join(critique.entity_type_issues)
        )
    if critique.relationship_issues:
        feedback_parts.append(
            "Relationship issues:\n- " + "\n- ".join(critique.relationship_issues)
        )
    if critique.missing_types:
        feedback_parts.append(
            "Missing types to add:\n- " + "\n- ".join(critique.missing_types)
        )
    if critique.suggestions:
        feedback_parts.append(
            "Suggestions:\n- " + "\n- ".join(critique.suggestions)
        )

    feedback = "\n\n".join(feedback_parts)

    logger.info(
        "applying_ontology_critique",
        ontology_id=str(ontology_id),
        feedback_length=len(feedback),
    )

    result = await refine_ontology(ontology_id, feedback)
    return result
