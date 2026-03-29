from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "saibyl",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.workers.simulation_tasks",
        "app.workers.report_tasks",
        "app.workers.export_tasks",
        "app.workers.asset_tasks",
        "app.workers.market_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_expires=86400,  # 24 hours
    worker_concurrency=settings.simulation_worker_concurrency,
)
