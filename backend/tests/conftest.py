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
