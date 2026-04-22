"""IDX AI Stock Assistant - Application Configuration."""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ── Application ──────────────────────────────────
    app_name: str = "IDX AI Stock Assistant"
    app_env: str = "development"
    debug: bool = True
    log_level: str = "INFO"

    # ── Database ─────────────────────────────────────
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "idx_ai"
    postgres_user: str = "idx_ai_user"
    postgres_password: str = "change_me_in_production"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        """Sync URL for Alembic migrations."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ── Redis ────────────────────────────────────────
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # ── Telegram ─────────────────────────────────────
    telegram_bot_token: str = ""
    telegram_webhook_url: str = ""
    telegram_use_webhook: bool = False
    telegram_admin_id: Optional[str] = None

    # ── LLM ──────────────────────────────────────────
    llm_provider: str = "gemini"  # "gemini", "deepseek", or "ollama"
    
    # Gemini (Native support)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # DeepSeek (OpenAI-compatible)
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # Groq (OpenAI-compatible)
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.3-70b-versatile"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma2:9b"

    # ── Stock Data ───────────────────────────────────
    stock_cache_ttl: int = 300  # 5 minutes
    stock_data_days: int = 90

    # ── Rate Limiting ────────────────────────────────
    rate_limit_per_user: int = 30
    rate_limit_window: int = 60  # seconds

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
