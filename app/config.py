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
    
    # Groq (Secondary - Fast, Free). Model must exist on the account; as of
    # 2026-09 the llama-3.3-70b-versatile model no longer exists → switched to
    # gpt-oss-120b (best reasoning; ~$0.36/M input + $1.0/M output tokens).
    # Cheaper alt: qwen/qwen3.8-27b.
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "openai/gpt-oss-120b"
    
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

    # ── Freqtrade-style liquidity filters (scanner) ──────────────────
    # Spread filter: skip pairs whose best-bid/best-ask spread exceeds the
    # tolerance (%). A wide spread means a market order pays heavy slippage —
    # exactly what momentum entries on low-liquidity pairs suffer from.
    # The 24h ticker already carries bidPrice/askPrice (no extra API call).
    crypto_spread_filter_enabled: bool = True
    crypto_spread_max_pct: float = 0.5

    # Volume consistency filter: reject pairs whose recent volume is dominated
    # by a single candle spike (pump & dump) instead of being spread evenly
    # across the window. Checked on the last N hours of 1h candles AND the
    # equivalent 15m window. A candle fails if BOTH conditions hold in the same
    # window: spike_ratio (max/median volume) above the max AND the single
    # candle's share of the total window volume above the max share.
    crypto_volume_consistency_enabled: bool = True
    crypto_volume_consistency_window_hours: int = 24
    crypto_volume_consistency_max_spike_ratio: float = 3.0
    crypto_volume_consistency_max_single_share: float = 0.35
    # Ignore windows with fewer bars than this (too little history to judge).
    crypto_volume_consistency_min_bars: int = 12

    # HTTP / network
    crypto_api_timeout: int = 30
    crypto_max_concurrency: int = 5
    crypto_max_retries: int = 3

    # Scoring weights (must sum to ~1.0 across positive factors)
    # Trend is king: higher weight = only strong trend setups score well
    crypto_weight_trend: float = 0.35
    crypto_weight_momentum: float = 0.20
    crypto_weight_volume: float = 0.25
    crypto_weight_breakout: float = 0.20

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
    crypto_paper_entry_pullback_max_pct: float = 8.0  # was 5.0 → wider to catch more valid setups
    # % of the position sold when TP1 is reached (rest at TP2).
    # Backtest (60d × 12 liquid symbols) showed ANY partial sell at TP1 (25/50/75%)
    # CUTS expectancy (+0.59% → +0.47%/trade) vs a full close at TP1: riders that
    # miss TP2 drift back into the SL and turnover drops. So the default is a full
    # close (100). Set <100 to re-enable the partial-TP1 ride.
    crypto_paper_sell_pct_at_tp1: float = 100.0
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

    # ── Crypto AI analysis depth ───────────────────────
    # Number of most recent closes per timeframe to include in the LLM prompt.
    # Higher = richer context (trend structure, swing levels) but more input
    # tokens per scan. 0 = compact summary only (cheapest, original behaviour).
    crypto_ai_candle_lookback: int = 200

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
    # Minimum POSITION value in quote asset when opening. Must sit comfortably
    # ABOVE the exchange NOTIONAL minimum: sizing right at the exchange minimum
    # means fees + a tiny adverse move push the position below the sellable
    # threshold ("dust trap" — the position becomes impossible to close).
    crypto_real_min_position_quote: float = 7.0
    # Max simultaneously open real positions (focused on top 3 setups for higher position size).
    crypto_real_max_positions: int = 3
    # Min momentum score to open a real position (higher = more selective).
    # Backtest and 327 real trade review showed score >= 78 generates consistent positive PnL (+5.8 USDT),
    # while sub-78 setups account for >80% of net negative trades.
    crypto_real_entry_score: int = 78
    # Hard safety: stop opening new positions once realized PnL (USDT) drops
    # below this threshold. 0 = disabled.
    crypto_real_max_drawdown: float = 50.0
    # Notify Telegram on every real fill.
    crypto_real_notify: bool = True
    # % of the position sold when TP1 is reached (the rest keeps riding the
    # trailing stop toward TP2). Mirror of crypto_paper_sell_pct_at_tp1. Backtest
    # showed partial TP1 cuts expectancy, so default 100 = full close at TP1.
    # Set <100 to re-enable the partial-TP1 ride.
    crypto_real_sell_pct_at_tp1: float = 100.0

    # Real trading entry gate (stricter than paper)
    crypto_real_entry_require_uptrend: bool = True
    crypto_real_entry_require_breakout: bool = False
    # Max allowed distance (%) above EMA20 for pullback entry. Stricter (1.5%) so we only buy
    # near support, ensuring our stop-loss sits safely below support instead of hanging mid-air.
    crypto_real_entry_pullback_max_pct: float = 1.5
    crypto_real_entry_min_risk_reward: float = 1.5  # minimum R:R ratio
    crypto_real_entry_max_atr_pct: float = 5.0  # max ATR% to avoid high volatility
    crypto_real_sl_cooldown_minutes: int = 180  # 3 hours cooldown after SL
    # Trailing-stop distance multiplier (×ATR). Data review (111 closed REAL):
    # 52 SL exits averaged only -1.24% and 5 exited while still ABOVE entry —
    # the trailing stop was too tight (1.2×ATR) and cut winners before they
    # could reach TP1 (+1.8%). A larger multiplier lets price breathe toward TP1
    # instead of stopping out on the first pullback. Tune via backtest.
    crypto_real_trailing_mult: float = 2.2
    # Floor (×entry price) for the trailing distance, so very low-ATR coins
    # still get a meaningful cushion. Used as max(trailing_mult*ATR, this).
    crypto_real_trailing_min_pct: float = 2.0
    # SL "wick guard": % below the effective stop-loss that price must actually
    # trade under before the SL fires. A single ticker snapshot can print a
    # momentary wick past SL that then recovers — executing a market sell on
    # that print locks in a loss for no reason. With 0.5, price must be
    # genuinely 0.5%+ UNDER the stop before we exit (real breakdowns still
    # caught on the next 30s quick-check). 0 = disable (exit instantly).
    crypto_real_sl_exit_tolerance_pct: float = 0.5
    # Maximum allowed initial stop-loss % below entry (hard cap).
    # Prevents catastrophic wide stops (e.g. -8% to -10%) when 24h recent swing low is very deep.
    # Backtest & trade history review showed capping initial SL at 3.0% eliminates >60% of gross loss.
    crypto_real_max_sl_pct: float = 3.0
    # Stale position timeout cut: if a position has been held >= N hours and remains
    # in negative territory (floating loss >= stale_loss_pct), close it early instead of
    # letting it slowly drift into a full stop-loss over 10-24 hours. (Winners resolve in ~4h).
    crypto_real_stale_timeout_hours: float = 5.0
    crypto_real_stale_loss_pct: float = 1.0
    # ── Auto BEP (Break-Even Point) ──────────────────────────────────
    # When enabled, once peak profit touches bep_trigger_pct (or 50% towards TP1),
    # SL is automatically raised to at least entry * (1 + bep_buffer_pct/100) for LONG
    # or entry * (1 - bep_buffer_pct/100) for SHORT.
    crypto_real_bep_enabled: bool = True
    # Profit % above entry needed to trigger auto-BEP (default 1.8% or 50% to TP1).
    # Must comfortably exceed round-trip fees (1.00%).
    crypto_real_bep_trigger_pct: float = 1.8
    # Dynamic offset % to cover round-trip fee (1.00%) + profit buffer (0.20%).
    # Total offset 1.20% ensures positions stopped out at BEP remain safely net-profitable.
    crypto_real_bep_buffer_pct: float = 1.20

    # ── Exchange Fees ────────────────────────────────────────────────
    # Tokocrypto / Indonesian crypto fee is ~0.4044% per side (including PPh/ICEx).
    # Setting 0.005 (0.50% per side, 1.00% round-trip) provides a realistic conservative
    # buffer covering trading fees, taxes, and minor market order slippage.
    crypto_real_fee_rate: float = 0.005

    # ── Freqtrade-style exits: trailing stop + dynamic ROI ────────────
    # Trailing master switch. True = legacy behaviour (trail from entry at the
    # ATR/min% distance below the peak). False = trailing off entirely; exits
    # purely on the static stop_loss.
    crypto_real_trailing_enabled: bool = True
    # Only start trailing once floating profit reaches this % (Freqtrade
    # "trailing_only_offset_is_reached"). 0 = trail from entry (legacy).
    # E.g. 2.0 → SL only starts moving after price is +2% above entry.
    crypto_real_trailing_only_after_pct: float = 2.0
    # Trailing distance as % of the highest price, used AFTER the trigger
    # (Freqtrade "trailing_stop_positive"). 0 = keep the max(ATR×mult, entry×%)
    # distance above. E.g. 1.5 → stop sits 1.5% below the peak.
    crypto_real_trailing_pct: float = 1.5

    # Dynamic ROI exit (Freqtrade "minimal_roi"): time-based early exit so stale
    # thin-profit positions release capital instead of waiting for a full TP.
    # The tiers were relaxed (higher thresholds / later) so a position isn't
    # force-sold at +0.5% before it can reach TP1 (>=3.5%). It still frees
    # capital from truly stale positions without hurting the TP goal.
    crypto_real_dynamic_roi_enabled: bool = True
    # Tiers as "open_minutes:min_profit_pct,..." e.g. "60:1.2,120:0.8,240:0.5". Exit
    # when position age ≥ minutes AND floating profit ≥ percent (time-ANDed per
    # tier; the first tier whose age is reached applies). Empty string → fall
    # back to the single (min, percent) pair below.
    crypto_real_dynamic_roi_tiers: str = "120:1.5,240:1.0,480:0.75"
    crypto_real_dynamic_roi_min: int = 120
    crypto_real_dynamic_roi_percent: float = 1.5
    # Require a short-term (15m) recovery confirmation before entry: reject
    # candidates whose 15m is still bearish. This stops the engine from buying
    # a pullback that is still heading down (falling knife) — we only enter
    # once the 15m momentum has turned up/neutral. True default.
    crypto_real_entry_confirm_15m: bool = True
    # BTC Market Trend Guard: reject altcoin entry if BTC 1h or 15m is strongly bearish.
    # When BTC dumps, virtually all altcoins follow and hit SL. True default.
    crypto_btc_filter_enabled: bool = True
    # Base symbols never traded by the real engine: stablecoins / pegged assets /
    # gold tokens / wrapped-staked assets. Their price is flat by design so TP/SL
    # levels are meaningless and taker fees guarantee a slow loss. Comma-separated
    # list of BASE symbols (the part before the "_USDT" suffix).
    crypto_real_symbol_blacklist: str = (
        "USD1,USDC,FDUSD,TUSD,USDP,DAI,USDS,USDE,FRAX,PYUSD,EURI,AEUR,XUSD,BFUSD,"
        "U,RLUSD,PAXG,XAUT,WBETH,BNSOL,WBTC,WETH,WBNB,STETH,WSTETH,RETH,CBETH,"
        "FET,BIO,TRX,LUNC"
    )

    # ── Crypto Dust Report ────────────────────────────
    # Weekly read-only wallet inventory. Dust = balances below the exchange
    # minimum notional that can never be sold individually (fee leftovers,
    # old SL_DUST positions, pegged assets bought before the blacklist).
    # The report only lists them and points to the exchange's
    # "Convert Small Balance" feature — it never places orders.
    crypto_dust_report_enabled: bool = True
    # CronTrigger day_of_week (mon..sun) and hour in WIB.
    crypto_dust_report_day: str = "sun"
    crypto_dust_report_hour: int = 8

    # ── IDX Intraday Alerts ───────────────────────────
    # Alert gate for the hourly intraday scanner (09:00-15:00 WIB, Mon-Fri).
    # A loose gate (score>=55) produced 100+ alerts/hour — everything looked
    # like a BUY. Keep these strict so alerts stay meaningful.
    idx_alert_min_score: int = 68
    idx_alert_min_risk_reward: float = 1.5
    idx_alert_max_per_run: int = 10

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

    # ── Dashboard Authentication ──────────────────────
    dashboard_auth_enabled: bool = True
    dashboard_username: str = "duwiarsana"
    dashboard_password: str = "bait695mash215"

    # ── Trade Stats Display Offset ───────────────────
    # Number of historical trade records to offset/deduct from stats display (Telegram & Dashboard)
    crypto_trade_stats_offset: int = 100

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
