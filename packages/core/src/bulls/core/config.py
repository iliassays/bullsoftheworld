"""Application settings, loaded from environment (see .env.example)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The single repo-root .env, resolved absolutely so it loads no matter which service's directory
# the process is launched from (e.g. granian runs from services/api). Real environment variables
# still take precedence over the file.
_ENV_FILE = Path(__file__).resolve().parents[5] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    env: str = "local"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://bulls:bulls@localhost:5433/bulls"
    database_pool_size: int = 10
    database_max_overflow: int = 10
    database_pool_timeout_s: int = 10
    database_statement_timeout_ms: int = 30_000
    redis_url: str = "redis://localhost:6379/0"
    ai_queue_name: str = "arq:ai"
    dse_ingestion_queue_name: str = "arq:ingestion:dse"
    us_ingestion_queue_name: str = "arq:ingestion:us"
    us_research_queue_name: str = "arq:research:us"
    sec_ingestion_queue_name: str = "arq:ingestion:sec"
    us_eod_min_coverage: float = Field(default=0.90, gt=0, le=1)
    us_universe_promotion_enabled: bool = False
    us_market_data_authorization_id: str = ""
    on_demand_research_daily_limit: int = Field(default=5, ge=1, le=50)
    sec_contact_email: str = "hello@bullsofwallst.com"

    # LLM-only features are opt-in. Retrieval embeddings remain local and free when this is disabled.
    ai_provider: Literal["disabled", "ollama", "claude"] = "disabled"

    anthropic_api_key: str = ""
    # Used when ai_provider="claude". Cheaper tier (claude-haiku-4-5) is a cost call you own.
    anthropic_model: str = "claude-opus-4-8"

    # Used when ai_provider="ollama". qwen2.5 / aya are the better multilingual (Bangla) picks.
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5"
    # Retrieval embeddings. "fastembed" is the free local semantic path for production workers.
    # "hash" stays available as the dependency-free fallback; "ollama"/"openai" are opt-in only.
    ai_embedding_provider: Literal["fastembed", "hash", "openai", "ollama"] = "fastembed"
    ai_embedding_model: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
    ai_embedding_dimensions: int = 768
    ai_embedding_api_base_url: str = "https://api.openai.com/v1"
    ai_embedding_api_key: str = ""
    ai_embedding_cache_dir: str = ".cache/fastembed"

    jwt_secret: str = "change-me-in-prod"
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_ttl_min: int = 30  # short-lived by design; the refresh token carries persistence
    refresh_token_ttl_days: int = 60  # rotating opaque token — sliding 60-day sign-in
    refresh_cookie_name: str = "bulls_refresh"
    refresh_cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    @property
    def production_cookies(self) -> bool:
        return self.env.lower() not in {"local", "dev", "development", "test"}

    # Shared token guarding /admin routes (sent as X-Admin-Token). Empty = admin locked.
    admin_token: str = ""

    # Feed moderation (docs/specs/feed-moderation.md). Default-on: clear violations are blocked,
    # gray-zone posts are held for review, and every decision is logged to moderation_events. Set
    # MODERATION_ENFORCE=false only for a deliberate shadow rollout where posts still publish.
    moderation_enforce: bool = True
    # L4 async safety+relevance screen (the LLM layer). OFF by default — it's the only piece that
    # needs an LLM (local Ollama or the Claude API), so it stays disabled on resource-limited servers.
    # L1/L2 deterministic moderation + the review queue run fully without it. Enable when you have
    # capacity, or after switching AI_PROVIDER to the hosted Claude API.
    moderation_l4_enabled: bool = False

    default_tenant: str = "bullsofdhaka"
    strict_tenant_resolution: bool = True

    # CORS origins for the web client (comma-separated in env).
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Email (transactional) ---------------------------------------------
    # Public base URL of the web app, for links in emails (reset/verify).
    app_base_url: str = "http://localhost:5173"
    # Branded sender, e.g. "Bulls of Dhaka <no-reply@bullsofdhaka.com>".
    email_from: str = "Bulls of Dhaka <no-reply@bullsofdhaka.com>"
    # Real, monitored address users can reply to / contact us at (shown in the portal too).
    support_email: str = "hello@bullsofdhaka.com"
    # Where the ops watchdog pages on a health problem (worker down / stale data / API down).
    alert_email: str = ""  # defaults to support_email when blank
    # Replies to transactional mail go here (defaults to support_email when blank).
    email_reply_to: str = ""
    # Preferred: a transactional provider (set RESEND_API_KEY). Falls back to SMTP if set, else logs.
    resend_api_key: str = ""
    smtp_server: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""

    # --- Facebook (page auto-posting) --------------------------------------
    # Permanent Page access token + Page id for the Bulls of Dhaka page.
    fb_page_id: str = ""
    fb_page_token: str = ""
    fb_graph_version: str = "v21.0"

    # --- Generated card images (served by the API, referenced from feed posts) ---
    card_dir: str = "/tmp/bulls-cards"  # writable dir for generated card PNGs
    api_public_url: str = "http://localhost:8090"  # public base the cards are served from
    wallst_api_public_url: str = "https://api.bullsofwallst.com"
    wallst_alert_email: str = ""  # falls back to ALERT_EMAIL, then SUPPORT_EMAIL

    @model_validator(mode="after")
    def validate_production_secrets(self) -> Settings:
        """Refuse to start an internet-facing service with development credentials."""
        if self.ai_embedding_dimensions != 768:
            raise ValueError("AI_EMBEDDING_DIMENSIONS must match the pgvector schema width (768)")
        if self.moderation_l4_enabled and self.ai_provider == "disabled":
            raise ValueError("MODERATION_L4_ENABLED requires a configured LLM provider")
        if self.env.lower() not in {"local", "dev", "development", "test"} and (
            self.jwt_secret == "change-me-in-prod" or len(self.jwt_secret) < 32
        ):
            raise ValueError("JWT_SECRET must be a random value of at least 32 characters")
        if (
            self.env.lower() not in {"local", "dev", "development", "test"}
            and self.ai_embedding_provider == "hash"
        ):
            raise ValueError("AI_EMBEDDING_PROVIDER=hash is not allowed outside local/test")
        return self

    @property
    def email_enabled(self) -> bool:
        return bool(self.resend_api_key or (self.smtp_server and self.smtp_username))

    @property
    def reply_to(self) -> str:
        return self.email_reply_to or self.support_email

    @property
    def fb_enabled(self) -> bool:
        return bool(self.fb_page_id and self.fb_page_token)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached singleton — import this, don't construct Settings() directly."""
    return Settings()
