from __future__ import annotations

import asyncio
import json
import re

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_org
from app.core.database import get_supabase_admin
from app.core.llm_client import llm_complete, _extract_json
from app.services.engine.personas.pack_loader import (
    PersonaPack,
    get_pack,
    list_available_packs,
)

log = structlog.get_logger()

router = APIRouter(tags=["persona-packs"])


class CreateCustomPackBody(BaseModel):
    name: str
    description: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def list_packs(auth: dict = Depends(get_current_org)):
    """List all available persona packs (built-in + org custom)."""
    log.info("list_persona_packs", org_id=auth["org_id"])
    packs = list_available_packs(org_id=auth["org_id"])
    return [p.model_dump() for p in packs]


@router.get("/{pack_id}")
async def get_pack_details(pack_id: str, auth: dict = Depends(get_current_org)):
    """Get details of a specific persona pack."""
    log.info("get_persona_pack", pack_id=pack_id, org_id=auth["org_id"])
    pack = get_pack(pack_id)
    return pack.model_dump()


@router.post("/custom")
async def create_custom_pack(body: CreateCustomPackBody, auth: dict = Depends(get_current_org)):
    """Generate a custom persona pack from a user description using LLM."""
    log.info("create_custom_pack", name=body.name, org_id=auth["org_id"])

    pack_id = re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-")
    pack_id = f"custom-{pack_id}"

    # Check for duplicate
    admin = get_supabase_admin()
    existing = admin.table("custom_persona_packs").select("id").eq(
        "organization_id", auth["org_id"]
    ).eq("pack_id", pack_id).execute()
    if existing.data:
        raise HTTPException(status_code=409, detail=f"Custom pack '{body.name}' already exists")

    prompt = f"""Generate a persona pack for social media simulation based on this description:

Name: {body.name}
Description: {body.description}

Create 3-5 distinct archetypes that represent different behavioral segments within this persona group.
Each archetype should have realistic, differentiated traits.

Return a JSON object with this exact structure:
{{
  "id": "{pack_id}",
  "name": "{body.name}",
  "version": "1.0",
  "category": "custom",
  "description": "{body.description}",
  "archetypes": [
    {{
      "id": "archetype-slug",
      "label": "Archetype Name",
      "weight": 0.25,
      "demographics": {{
        "age_range": [25, 55],
        "gender_distribution": {{"male": 0.50, "female": 0.45, "nonbinary": 0.05}},
        "education": ["Bachelors", "Masters"],
        "income_bracket": "$50k-$100k"
      }},
      "personality": {{
        "mbti_pool": ["INTJ", "ENTJ"],
        "big5": {{"openness": 0.7, "conscientiousness": 0.6, "extraversion": 0.5}}
      }},
      "platform_preferences": {{
        "twitter_x": 0.5, "reddit": 0.6, "linkedin": 0.3, "hacker_news": 0.2
      }},
      "behavior_traits": {{
        "posts_per_week": [2, 8],
        "typical_content": ["opinions", "analysis"],
        "sentiment_baseline": 0.1,
        "influence_multiplier": 1.5
      }},
      "interests": ["topic1", "topic2"],
      "political_lean": "center",
      "values": ["value1", "value2"]
    }}
  ]
}}

Weights across all archetypes should sum to approximately 1.0.
Make archetypes feel distinct — vary demographics, personality, sentiment, and influence.
Return ONLY the JSON object, no other text."""

    raw = await llm_complete(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096,
    )
    pack_json = json.loads(_extract_json(raw))

    # Validate against schema
    pack = PersonaPack.model_validate(pack_json)

    # Store in DB
    admin.table("custom_persona_packs").insert({
        "organization_id": auth["org_id"],
        "created_by": auth["user"]["id"],
        "pack_id": pack.id,
        "name": pack.name,
        "description": pack.description,
        "category": "custom",
        "pack_data": pack_json,
    }).execute()

    log.info("custom_pack_created", pack_id=pack.id, archetypes=len(pack.archetypes))
    return {
        "id": pack.id,
        "name": pack.name,
        "category": "custom",
        "description": pack.description,
        "archetype_count": len(pack.archetypes),
        "archetype_labels": [a.label for a in pack.archetypes],
    }
