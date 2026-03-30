import asyncio
import json
import random

import structlog

from app.core.database import get_supabase_admin
from app.core.llm_client import llm_complete, _extract_json
from app.services.engine.document_processor import process_document
from app.services.engine.ontology_generator import generate_ontology

logger = structlog.get_logger()

# Limit concurrent LLM calls during agent generation to avoid rate limits
_AGENT_GEN_SEMAPHORE = asyncio.Semaphore(8)


async def run_process_document(document_id: str):
    result = await process_document(document_id)
    logger.info("task_process_document_complete", document_id=document_id, chunks=len(result.chunks))
    return {"document_id": document_id, "chunks": len(result.chunks)}


async def run_generate_ontology(project_id: str):
    result = await generate_ontology(project_id)
    logger.info("task_generate_ontology_complete", project_id=project_id)
    return {"ontology_id": result["id"]}


async def run_build_knowledge_graph(project_id: str, ontology_id: str):
    from app.services.engine.knowledge_graph_builder import build_graph
    result = await build_graph(project_id, ontology_id)
    logger.info("task_build_knowledge_graph_complete", project_id=project_id)
    return {"knowledge_graph_id": result["id"]}


async def run_prepare_agents(simulation_id: str):
    """Generate agents from persona packs (or fallback to ontology entities)."""
    admin = get_supabase_admin()
    sim = admin.table("simulations").select("*").eq("id", simulation_id).single().execute().data
    project_id = sim["project_id"]
    org_id = sim["organization_id"]
    platforms = sim.get("platforms") or ["twitter_x"]
    persona_pack_ids = sim.get("persona_pack_ids") or []
    target_agent_count = sim.get("agent_count") or 20

    admin.table("simulations").update({"status": "preparing"}).eq("id", simulation_id).execute()
    logger.info("prepare_agents_start", simulation_id=simulation_id, packs=len(persona_pack_ids))

    # Get document context for grounding (parallel downloads)
    docs = admin.table("documents").select("filename, storage_path").eq(
        "project_id", project_id
    ).eq("processing_status", "complete").execute().data

    async def _download_doc(storage_path: str) -> str:
        try:
            file_bytes = await asyncio.to_thread(
                admin.storage.from_("project-media").download, storage_path
            )
            return file_bytes.decode("utf-8", errors="replace")[:5000] + "\n\n"
        except Exception:
            return ""

    doc_chunks = await asyncio.gather(*[_download_doc(d["storage_path"]) for d in docs[:3]])
    doc_context = "".join(doc_chunks)

    prediction_goal = sim.get("prediction_goal", "")

    # Load ontology context if available — used to enrich persona-based agents
    ontology_context = ""
    try:
        ontologies = admin.table("ontologies").select("entity_types, relationship_types").eq(
            "project_id", project_id
        ).order("created_at", desc=True).limit(1).execute().data
        if ontologies:
            entity_types = ontologies[0].get("entity_types") or []
            relationships = ontologies[0].get("relationship_types") or []
            entity_names = [et.get("name", "") for et in entity_types]
            rel_summaries = [f"{r.get('name', '')}: {r.get('source_entity_type', '')} → {r.get('target_entity_type', '')}" for r in relationships[:10]]
            ontology_context = f"Key entities in this domain: {', '.join(entity_names[:15])}."
            if rel_summaries:
                ontology_context += f" Key relationships: {'; '.join(rel_summaries)}."
    except Exception:
        pass  # Ontology enrichment is optional

    if not persona_pack_ids:
        admin.table("simulations").update({"status": "failed"}).eq("id", simulation_id).execute()
        raise ValueError(
            "No persona packs selected. Please select at least one persona pack "
            "(built-in or custom) to run a simulation."
        )

    # -- Generate agents from persona packs (enriched with ontology + doc context) --
    from app.services.engine.personas.pack_loader import get_pack

    all_archetypes = []
    for pack_id in persona_pack_ids:
        try:
            pack = get_pack(pack_id)
            for archetype in pack.archetypes:
                all_archetypes.append((pack, archetype))
        except KeyError:
            logger.warning("pack_not_found", pack_id=pack_id)

    if not all_archetypes:
        admin.table("simulations").update({"status": "failed"}).eq("id", simulation_id).execute()
        raise ValueError("No valid persona packs found")

    total_weight = sum(a.weight for _, a in all_archetypes)
    agents_per_platform = max(1, target_agent_count // len(platforms))

    agent_specs = []
    for platform in platforms:
        remaining = agents_per_platform
        for pack, archetype in all_archetypes:
            count = max(1, round(archetype.weight / total_weight * agents_per_platform))
            if remaining <= 0:
                break
            count = min(count, remaining)
            remaining -= count
            for i in range(count):
                agent_specs.append((pack, archetype, platform, i))

    async def _gen_pack_agent(pack, archetype, platform, i):
        async with _AGENT_GEN_SEMAPHORE:
            try:
                prompt = f"""Create a realistic social media persona for a {platform} simulation.

Archetype: {archetype.label}
Pack: {pack.name}
Demographics: age {archetype.demographics.age_range[0]}-{archetype.demographics.age_range[1]}, education: {', '.join(archetype.demographics.education)}, income: {archetype.demographics.income_bracket}
Personality: MBTI pool: {archetype.personality.mbti_pool}, Big5: {archetype.personality.big5}
Interests: {', '.join(archetype.interests)}
Values: {', '.join(archetype.values)}
Political lean: {archetype.political_lean}
Typical content: {', '.join(archetype.behavior_traits.typical_content)}
Sentiment baseline: {archetype.behavior_traits.sentiment_baseline}

Topic context: {prediction_goal}
Domain context: {ontology_context}
Document context: {doc_context[:2000]}

This persona should have grounded knowledge of the topic from the domain and document context above.
Their opinions, backstory, and behavior should reflect how a real {archetype.label} would engage with this specific subject matter.

Return a JSON object:
- "display_name": realistic full name
- "username": {platform} handle (lowercase, no spaces)
- "bio": 1-2 sentence bio in character, referencing the topic
- "age": integer within the age range
- "profession": specific job title fitting this archetype and domain
- "sentiment_baseline": float (use {archetype.behavior_traits.sentiment_baseline} as center, vary +/-0.15)
- "backstory": 2-3 sentences about their perspective on the topic, informed by the domain context"""

                raw = await llm_complete(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=400,
                )
                profile_data = json.loads(_extract_json(raw))

                logger.info("agent_created", archetype=archetype.label, platform=platform)
                return {
                    "simulation_id": simulation_id,
                    "organization_id": org_id,
                    "entity_id": f"{archetype.id}_{platform}_{i}",
                    "entity_name": profile_data.get("display_name", archetype.label),
                    "persona_pack_id": pack.id,
                    "variant": "a",
                    "platform": platform,
                    "profile": {
                        **profile_data,
                        "archetype": archetype.label,
                        "pack": pack.name,
                        "persona_type": archetype.label,
                        "entity_type": archetype.label,
                        "platform": platform,
                        "influence_multiplier": archetype.behavior_traits.influence_multiplier,
                    },
                    "username": profile_data.get("username", f"{archetype.id}_{i}"),
                }
            except Exception as e:
                logger.warning("agent_creation_failed", archetype=archetype.label, error=str(e))
                return {
                    "simulation_id": simulation_id,
                    "organization_id": org_id,
                    "entity_id": f"{archetype.id}_{platform}_{i}",
                    "entity_name": f"{archetype.label} #{i+1}",
                    "persona_pack_id": pack.id,
                    "variant": "a",
                    "platform": platform,
                    "profile": {
                        "display_name": f"{archetype.label} #{i+1}",
                        "persona_type": archetype.label,
                        "platform": platform,
                        "bio": f"A {archetype.label.lower()} active on {platform}",
                        "sentiment_baseline": archetype.behavior_traits.sentiment_baseline,
                        "influence_multiplier": archetype.behavior_traits.influence_multiplier,
                    },
                    "username": f"{archetype.id}_{platform}_{i}",
                }

    if not agent_specs:
        admin.table("simulations").update({"status": "failed"}).eq("id", simulation_id).execute()
        raise ValueError("No agents to generate — check persona pack archetypes and platform selection")

    results = await asyncio.gather(
        *[_gen_pack_agent(p, a, plat, idx) for p, a, plat, idx in agent_specs],
        return_exceptions=True,
    )
    agents_to_create = [r for r in results if isinstance(r, dict)]

    # Guard: if zero agents were created, fail explicitly
    if not agents_to_create:
        admin.table("simulations").update({"status": "failed"}).eq("id", simulation_id).execute()
        logger.error("prepare_agents_zero", simulation_id=simulation_id)
        raise ValueError("Agent generation produced 0 agents — all LLM calls failed")

    # Insert agents in batch
    if agents_to_create:
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


def _check_stop_signal(simulation_id: str) -> bool:
    """Check Redis for a stop signal."""
    try:
        import redis
        from app.core.config import settings
        r = redis.from_url(settings.redis_url, decode_responses=True)
        return bool(r.get(f"simulation:{simulation_id}:stop"))
    except Exception:
        return False


async def run_simulation(simulation_id: str):
    """Run simulation using platform adapters."""
    from datetime import datetime, UTC

    admin = get_supabase_admin()
    sim = admin.table("simulations").select("*").eq("id", simulation_id).single().execute().data

    if sim["status"] not in ("ready", "running"):
        logger.error(
            "sim_not_ready_for_run",
            simulation_id=simulation_id,
            status=sim["status"],
            detail="start called on sim that is not ready — status check should have caught this",
        )
        return {"simulation_id": simulation_id, "status": sim["status"], "events": 0}

    admin.table("simulations").update({"status": "running"}).eq("id", simulation_id).execute()

    agents = admin.table("simulation_agents").select("*").eq("simulation_id", simulation_id).execute().data
    if not agents:
        admin.table("simulations").update({"status": "failed"}).eq("id", simulation_id).execute()
        return {"simulation_id": simulation_id, "status": "failed", "events": 0}

    max_rounds = sim.get("max_rounds", 5)
    org_id = sim["organization_id"]
    prediction_goal = sim.get("prediction_goal", "")
    platforms_list = sim.get("platforms") or ["twitter_x"]
    total_events = 0

    # Build username -> (agent_id, sentiment_baseline) lookup for event enrichment
    agent_lookup: dict[str, dict] = {
        a["username"]: {"id": a["id"], "sentiment_baseline": a.get("profile", {}).get("sentiment_baseline", 0.0)}
        for a in agents
    }

    # Initialize platform adapters
    from app.services.platforms.registry import get_adapter, load_all_adapters
    load_all_adapters()

    adapters = {}
    for platform_id in platforms_list:
        try:
            adapter = get_adapter(platform_id)
            # Get agents for this platform
            platform_agents = [
                {
                    "username": a["username"],
                    "persona": a.get("profile", {}).get("bio", ""),
                    "variant": a.get("variant", "a"),
                    "profile": a.get("profile", {}),
                }
                for a in agents if a.get("platform") == platform_id
            ]
            if platform_agents:
                await adapter.initialize(
                    config={"prediction_goal": prediction_goal, "simulation_id": simulation_id},
                    agents=platform_agents,
                )
                adapters[platform_id] = adapter
        except Exception as e:
            logger.warning("adapter_init_failed", platform=platform_id, error=str(e))

    logger.info("simulation_start", simulation_id=simulation_id, agents=len(agents), rounds=max_rounds, platforms=list(adapters.keys()))

    try:
        for round_num in range(1, max_rounds + 1):
            # Check stop signal before each round
            if _check_stop_signal(simulation_id):
                logger.info("simulation_stopped", simulation_id=simulation_id, round=round_num)
                admin.table("simulations").update({"status": "stopped"}).eq("id", simulation_id).execute()
                return {"simulation_id": simulation_id, "status": "stopped", "total_events": total_events}

            round_events = []

            for platform_id, adapter in adapters.items():
                try:
                    async for event in adapter.run_round(round_num):
                        agent_info = agent_lookup.get(event.agent_username, {})
                        agent_id = agent_info.get("id")
                        sentiment_score = agent_info.get("sentiment_baseline", 0.0)

                        round_events.append({
                            "simulation_id": simulation_id,
                            "organization_id": org_id,
                            "event_type": event.event_type,
                            "agent_id": agent_id,
                            "platform": event.platform,
                            "variant": event.variant,
                            "round_number": event.round_number,
                            "content": event.content[:1000] if event.content else None,
                            "metadata": event.metadata,
                            "sentiment_score": sentiment_score,
                        })
                except Exception as e:
                    logger.warning("round_failed", platform=platform_id, round=round_num, error=str(e))

            if round_events:
                for i in range(0, len(round_events), 20):
                    admin.table("simulation_events").insert(round_events[i:i+20]).execute()
                total_events += len(round_events)

            logger.info("round_complete", simulation_id=simulation_id, round=round_num, events=len(round_events))
    except Exception as e:
        logger.exception("simulation_run_error", simulation_id=simulation_id, error=str(e))
        admin.table("simulations").update({
            "status": "failed",
            "error_message": f"[run_simulation] {type(e).__name__}: {e}",
        }).eq("id", simulation_id).execute()
        return {"simulation_id": simulation_id, "status": "failed", "total_events": total_events}

    admin.table("simulations").update({
        "status": "complete",
        "completed_at": datetime.now(UTC).isoformat(),
    }).eq("id", simulation_id).execute()

    logger.info("simulation_complete", simulation_id=simulation_id, total_events=total_events)

    # Auto-trigger report generation after simulation completes
    from app.workers.report_tasks import run_generate_report
    asyncio.create_task(run_generate_report(simulation_id))
    logger.info("report_generation_triggered", simulation_id=simulation_id)

    return {"simulation_id": simulation_id, "status": "complete", "total_events": total_events}


async def run_simulation_ab(simulation_id: str):
    return await run_simulation(simulation_id)
