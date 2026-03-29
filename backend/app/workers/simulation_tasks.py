import asyncio
import random

import structlog

from app.core.database import get_supabase_admin
from app.core.llm_client import llm_complete
from app.services.engine.document_processor import process_document
from app.services.engine.ontology_generator import generate_ontology
from app.workers.celery_app import celery_app

logger = structlog.get_logger()


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="process_document", bind=True, max_retries=3)
def task_process_document(self, document_id: str):
    try:
        result = _run_async(process_document(document_id))
        logger.info("task_process_document_complete", document_id=document_id, chunks=len(result.chunks))
        return {"document_id": document_id, "chunks": len(result.chunks)}
    except Exception as exc:
        logger.error("task_process_document_failed", document_id=document_id, error=str(exc))
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="generate_ontology")
def task_generate_ontology(project_id: str):
    result = _run_async(generate_ontology(project_id))
    logger.info("task_generate_ontology_complete", project_id=project_id)
    return {"ontology_id": result["id"]}


@celery_app.task(name="build_knowledge_graph")
def task_build_knowledge_graph(project_id: str, ontology_id: str):
    from app.services.engine.knowledge_graph_builder import build_graph
    result = _run_async(build_graph(project_id, ontology_id))
    logger.info("task_build_knowledge_graph_complete", project_id=project_id)
    return {"knowledge_graph_id": result["id"]}


@celery_app.task(name="prepare_agents")
def task_prepare_agents(simulation_id: str):
    """Full pipeline: ensure ontology → generate agents from documents → mark ready."""
    admin = get_supabase_admin()

    sim = admin.table("simulations").select("*").eq("id", simulation_id).single().execute().data
    project_id = sim["project_id"]
    org_id = sim["organization_id"]
    platforms = sim.get("platforms") or ["twitter_x"]

    admin.table("simulations").update({"status": "preparing"}).eq("id", simulation_id).execute()
    logger.info("prepare_agents_start", simulation_id=simulation_id, project_id=project_id)

    # 1. Get ontology — must exist
    ontologies = admin.table("ontologies").select("*").eq(
        "project_id", project_id
    ).order("created_at", desc=True).limit(1).execute().data

    if not ontologies:
        admin.table("simulations").update({"status": "failed"}).eq("id", simulation_id).execute()
        raise ValueError("No ontology found. Generate an ontology first.")

    ontology = ontologies[0]
    entity_types = ontology.get("entity_types") or []
    logger.info("prepare_agents_ontology", entities=len(entity_types))

    # 2. Get document text for context
    docs = admin.table("documents").select("filename, storage_path, file_type").eq(
        "project_id", project_id
    ).eq("processing_status", "complete").execute().data

    doc_context = ""
    for doc in docs[:3]:  # Use first 3 docs
        try:
            file_bytes = admin.storage.from_("project-media").download(doc["storage_path"])
            doc_context += file_bytes.decode("utf-8", errors="replace")[:5000] + "\n\n"
        except Exception:
            pass

    # 3. Generate agents from entity types using LLM
    agents_to_create = []
    for entity_type in entity_types:
        if not entity_type.get("social_media_suitable", True):
            continue

        for platform in platforms:
            # Generate 2-3 agents per entity type per platform
            count = random.randint(2, 3)
            for i in range(count):
                try:
                    prompt = f"""Create a realistic social media persona for simulation.

Entity type: {entity_type['name']}
Description: {entity_type.get('description', '')}
Platform: {platform}
Context from documents: {doc_context[:2000]}

Return a JSON object with these fields:
- "display_name": realistic full name
- "username": social media handle (lowercase, no spaces)
- "bio": 1-2 sentence bio in character
- "age": integer
- "profession": specific job title
- "sentiment_baseline": float -1.0 to 1.0 (their general outlook)
- "backstory": 2 sentences about their perspective"""

                    raw = _run_async(llm_complete(
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=300,
                    ))

                    # Parse the response
                    from app.core.llm_client import _extract_json
                    import json
                    profile_data = json.loads(_extract_json(raw))

                    agents_to_create.append({
                        "simulation_id": simulation_id,
                        "organization_id": org_id,
                        "entity_id": f"{entity_type['name']}_{platform}_{i}",
                        "entity_name": profile_data.get("display_name", entity_type["name"]),
                        "persona_pack_id": None,
                        "variant": "a",
                        "platform": platform,
                        "profile": {
                            **profile_data,
                            "persona_type": entity_type["name"],
                            "entity_type": entity_type["name"],
                            "platform": platform,
                        },
                        "username": profile_data.get("username", f"{entity_type['name'].lower().replace(' ', '_')}_{i}"),
                    })
                    logger.info("agent_created", entity=entity_type["name"], platform=platform, name=profile_data.get("display_name"))

                except Exception as e:
                    logger.warning("agent_creation_failed", entity=entity_type["name"], error=str(e))
                    # Create a fallback agent
                    agents_to_create.append({
                        "simulation_id": simulation_id,
                        "organization_id": org_id,
                        "entity_id": f"{entity_type['name']}_{platform}_{i}",
                        "entity_name": f"{entity_type['name']} Agent {i+1}",
                        "persona_pack_id": None,
                        "variant": "a",
                        "platform": platform,
                        "profile": {
                            "display_name": f"{entity_type['name']} Agent {i+1}",
                            "persona_type": entity_type["name"],
                            "platform": platform,
                            "bio": f"A {entity_type['name'].lower()} active on {platform}",
                            "sentiment_baseline": random.uniform(-0.3, 0.5),
                        },
                        "username": f"{entity_type['name'].lower().replace(' ', '_')}_{platform}_{i}",
                    })

    # 4. Insert agents in batch
    if agents_to_create:
        # Insert in chunks of 20
        for i in range(0, len(agents_to_create), 20):
            batch = agents_to_create[i:i+20]
            admin.table("simulation_agents").insert(batch).execute()

    agent_count = len(agents_to_create)
    admin.table("simulations").update({
        "status": "ready",
        "agent_count": agent_count,
    }).eq("id", simulation_id).execute()

    logger.info("prepare_agents_complete", simulation_id=simulation_id, agents=agent_count)
    return {"simulation_id": simulation_id, "agents": agent_count, "status": "ready"}


@celery_app.task(name="run_simulation")
def task_run_simulation(simulation_id: str):
    """Run simulation — generate events from agents using LLM."""
    admin = get_supabase_admin()
    sim = admin.table("simulations").select("*").eq("id", simulation_id).single().execute().data

    if sim["status"] not in ("ready", "running"):
        logger.warning("sim_not_ready", status=sim["status"])
        return {"simulation_id": simulation_id, "status": sim["status"], "events": 0}

    admin.table("simulations").update({"status": "running"}).eq("id", simulation_id).execute()

    agents = admin.table("simulation_agents").select("*").eq("simulation_id", simulation_id).execute().data
    if not agents:
        admin.table("simulations").update({"status": "failed"}).eq("id", simulation_id).execute()
        return {"simulation_id": simulation_id, "status": "failed", "events": 0, "error": "No agents"}

    max_rounds = sim.get("max_rounds", 5)
    org_id = sim["organization_id"]
    prediction_goal = sim.get("prediction_goal", "")
    total_events = 0

    logger.info("simulation_start", simulation_id=simulation_id, agents=len(agents), rounds=max_rounds)

    for round_num in range(1, max_rounds + 1):
        round_events = []

        # Each agent produces 1-2 events per round
        for agent in agents:
            profile = agent.get("profile", {})
            platform = agent.get("platform", "twitter_x")

            try:
                prompt = f"""You are {profile.get('display_name', 'an agent')} ({profile.get('persona_type', 'person')}).
Bio: {profile.get('bio', '')}
Platform: {platform}
Topic: {prediction_goal}
Round: {round_num}/{max_rounds}

Write a realistic {platform} post reacting to this topic. Stay in character.
Keep it under 280 characters for Twitter, under 500 for others.
Also rate your sentiment from -1.0 (very negative) to 1.0 (very positive).

Format: POST: <your post content>
SENTIMENT: <number>"""

                response = _run_async(llm_complete(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=200,
                ))

                # Parse post and sentiment
                content = response.strip()
                sentiment = 0.0
                if "SENTIMENT:" in content:
                    parts = content.split("SENTIMENT:")
                    content = parts[0].replace("POST:", "").strip()
                    try:
                        sentiment = float(parts[1].strip()[:5])
                        sentiment = max(-1.0, min(1.0, sentiment))
                    except (ValueError, IndexError):
                        pass
                elif "POST:" in content:
                    content = content.replace("POST:", "").strip()

                round_events.append({
                    "simulation_id": simulation_id,
                    "organization_id": org_id,
                    "event_type": "post",
                    "agent_id": agent["id"],
                    "platform": platform,
                    "variant": "a",
                    "round_number": round_num,
                    "content": content[:1000],
                    "metadata": {"sentiment": sentiment},
                })

            except Exception as e:
                logger.warning("agent_event_failed", agent=agent.get("entity_name"), error=str(e))

        # Batch insert events for this round
        if round_events:
            admin.table("simulation_events").insert(round_events).execute()
            total_events += len(round_events)

        logger.info("round_complete", simulation_id=simulation_id, round=round_num, events=len(round_events))

    # Mark complete
    from datetime import datetime, UTC
    admin.table("simulations").update({
        "status": "complete",
        "completed_at": datetime.now(UTC).isoformat(),
    }).eq("id", simulation_id).execute()

    logger.info("simulation_complete", simulation_id=simulation_id, total_events=total_events)
    return {"simulation_id": simulation_id, "status": "complete", "total_events": total_events}


@celery_app.task(name="run_simulation_ab")
def task_run_simulation_ab(simulation_id: str):
    return task_run_simulation(simulation_id)
