import os

import pytest

# Set test env vars before any app imports
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("SECRET_KEY", "test-secret-key-32chars-minimum!")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-fake")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")



@pytest.fixture(autouse=True)
def _log_assertions_are_not_vacuous():
    """Make `structlog.testing.capture_logs` see `app.*` module loggers.

    Without this, a log assertion can pass because nothing was captured rather
    than because the right thing was logged — and it does so **depending on
    test order**, which is the worst version of the problem.

    The mechanism: modules hold `logger = structlog.get_logger(__name__)`, a
    lazy proxy that resolves to a real bound logger on first use and, with
    `cache_logger_on_first_use=True`, keeps it forever. `setup_logging()`
    installs a *new* processors list and `create_app()` calls it every time,
    while `capture_logs` swaps processors on whichever list is current, in
    place. So a module logger first used before the most recent `create_app()`
    stays bound to the old list: it still logs, and `capture_logs` still
    returns `[]`.

    Resetting the proxies before each test forces them to re-resolve against
    the live configuration. Four test files had each grown their own autouse
    fixture doing this for one module — a duplicated fix is the "two sources of
    truth" class, and it only protects the modules somebody already knew to
    protect. This covers every `app.*` module and needs no upkeep.

    `test_log_capture_canary.py` fails if this stops working.
    """
    import sys

    import structlog
    from structlog._config import BoundLoggerLazyProxy

    restore: list[tuple[object, str, object]] = []
    for name, module in list(sys.modules.items()):
        if not name.startswith("app.") or module is None:
            continue
        for attr in ("logger", "log"):
            existing = getattr(module, attr, None)
            if isinstance(existing, BoundLoggerLazyProxy):
                restore.append((module, attr, existing))
                setattr(module, attr, structlog.get_logger(name))

    try:
        yield
    finally:
        for module, attr, original in restore:
            setattr(module, attr, original)


@pytest.fixture
def app():
    """Create a FastAPI test app instance."""
    from app.main import create_app
    return create_app()


@pytest.fixture
def client(app):
    """Create a test client."""
    from fastapi.testclient import TestClient
    return TestClient(app)
