"""Application settings, loaded from environment (see .env.example)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

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
    redis_url: str = "redis://localhost:6379/0"

    # AI provider: "ollama" (free, local) or "claude" (Anthropic API). Same code path either way.
    ai_provider: str = "ollama"

    anthropic_api_key: str = ""
    # Used when ai_provider="claude". Cheaper tier (claude-haiku-4-5) is a cost call you own.
    anthropic_model: str = "claude-opus-4-8"

    # Used when ai_provider="ollama". qwen2.5 / aya are the better multilingual (Bangla) picks.
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5"

    jwt_secret: str = "change-me-in-prod"
    jwt_algorithm: str = "HS256"
    access_token_ttl_min: int = 60

    # Shared token guarding /admin routes (sent as X-Admin-Token). Empty = admin locked.
    admin_token: str = ""

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
