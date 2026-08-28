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
    # Opus 5. The migration from 4.6 is NOT a variable change: 4.7+ reject
    # `temperature`/`top_p`/`top_k` with a 400, so `llm_client` had to stop
    # sending them first. See DECISIONS_LOG 2026-08-28.
    llm_model: str = "claude-opus-5"
    # No date suffix. `claude-haiku-4-5` is the complete id; the dated form
    # was a training-data habit, and `model_pricing` only matched it by
    # prefix luck.
    llm_fast_model: str = "claude-haiku-4-5"
    # How hard the model thinks, and the main cost lever on Opus 5.
    #
    # **`medium`, set by the founder on 2026-08-28**, not the API's `high`
    # default. Measured that day: moving 4.6 -> Opus 5 took one website check
    # from $0.65 to $1.22, and output tokens were 79% of that bill — thinking is
    # on by default on Opus 5 and billed as output. Input rose 29% on the
    # tokenizer change and cannot be tuned; output can.
    #
    # The migration guide calls Opus 5 unusually strong at low/medium and names
    # effort the primary cost lever. This is the experiment running in
    # production: if report quality holds, the biggest cost line is cut.
    #
    # **How to tell if it was wrong.** `measured` and `standard` are arithmetic
    # and must not move at all; they returned 66 and 93 across a model change.
    # If those hold and only the vision dimensions drift a few points, that is
    # the +/-10 noise already measured on identical inputs, not degradation.
    #
    # Env var: LLM_EFFORT. One of low | medium | high | xhigh | max.
    llm_effort: str = "medium"
    llm_base_url: str = ""
    supabase_storage_bucket: str = "saibyl-uploads"
    simulation_max_rounds: int = 10
    simulation_worker_concurrency: int = 4
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    resend_api_key: str = ""
    # The From: on anything Saibyl sends. Must be on a domain verified in
    # Resend — until it is, Resend accepts only `onboarding@resend.dev`, and
    # only to the account owner, which looks like working software until the
    # first real founder. Empty means send nothing, by design: see
    # `services/email/sender.email_is_configured`.
    email_from: str = ""
    # Where a founder's reply lands. Optional; without it a reply goes to
    # `email_from`, which may be a no-reply address nobody reads — and the
    # follow-up is a question, so somebody has to be able to answer.
    email_reply_to: str = ""
    uspto_odp_api_key: str = ""
    uspto_tsdr_api_key: str = ""
    sentry_dsn: str = ""
    # Crisis is shelved, not deleted (PRD_V3 §7). Off hides the surface
    # entirely — the API answers 404, not 403 — until it returns as a paid
    # module. Env var: CRISIS_ENABLED.
    crisis_enabled: bool = False
    # The platform owner's org; empty disables the admin routes entirely
    # (they answer 404, like crisis above). Env var: ADMIN_ORGANIZATION_ID.
    admin_organization_id: str = ""
    # How many proxies sit in front of this process, counted from the app.
    #
    # `X-Forwarded-For` is a list each proxy *appends its peer to*, so the
    # right-most entry is written by the proxy nearest us and everything to the
    # left of it is whatever the client typed. Render is one hop, hence 1;
    # putting a CDN in front makes it 2, and the number must move with the
    # deployment or `core/rate_limit` keys on a value somebody else controls.
    # Env var: TRUSTED_PROXY_HOPS.
    trusted_proxy_hops: int = 1

    model_config = {"env_file": ["../.env", ".env"], "env_file_encoding": "utf-8"}


settings = Settings()
