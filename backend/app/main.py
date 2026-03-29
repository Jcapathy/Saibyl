import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    api_keys,
    auth,
    billing,
    documents,
    exports,
    markets,
    ontologies,
    organizations,
    personas,
    platforms,
    projects,
    reports,
    simulations,
    uploads,
    webhooks,
    ws,
)
from app.core.config import settings
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle — launches Redis-to-WebSocket bridge."""
    from app.services.streaming.redis_bridge import start_redis_bridge

    bridge_task = asyncio.create_task(start_redis_bridge())
    yield
    bridge_task.cancel()
    try:
        await bridge_task
    except asyncio.CancelledError:
        pass


def create_app() -> FastAPI:
    setup_logging()

    app = FastAPI(
        title="Saibyl API",
        description="Swarm Intelligence Prediction Platform",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins.split(","),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )

    # REST API routers
    app.include_router(auth.router, prefix="/api/auth")
    app.include_router(organizations.router, prefix="/api/organizations")
    app.include_router(projects.router, prefix="/api/projects")
    app.include_router(documents.router, prefix="/api/documents")
    app.include_router(ontologies.router, prefix="/api/ontologies")
    app.include_router(simulations.router, prefix="/api/simulations")
    app.include_router(reports.router, prefix="/api/reports")
    app.include_router(personas.router, prefix="/api/persona-packs")
    app.include_router(platforms.router, prefix="/api/platforms")
    app.include_router(webhooks.router, prefix="/api/webhooks")
    app.include_router(billing.router, prefix="/api/billing")
    app.include_router(api_keys.router, prefix="/api/api-keys")
    app.include_router(exports.router, prefix="/api")
    app.include_router(uploads.router, prefix="/api/uploads")
    app.include_router(markets.router, prefix="/api/markets")

    # WebSocket + SSE streaming
    app.include_router(ws.router)

    @app.get("/health")
    async def health():
        checks = {}
        # Database check
        try:
            from app.core.database import get_supabase_admin
            admin = get_supabase_admin()
            admin.table("organizations").select("id").limit(1).execute()
            checks["database"] = "ok"
        except Exception as e:
            checks["database"] = f"error: {e}"

        # Redis check
        try:
            import redis as r
            rc = r.from_url(settings.redis_url, decode_responses=True)
            rc.ping()
            checks["redis"] = "ok"
        except Exception as e:
            checks["redis"] = f"error: {e}"

        checks["llm"] = "ok"  # don't call LLM on health check
        status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"

        return {
            "status": status,
            "version": "1.0.0",
            "environment": settings.environment,
            "checks": checks,
        }

    # Sentry integration
    if settings.sentry_dsn and settings.environment != "development":
        import sentry_sdk
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            traces_sample_rate=0.1,
        )

    return app


app = create_app()
