def test_settings_loads_defaults():
    from app.core.config import Settings

    s = Settings(
        secret_key="test",
        anthropic_api_key="test",
        supabase_url="https://test.supabase.co",
        supabase_anon_key="test",
        supabase_service_role_key="test",
        database_url="postgresql://test:test@localhost/test",
    )
    assert s.environment == "development"
    assert s.redis_url == "redis://localhost:6379"
    assert s.frontend_url == "http://localhost:3000"
    assert s.llm_provider == "anthropic"
    assert s.simulation_max_rounds == 10
    assert s.simulation_worker_concurrency == 4


def test_settings_accepts_production():
    from app.core.config import Settings

    s = Settings(
        environment="production",
        # Production requires a SECRET_KEY of at least 32 characters.
        secret_key="p" * 32,
        anthropic_api_key="sk-prod",
        supabase_url="https://prod.supabase.co",
        supabase_anon_key="prod-anon",
        supabase_service_role_key="prod-service",
        database_url="postgresql://prod@db/saibyl",
    )
    assert s.environment == "production"


def test_settings_rejects_short_secret_key_in_production():
    import pytest

    from app.core.config import Settings

    with pytest.raises(ValueError):
        Settings(
            environment="production",
            secret_key="too-short",
            anthropic_api_key="sk-prod",
            supabase_url="https://prod.supabase.co",
            supabase_anon_key="prod-anon",
            supabase_service_role_key="prod-service",
            database_url="postgresql://prod@db/saibyl",
        )
