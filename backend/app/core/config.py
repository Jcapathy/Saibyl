from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    environment: Literal["development", "staging", "production"] = "development"
    secret_key: str = ""

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str, info) -> str:
        env = info.data.get("environment", "development")
        if env in ("production", "staging") and len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters in production/staging")
        return v
    anthropic_api_key: str = ""
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    database_url: str = ""
    redis_url: str = "redis://localhost:6379"
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:3000"
    llm_provider: str = "anthropic"
    llm_model: str = "claude-opus-4-7"
    llm_fast_model: str = "claude-haiku-4-5-20251001"
    llm_base_url: str = ""
    supabase_storage_bucket: str = "saibyl-uploads"
    simulation_max_rounds: int = 10
    simulation_worker_concurrency: int = 4
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    resend_api_key: str = ""
    sentry_dsn: str = ""

    model_config = {"env_file": ["../.env", ".env"], "env_file_encoding": "utf-8"}


settings = Settings()
