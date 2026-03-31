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
        secret_key="prod-key",
        anthropic_api_key="sk-prod",
        supabase_url="https://prod.supabase.co",
        supabase_anon_key="prod-anon",
        supabase_service_role_key="prod-service",
        database_url="postgresql://prod@db/saibyl",
    )
    assert s.environment == "production"
