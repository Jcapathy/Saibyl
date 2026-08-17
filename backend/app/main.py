import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import (
    accuracy,
    admin,
    analysis,
    auth,
    billing,
    clearance,
    comparison,
    documents,
    exports,
    gtm,
    icp,
    inoculation,
    organizations,
    packs,
    personas,
    products,
    projects,
    reports,
    simulations,
    variants,
    website,
    ws,
)
from app.core.config import settings
from app.core.logging import setup_logging

# Maximum accepted request body (50 MB) — enforced by LimitRequestBodyMiddleware.
MAX_BODY_SIZE = 50 * 1024 * 1024


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
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url="/redoc" if settings.environment != "production" else None,
        redirect_slashes=False,
        lifespan=lifespan,
    )

    logger = logging.getLogger(__name__)

    class LimitRequestBodyMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            if request.headers.get("content-length"):
                if int(request.headers["content-length"]) > MAX_BODY_SIZE:
                    return JSONResponse(status_code=413, content={"detail": "Request too large"})

            received = 0
            original_receive = request._receive

            async def sized_receive():
                nonlocal received
                message = await original_receive()
                if message.get("type") == "http.request":
                    received += len(message.get("body", b""))
                    if received > MAX_BODY_SIZE:
                        raise HTTPException(413, "Request too large")
                return message

            request._receive = sized_receive
            return await call_next(request)

    app.add_middleware(LimitRequestBodyMiddleware)

    # CORS configuration
    cors_origins = [o.strip() for o in settings.cors_origins.split(",")]
    allow_credentials = True
    if "*" in cors_origins and allow_credentials:
        logger.warning(
            "CORS wildcard '*' with allow_credentials=True is invalid per spec; "
            "disabling credentials"
        )
        allow_credentials = False

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=allow_credentials,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )

    # Security response headers
    class SecurityHeadersMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            response = await call_next(request)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
            if settings.environment in ("production", "staging"):
                response.headers["Strict-Transport-Security"] = (
                    "max-age=31536000; includeSubDomains"
                )
            return response

    app.add_middleware(SecurityHeadersMiddleware)

    # REST API routers
    app.include_router(auth.router, prefix="/api/auth")
    app.include_router(organizations.router, prefix="/api/organizations")
    app.include_router(projects.router, prefix="/api/projects")
    # The staged rail. Its own prefix rather than paths under /api/projects:
    # it is a read model over five subsystems, and mounting it alongside the
    # CRUD routes would put a static path in front of `/projects/{id}`.
    # Additive — every /api/projects route still works and still returns the
    # same rows.
    app.include_router(products.router, prefix="/api/products")
    app.include_router(documents.router, prefix="/api/documents")
    app.include_router(simulations.router, prefix="/api/simulations")
    app.include_router(reports.router, prefix="/api/reports")
    app.include_router(personas.router, prefix="/api/persona-packs")
    # The org-level pack library. Separate prefix from /api/persona-packs, which
    # is the built-in + custom picker; nothing here can shadow one of its paths.
    app.include_router(packs.router, prefix="/api/packs")
    app.include_router(icp.router, prefix="/api/icp")
    # Go-to-market candidate discovery. Its own prefix rather than nesting
    # under /api/icp: it reads an ICP but is a separate asset with its own
    # lifecycle, and nothing here can shadow an ICP path.
    app.include_router(gtm.router, prefix="/api/gtm")
    app.include_router(inoculation.router, prefix="/api/inoculation")
    app.include_router(variants.router, prefix="/api/variants")
    app.include_router(billing.router, prefix="/api/billing")
    app.include_router(clearance.router, prefix="/api/clearance")
    app.include_router(website.router, prefix="/api/website")
    app.include_router(admin.router, prefix="/api/admin")
    # Mounted at /api because its paths are nested under /simulations/{id}/…
    # but it is a separate module from the simulation lifecycle router.
    # Registered after simulations.router so no path can shadow one of its
    # routes — the collision that made the export path unreachable in V1.
    app.include_router(analysis.router, prefix="/api")
    app.include_router(exports.router, prefix="/api")
    app.include_router(accuracy.router, prefix="/api/accuracy")
    app.include_router(comparison.router, prefix="/api/compare")

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
        except Exception:
            checks["database"] = "error"

        # Redis check
        try:
            import redis as r
            rc = r.from_url(settings.redis_url, decode_responses=True)
            rc.ping()
            checks["redis"] = "ok"
        except Exception:
            checks["redis"] = "error"

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
