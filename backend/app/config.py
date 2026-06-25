"""Application settings, loaded from environment / .env (pydantic-settings)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # Database — SQLite by default so the app runs with zero external services.
    database_url: str = "sqlite+aiosqlite:///./learning.db"
    pg_ssl: bool = False  # force SSL for Postgres (auto-on when URL has sslmode=require)

    # Auth
    jwt_secret: str = "dev-secret-change-me-in-production-please-32b+"
    jwt_alg: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days

    # LLM provider (pick one; "auto" resolves from whichever key is set)
    llm_provider: str = "auto"  # auto | anthropic | groq | none
    # -- Anthropic (Claude)
    anthropic_api_key: str = ""
    tutor_model: str = "claude-opus-4-8"
    judge_model: str = "claude-haiku-4-5"
    # -- Groq / any OpenAI-compatible endpoint
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_judge_model: str = "llama-3.1-8b-instant"
    openai_base_url: str = "https://api.groq.com/openai/v1"  # override for OpenAI/Together/etc.

    # Optional infra
    redis_url: str = ""

    # Content (blank = use bundled content/, else fall back to ../../learning-path)
    content_dir: str = ""

    # Dev seed account
    seed_email: str = "visakh@local"
    seed_password: str = "learn"

    cors_origins: list[str] = ["*"]

    # ---- derived ----
    @property
    def db_url(self) -> str:
        """Normalize host-provided URLs (Render/Neon give postgres://...) for asyncpg."""
        u = self.database_url
        if u.startswith("postgres://"):
            u = "postgresql://" + u[len("postgres://"):]
        if u.startswith("postgresql://") and "+asyncpg" not in u:
            u = "postgresql+asyncpg://" + u[len("postgresql://"):]
        if u.startswith("postgresql+asyncpg://") and "?" in u:
            u = u.split("?", 1)[0]  # asyncpg rejects libpq query params (sslmode, etc.)
        return u

    @property
    def is_postgres(self) -> bool:
        return self.db_url.startswith("postgresql")

    @property
    def pg_ssl_enabled(self) -> bool:
        raw = self.database_url.lower()
        return self.is_postgres and (self.pg_ssl or "sslmode=require" in raw or "ssl=true" in raw)

    @property
    def resolved_provider(self) -> str:
        lp = self.llm_provider.lower().strip()
        if lp in ("anthropic", "groq", "none"):
            return lp
        if self.groq_api_key.strip():
            return "groq"
        if self.anthropic_api_key.strip():
            return "anthropic"
        return "none"

    @property
    def ai_enabled(self) -> bool:
        return self.resolved_provider not in ("", "none")

    @property
    def content_path(self) -> Path:
        if self.content_dir.strip():
            p = Path(self.content_dir)
            return p if p.is_absolute() else (BACKEND_DIR / p).resolve()
        return (BACKEND_DIR.parent / "content").resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
