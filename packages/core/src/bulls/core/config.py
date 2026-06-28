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

    # --- Email (transactional) ---------------------------------------------
    # Public base URL of the web app, for links in emails (reset/verify).
    app_base_url: str = "http://localhost:5173"
    # Branded sender, e.g. "Bulls of Dhaka <no-reply@bullsofdhaka.com>".
    email_from: str = "Bulls of Dhaka <no-reply@bullsofdhaka.com>"
    # Real, monitored address users can reply to / contact us at (shown in the portal too).
    support_email: str = "hello@bullsofdhaka.com"
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
