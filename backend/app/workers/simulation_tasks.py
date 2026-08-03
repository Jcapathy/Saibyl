import asyncio
import json

import structlog

from app.core.database import get_supabase_admin
from app.core.llm_client import _extract_json, llm_fast
from app.services.billing.usage_ledger import usage_context
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


def _context_block(archetype) -> str:
    """The founder-lens grounding for one archetype, as prompt text.

    Empty for the 16 built-in packs, which carry no `context`. For a synthesized
    ICP this is the part that was worth an Opus pass: what this buyer uses
    today, what it would cost them to switch, what makes them stop reading. An
    ICP whose incumbent tooling never reaches an agent's head is a relabelled
    generic pack, which is the outcome DECISIONS §3 rejected packs to avoid.
    """
    ctx = getattr(archetype, "context", None)
    if ctx is None:
        return ""

    lines: list[str] = []
    if ctx.role:
        lines.append(f"Role: {ctx.role}")
    if ctx.seniority:
        lines.append(f"Seniority: {ctx.seniority}, budget authority: {ctx.budget_authority}")
    if ctx.incumbent_tooling:
        lines.append(
            f"Uses today: {', '.join(ctx.incumbent_tooling)} "
            f"(switching cost: {ctx.switching_cost or 'unknown'})"
        )
    if ctx.evaluation_criteria:
        lines.append(f"Judges on: {', '.join(ctx.evaluation_criteria)}")
    if ctx.skepticism_triggers:
        lines.append(f"Stops reading when: {', '.join(ctx.skepticism_triggers)}")
    if ctx.goals:
        lines.append(f"Trying to: {', '.join(ctx.goals)}")
    if ctx.pains:
        lines.append(f"Frustrated by: {', '.join(ctx.pains)}")

    if archetype.is_adversarial:
        # The guardrail, restated at the call site that could break it. A named
        # competitor reaches this prompt only when uploaded competitor material
        # licensed the name — but the model still must not invent facts about
        # that company, because the material grounds the name, not the claims.
        aligned = (
            f"aligned with {ctx.competitor_name}"
            if ctx.competitor_name
            else "aligned with the status quo, with no specific company in mind"
        )
        lines.append(f"This persona is {aligned}, and argues against adopting the subject.")
        if ctx.core_argument:
            lines.append(f"Their core argument: {ctx.core_argument}")
        if ctx.talking_points:
            lines.append(f"Their talking points: {', '.join(ctx.talking_points)}")
        lines.append(
            "Do not state facts about any real company's product, pricing, "
            "roadmap, or customers. Argue about the category and the cost of "
            "switching, which is what this persona actually knows."
        )

    return "\n" + "\n".join(lines) + "\n" if lines else ""


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
    from app.services.engine.personas.icp_synthesizer import rebalance_adversarial
    from app.services.engine.personas.pack_loader import get_pack

    # The run's configured share, not the one the ICP was compiled with. An ICP
    # is reused across runs, and a founder who wants to see the reception at 40%
    # incumbents should not have to re-synthesize their audience to find out.
    adversarial_share = float(sim.get("adversarial_share") or 0.0)

    all_archetypes = []
    for pack_id in persona_pack_ids:
        try:
            pack = get_pack(pack_id)
            for archetype in rebalance_adversarial(pack.archetypes, adversarial_share):
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
{_context_block(archetype)}
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

                raw = await llm_fast(
                    messages=[{"role": "user", "content": prompt}],
                    # 400 truncated the JSON mid-string for roughly 4 in 5
                    # profiles: seven fields including a 1-2 sentence bio and a
                    # 2-3 sentence backstory do not fit, and a truncated object
                    # fails json.loads and falls through to the stub profile
                    # below. A stub agent has no knowledge of the topic, so the
                    # cost of being stingy here is a whole run of bland agents.
                    max_tokens=900,
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
                    # Carried on the row, not inferred later from the archetype
                    # label. Every report and export labels these agents
                    # synthetic (PRD §4), and a label-matching rule is exactly
                    # the kind of string coupling this codebase has been
                    # removing.
                    "is_adversarial": archetype.is_adversarial,
                    "adversarial_role": archetype.adversarial_role,
                    "profile": {
                        **profile_data,
                        "archetype": archetype.label,
                        "pack": pack.name,
                        "persona_type": archetype.label,
                        "entity_type": archetype.label,
                        "platform": platform,
                        "influence_multiplier": archetype.behavior_traits.influence_multiplier,
                        "is_adversarial": archetype.is_adversarial,
                        "adversarial_role": archetype.adversarial_role,
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
                    "is_adversarial": archetype.is_adversarial,
                    "adversarial_role": archetype.adversarial_role,
                    "profile": {
                        "display_name": f"{archetype.label} #{i+1}",
                        "persona_type": archetype.label,
                        "platform": platform,
                        "bio": f"A {archetype.label.lower()} active on {platform}",
                        "sentiment_baseline": archetype.behavior_traits.sentiment_baseline,
                        "influence_multiplier": archetype.behavior_traits.influence_multiplier,
                        "is_adversarial": archetype.is_adversarial,
                        "adversarial_role": archetype.adversarial_role,
                    },
                    "username": f"{archetype.id}_{platform}_{i}",
                }

    if not agent_specs:
        admin.table("simulations").update({"status": "failed"}).eq("id", simulation_id).execute()
        raise ValueError("No agents to generate — check persona pack archetypes and platform selection")

    # Attributed to the agent_generation stage so the quote can be reconciled
    # against measured spend per stage, not just per run.
    with usage_context(
        "agent_generation", simulation_id=simulation_id, organization_id=org_id
    ):
        results = await asyncio.gather(
            *[_gen_pack_agent(p, a, plat, idx) for p, a, plat, idx in agent_specs],
            return_exceptions=True,
        )
    agents_to_create = [r for r in results if isinstance(r, dict)]

    # Usernames must be unique within a simulation. Platform adapters address
    # agents by username and nothing else: they key agent memory on it, and the
    # runner maps `event.agent_username` back to an agent row through it.
    #
    # The model does not cooperate. Asked for 100 handles it produced 45
    # distinct ones — nine agents called `mchen_itdir` — which silently merged
    # those nine into one: they shared memory, and all their events were
    # attributed to whichever row happened to be last in the lookup. Confidence
    # intervals are computed across agents, so nine independent observations
    # counted as one and every band in the artifact was drawn from a swarm less
    # than half its real size.
    seen_usernames: set[str] = set()
    for agent in agents_to_create:
        base = agent["username"]
        name, suffix = base, 2
        while name in seen_usernames:
            name = f"{base}{suffix}"
            suffix += 1
        if name != base:
            logger.info("agent_username_deduped", original=base, assigned=name)
        seen_usernames.add(name)
        agent["username"] = name
        agent["profile"]["username"] = name

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
    from datetime import UTC, datetime

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

    # Dispatch webhook: simulation started
    try:
        from app.services.billing.webhook_dispatcher import dispatch_webhook
        await dispatch_webhook(sim["organization_id"], "simulation.started", {
            "simulation_id": simulation_id,
            "name": sim.get("name", ""),
            "status": "running",
        })
    except Exception:
        pass  # Webhooks are best-effort

    agents = admin.table("simulation_agents").select("*").eq("simulation_id", simulation_id).execute().data
    if not agents:
        admin.table("simulations").update({"status": "failed"}).eq("id", simulation_id).execute()
        return {"simulation_id": simulation_id, "status": "failed", "events": 0}

    max_rounds = sim.get("max_rounds", 5)
    org_id = sim["organization_id"]
    prediction_goal = sim.get("prediction_goal", "")
    platforms_list = sim.get("platforms") or ["twitter_x"]
    total_events = 0

    # username -> agent_id, so an event can be attributed to the agent that
    # produced it. The old lookup also carried sentiment_baseline, which existed
    # only to feed the drift formula that has been removed — sentiment is now
    # measured from event content by services/intelligence/event_measurement.py.
    agent_lookup: dict[str, str] = {a["username"]: a["id"] for a in agents}

    # Defensive: uniqueness is enforced at generation, but a simulation prepared
    # before that fix — or by any other path — would silently under-count its
    # swarm here, and every confidence interval in the artifact would be drawn
    # from fewer agents than actually ran. Loud, because the resulting numbers
    # look entirely plausible.
    if len(agent_lookup) != len(agents):
        logger.error(
            "duplicate_agent_usernames",
            simulation_id=simulation_id,
            agents=len(agents),
            distinct_usernames=len(agent_lookup),
            detail="events will be mis-attributed and agent counts under-reported",
        )

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
                    # Identity. Adapters key memory on this and stamp it on
                    # every event they emit; `username` is a display handle.
                    "agent_id": a["id"],
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

            # Run all platforms concurrently within each round
            async def _run_platform_round(platform_id, adapter):
                events = []
                try:
                    async for event in adapter.run_round(round_num):
                        # Events are written unmeasured. Sentiment is scored
                        # from content after the run, not synthesised here from
                        # the agent's archetype preset and the round index.
                        events.append({
                            "simulation_id": simulation_id,
                            "organization_id": org_id,
                            "event_type": event.event_type,
                            # The adapter stamps the agent's id on the event.
                            # The username lookup is a fallback for adapters
                            # that predate the id, and is the path that
                            # collapsed nine agents onto one row.
                            "agent_id": event.agent_id
                            or agent_lookup.get(event.agent_username),
                            "platform": event.platform,
                            "variant": event.variant,
                            "round_number": event.round_number,
                            "content": event.content[:1000] if event.content else None,
                            "metadata": event.metadata or {},
                        })
                except Exception as e:
                    logger.warning("round_failed", platform=platform_id, round=round_num, error=str(e))
                return events

            with usage_context(
                "agent_action",
                simulation_id=simulation_id,
                organization_id=org_id,
            ):
                platform_results = await asyncio.gather(
                    *[_run_platform_round(pid, adp) for pid, adp in adapters.items()],
                    return_exceptions=True,
                )

            round_events = []
            for result in platform_results:
                if isinstance(result, list):
                    round_events.extend(result)

            if round_events:
                for i in range(0, len(round_events), 20):
                    admin.table("simulation_events").insert(round_events[i:i+20]).execute()
                total_events += len(round_events)

            logger.info("round_complete", simulation_id=simulation_id, round=round_num, events=len(round_events))
    except Exception as e:
        logger.exception("simulation_run_error", simulation_id=simulation_id, error=str(e))
        error_msg = f"[run_simulation] {type(e).__name__}: {e}"
        admin.table("simulations").update({
            "status": "failed",
            "error_message": error_msg,
        }).eq("id", simulation_id).execute()
        try:
            from app.services.billing.webhook_dispatcher import dispatch_webhook
            await dispatch_webhook(org_id, "simulation.failed", {
                "simulation_id": simulation_id, "error": error_msg,
            })
        except Exception:
            pass
        return {"simulation_id": simulation_id, "status": "failed", "total_events": total_events}

    if total_events == 0:
        admin.table("simulations").update({
            "status": "failed",
            "error_message": "Simulation completed all rounds but generated 0 events. "
                "This usually means the LLM failed to produce valid actions for any agent. "
                "Check that your Anthropic API key is valid and has available credits.",
        }).eq("id", simulation_id).execute()
        logger.error("simulation_zero_events", simulation_id=simulation_id)
        return {"simulation_id": simulation_id, "status": "failed", "total_events": 0}

    # Track usage: agent-rounds consumed
    agent_rounds = len(agents) * max_rounds
    try:
        admin.table("simulations").update({
            "agent_rounds_consumed": agent_rounds,
        }).eq("id", simulation_id).execute()
    except Exception:
        pass

    # Measure the events and build the analysis artifact before the run is
    # marked complete. The report reads the artifact, and the UI renders only
    # from it, so a run that is "complete" without one would show a customer an
    # empty report and no explanation.
    admin.table("simulations").update({"status": "analyzing"}).eq(
        "id", simulation_id
    ).execute()

    from app.workers.analysis_tasks import run_analysis
    analysis_summary = await run_analysis(simulation_id, org_id)

    admin.table("simulations").update({
        "status": "complete",
        "completed_at": datetime.now(UTC).isoformat(),
    }).eq("id", simulation_id).execute()

    logger.info("simulation_complete", simulation_id=simulation_id, total_events=total_events)

    # Dispatch webhook: simulation complete
    try:
        from app.services.billing.webhook_dispatcher import dispatch_webhook
        await dispatch_webhook(org_id, "simulation.complete", {
            "simulation_id": simulation_id,
            "name": sim.get("name", ""),
            "status": "complete",
            "total_events": total_events,
            "agent_rounds": agent_rounds,
            "measurement_coverage_pct": analysis_summary.get("coverage_pct", 0.0),
        })
    except Exception:
        pass

    # Report generation runs after the artifact exists, and is awaited rather
    # than detached. The run is already marked complete, so the UI shows the
    # measured findings immediately while the narrative is written — but this
    # task must outlive the report, because the cost reconciliation below is
    # only meaningful once the report's spend is in the ledger, and the report
    # is the largest main-model stage in the run.
    from app.workers.analysis_tasks import reconcile_run_cost
    from app.workers.report_tasks import run_generate_report

    # The depth the run was quoted at, not the report writer's default. Report
    # depth is the one setting that changes a run's cost without changing the
    # simulation, and `run_generate_report` defaults to "deep" — so a run
    # configured and priced as "standard" was silently written at deep depth,
    # producing more Opus-written sections than the customer was quoted for.
    depth_map = {"brief": "shallow", "standard": "standard", "deep": "deep"}
    evidence_depth = depth_map.get(sim.get("depth") or "standard", "standard")

    logger.info(
        "report_generation_started",
        simulation_id=simulation_id,
        depth=sim.get("depth"),
        evidence_depth=evidence_depth,
    )
    try:
        await run_generate_report(simulation_id, evidence_depth=evidence_depth)
    except Exception:
        # A failed report does not invalidate the run: the events and the
        # artifact are already stored, and the run still consumed compute that
        # has to be reconciled.
        logger.exception("report_generation_failed", simulation_id=simulation_id)

    reconciliation = reconcile_run_cost(simulation_id, org_id)
    try:
        admin.table("simulations").update({
            "retail_cost_usd": reconciliation.get("measured_cost_usd", 0.0),
        }).eq("id", simulation_id).execute()
    except Exception:
        logger.warning("retail_cost_write_failed", simulation_id=simulation_id)

    return {
        "simulation_id": simulation_id,
        "status": "complete",
        "total_events": total_events,
        "analysis": {**analysis_summary, **reconciliation},
    }


async def run_simulation_ab(simulation_id: str):
    return await run_simulation(simulation_id)
