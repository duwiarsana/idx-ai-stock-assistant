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
    # Chat/group where automated crypto alerts are delivered. Defaults to admin id.
    telegram_chat_id: Optional[str] = None

    # ── LLM ──────────────────────────────────────────
    llm_provider: str = "qwen"  # "qwen" (primary), "groq" (fallback), "gemini" (backup)
    
    # Qwen3.5-397b (Primary - Most Powerful)
    qwen_api_key: str = "qwen"  # Empty for local/opencode
    qwen_base_url: str = "http://localhost:8000/v1"  # Opencode MCP or local
    qwen_model: str = "qwen3.5-397b"
    
    # Groq (Secondary - Fast, Free)
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.3-70b-versatile"
    
    # Gemini (Tertiary - Backup)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # ── Stock Data ───────────────────────────────────
    stock_cache_ttl: int = 300  # 5 minutes
    stock_data_days: int = 90

    # ── Rate Limiting ────────────────────────────────
    rate_limit_per_user: int = 30
    rate_limit_window: int = 60  # seconds

    # ── Crypto Scanner (Tokocrypto) ──────────────────
    crypto_scanner_enabled: bool = True
    crypto_scan_interval_minutes: int = 5
    crypto_scanner_dry_run: bool = False
    # Disable Telegram alert delivery for crypto momentum scans (scanning
    # still runs for the paper-trading engine; only the Telegram report is off).
    crypto_alert_telegram_enabled: bool = True

    # Quote assets to scan, comma separated (e.g. "USDT,IDR")
    crypto_quote_assets: str = "USDT,IDR"
    # Minimum 24h quote volume (in quote currency) to consider a pair liquid.
    # If empty, a sensible default is used (see crypto_scanner).
    crypto_min_quote_volume: Optional[str] = ""

    # Scoring / alert thresholds
    crypto_min_score_alert: int = 75
    crypto_max_candidates_ai: int = 10
    crypto_max_alerts_per_scan: int = 3
    crypto_alert_cooldown_minutes: int = 60

    # Pair filtering
    crypto_stablecoin_quotes: str = "USDT,USDC,BUSD,DAI,TUSD,FRAX,PAX,FDUSD"
    crypto_min_volume_pairs: int = 200
    crypto_max_candles: int = 300

    # HTTP / network
    crypto_api_timeout: int = 30
    crypto_max_concurrency: int = 5
    crypto_max_retries: int = 3

    # Scoring weights (must sum to ~1.0 across positive factors)
    crypto_weight_trend: float = 0.25
    crypto_weight_momentum: float = 0.25
    crypto_weight_volume: float = 0.25
    crypto_weight_breakout: float = 0.25

    # ── Crypto Paper Trading ─────────────────────────
    crypto_paper_trading_enabled: bool = True
    # Virtual starting cash in the paper account (quote asset).
    crypto_paper_initial_balance: float = 1_000_000.0
    # Quote asset used for the paper account (USDT or IDR).
    crypto_paper_quote_asset: str = "USDT"
    # % of available cash allocated per new position.
    crypto_paper_allocation_percent: float = 10.0
    # Max simultaneously open paper positions.
    crypto_paper_max_positions: int = 5
    # Min momentum score to open a position.
    crypto_paper_entry_score: int = 75
    # Require price to be at/recent-high (breakout) before entering.
    crypto_paper_entry_require_breakout: bool = False
    # Require a 1h uptrend (EMA9>EMA20>EMA50 + MACD bullish) before entering.
    crypto_paper_entry_require_uptrend: bool = True
    # Max % above EMA20 for a "pullback entry" (buy the dip, not the top).
    crypto_paper_entry_pullback_max_pct: float = 5.0
    # % of the position sold when TP1 is reached (rest at TP2).
    crypto_paper_sell_pct_at_tp1: float = 50.0
    # Move stop-loss to breakeven after TP1 is filled.
    crypto_paper_move_sl_to_breakeven: bool = True
    # Send Telegram notifications for paper open/close.
    crypto_paper_notify: bool = True
    # Minutes to wait before re-entering a symbol that just hit SL (avoid
    # buying back into a falling knife after a stop-out).
    crypto_paper_sl_cooldown_minutes: int = 120
    # Require a positive AI verdict (STRONG_WATCH / WATCH) before opening a
    # paper position. Candidates already pass the deterministic gate first, so
    # this is an extra quality filter, not a gate. If the AI verdict is missing
    # (AI down / not analysed) the candidate is NOT rejected — the AI is never
    # a single point of failure.
    crypto_paper_ai_filter_enabled: bool = True

    # ── Crypto Real Trading (REAL MONEY — be careful) ─────────
    # When enabled, the scanner opens REAL orders instead of paper positions.
    # Requires a TRADE-only Tokocrypto API key (withdraw must be disabled) and
    # a small allocation per position. Default OFF.
    crypto_real_trading_enabled: bool = False
    crypto_real_api_key: str = ""
    crypto_real_api_secret: str = ""
    # Quote asset to trade (must have available balance).
    crypto_real_quote_asset: str = "USDT"
    # % of available balance allocated per new position (small!).
    crypto_real_allocation_percent: float = 2.0
    # Min order value in quote asset. Orders below the exchange NOTIONAL filter
    # would be rejected, so we skip (never place an order this small).
    crypto_real_min_order_quote: float = 5.0
    # Max simultaneously open real positions.
    crypto_real_max_positions: int = 3
    # Min momentum score to open a real position (higher = more selective).
    crypto_real_entry_score: int = 75
    # Hard safety: stop opening new positions once realized PnL (USDT) drops
    # below this threshold. 0 = disabled.
    crypto_real_max_drawdown: float = 50.0
    # Notify Telegram on every real fill.
    crypto_real_notify: bool = True

    # ── MQTT (ESP32 sound alerts) ─────────────────────
    mqtt_enabled: bool = False
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    # Base topic prefix, e.g. "crypto/trade". Final topics:
    #   <prefix>/buy, <prefix>/profit, <prefix>/loss, <prefix>/heartbeat
    mqtt_topic_prefix: str = "crypto/trade"
    # Seconds between heartbeat "alive" messages.
    mqtt_heartbeat_seconds: int = 60
    # Reconnect / publish timeout.
    mqtt_timeout: float = 5.0

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
