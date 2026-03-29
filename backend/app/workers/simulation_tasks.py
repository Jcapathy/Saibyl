import asyncio

import structlog

from app.core.database import get_supabase_admin
from app.services.engine.document_processor import process_document
from app.services.engine.knowledge_graph_builder import build_graph
from app.services.engine.ontology_generator import generate_ontology
from app.services.engine.simulation_config_generator import generate_simulation_config
from app.workers.celery_app import celery_app

logger = structlog.get_logger()


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="process_document", bind=True, max_retries=3)
def task_process_document(self, document_id: str):
    """Process a single document: extract text, chunk, update status."""
    try:
        result = _run_async(process_document(document_id))
        logger.info("task_process_document_complete", document_id=document_id, chunks=len(result.chunks))
        return {"document_id": document_id, "chunks": len(result.chunks)}
    except Exception as exc:
        logger.error("task_process_document_failed", document_id=document_id, error=str(exc))
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="generate_ontology")
def task_generate_ontology(project_id: str):
    """Generate ontology from all project documents."""
    result = _run_async(generate_ontology(project_id))
    logger.info("task_generate_ontology_complete", project_id=project_id)
    return {"ontology_id": result["id"]}


@celery_app.task(name="build_knowledge_graph")
def task_build_knowledge_graph(project_id: str, ontology_id: str):
    """Build knowledge graph in Zep Cloud."""
    result = _run_async(build_graph(project_id, ontology_id))
    logger.info("task_build_knowledge_graph_complete", project_id=project_id)
    return {"knowledge_graph_id": result["id"]}


@celery_app.task(name="prepare_agents")
def task_prepare_agents(simulation_id: str):
    """Generate agent profiles for a simulation."""
    admin = get_supabase_admin()
    admin.table("simulations").update(
        {"status": "preparing"}
    ).eq("id", simulation_id).execute()

    config = _run_async(generate_simulation_config(simulation_id))

    admin.table("simulations").update(
        {"status": "ready"}
    ).eq("id", simulation_id).execute()

    logger.info(
        "task_prepare_agents_complete",
        simulation_id=simulation_id,
        agents=len(config.agent_behavior_configs),
    )
    return {"simulation_id": simulation_id, "status": "ready"}


@celery_app.task(name="run_simulation")
def task_run_simulation(simulation_id: str):
    """Run full simulation via simulation runner."""
    from app.services.platforms.simulation_runner import run_simulation

    logger.info("task_run_simulation_started", simulation_id=simulation_id)
    result = _run_async(run_simulation(simulation_id))
    logger.info("task_run_simulation_complete", simulation_id=simulation_id, events=result.total_events)
    return result.model_dump()


@celery_app.task(name="run_simulation_ab")
def task_run_simulation_ab(simulation_id: str):
    """Run A/B simulation — both variants concurrently."""
    from app.services.platforms.simulation_runner import run_simulation_ab

    logger.info("task_run_simulation_ab_started", simulation_id=simulation_id)
    result = _run_async(run_simulation_ab(simulation_id))
    logger.info("task_run_simulation_ab_complete", simulation_id=simulation_id)
    return result.model_dump()
