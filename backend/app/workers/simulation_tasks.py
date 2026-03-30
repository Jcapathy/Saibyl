import random

import structlog

from app.core.database import get_supabase_admin
from app.core.llm_client import llm_complete
from app.services.engine.document_processor import process_document
from app.services.engine.ontology_generator import generate_ontology

logger = structlog.get_logger()


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

    # Get document context for grounding
    docs = admin.table("documents").select("filename, storage_path").eq(
        "project_id", project_id
    ).eq("processing_status", "complete").execute().data
    doc_context = ""
    for doc in docs[:3]:
        try:
            file_bytes = admin.storage.from_("project-media").download(doc["storage_path"])
            doc_context += file_bytes.decode("utf-8", errors="replace")[:5000] + "\n\n"
        except Exception:
            pass

    prediction_goal = sim.get("prediction_goal", "")
    agents_to_create = []

    if persona_pack_ids:
        # -- Generate agents from persona packs --
        from app.services.engine.personas.pack_loader import get_pack

        # Collect all archetypes from selected packs with their weights
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

        # Distribute agents across archetypes by weight, then across platforms
        total_weight = sum(a.weight for _, a in all_archetypes)
        agents_per_platform = max(1, target_agent_count // len(platforms))

        for platform in platforms:
            remaining = agents_per_platform
            for pack, archetype in all_archetypes:
                # How many agents for this archetype on this platform
                count = max(1, round(archetype.weight / total_weight * agents_per_platform))
                if remaining <= 0:
                    break
                count = min(count, remaining)
                remaining -= count

                for i in range(count):
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
Document context: {doc_context[:2000]}

Return a JSON object:
- "display_name": realistic full name
- "username": {platform} handle (lowercase, no spaces)
- "bio": 1-2 sentence bio in character
- "age": integer within the age range
- "profession": specific job title fitting this archetype
- "sentiment_baseline": float (use {archetype.behavior_traits.sentiment_baseline} as center, vary +/-0.15)
- "backstory": 2 sentences about their perspective on the topic"""

                        raw = await llm_complete(
                            messages=[{"role": "user", "content": prompt}],
                            max_tokens=300,
                        )
                        from app.core.llm_client import _extract_json
                        import json
                        profile_data = json.loads(_extract_json(raw))

                        agents_to_create.append({
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
                        })
                        logger.info("agent_created", archetype=archetype.label, platform=platform)
                    except Exception as e:
                        logger.warning("agent_creation_failed", archetype=archetype.label, error=str(e))
                        # Fallback agent
                        agents_to_create.append({
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
                        })
    else:
        # -- Fallback: generate from ontology entities (original behavior) --
        ontologies = admin.table("ontologies").select("*").eq(
            "project_id", project_id
        ).order("created_at", desc=True).limit(1).execute().data

        if not ontologies:
            admin.table("simulations").update({"status": "failed"}).eq("id", simulation_id).execute()
            raise ValueError("No ontology found and no persona packs selected.")

        entity_types = ontologies[0].get("entity_types") or []
        agents_per_entity = max(1, target_agent_count // (len(entity_types) * len(platforms))) if entity_types else 2

        for entity_type in entity_types:
            if not entity_type.get("social_media_suitable", True):
                continue
            for platform in platforms:
                for i in range(agents_per_entity):
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
- "sentiment_baseline": float -1.0 to 1.0
- "backstory": 2 sentences about their perspective"""

                        raw = await llm_complete(messages=[{"role": "user", "content": prompt}], max_tokens=300)
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
                    except Exception as e:
                        logger.warning("agent_creation_failed", entity=entity_type["name"], error=str(e))
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


async def run_simulation(simulation_id: str):
    """Run simulation using platform adapters."""
    admin = get_supabase_admin()
    sim = admin.table("simulations").select("*").eq("id", simulation_id).single().execute().data

    if sim["status"] not in ("ready", "running"):
        logger.warning("sim_not_ready", status=sim["status"])
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

    for round_num in range(1, max_rounds + 1):
        round_events = []

        for platform_id, adapter in adapters.items():
            try:
                async for event in adapter.run_round(round_num):
                    # Find agent_id from username
                    agent_id = None
                    for a in agents:
                        if a["username"] == event.agent_username:
                            agent_id = a["id"]
                            break

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
                    })
            except Exception as e:
                logger.warning("round_failed", platform=platform_id, round=round_num, error=str(e))

        if round_events:
            for i in range(0, len(round_events), 20):
                admin.table("simulation_events").insert(round_events[i:i+20]).execute()
            total_events += len(round_events)

        logger.info("round_complete", simulation_id=simulation_id, round=round_num, events=len(round_events))

    from datetime import datetime, UTC
    admin.table("simulations").update({
        "status": "complete",
        "completed_at": datetime.now(UTC).isoformat(),
    }).eq("id", simulation_id).execute()

    logger.info("simulation_complete", simulation_id=simulation_id, total_events=total_events)
    return {"simulation_id": simulation_id, "status": "complete", "total_events": total_events}


async def run_simulation_ab(simulation_id: str):
    return await run_simulation(simulation_id)
