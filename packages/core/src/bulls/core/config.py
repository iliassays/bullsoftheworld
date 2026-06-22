"""Application settings, loaded from environment (see .env.example)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "local"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://bulls:bulls@localhost:5433/bulls"
    redis_url: str = "redis://localhost:6379/0"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    jwt_secret: str = "change-me-in-prod"
    jwt_algorithm: str = "HS256"
    access_token_ttl_min: int = 60

    default_tenant: str = "bullsofdhaka"

    # CORS origins for the web client (comma-separated in env).
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached singleton — import this, don't construct Settings() directly."""
    return Settings()
