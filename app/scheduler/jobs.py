"""Scheduled background jobs for data updates, scoring, and ML retraining."""

import logging
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pandas as pd
import yfinance as yf

from app.data.ingestion import stock_data_fetcher
from app.services.cache_service import cache_service
from app.services.ai_service import ai_service
from app.services.analysis_engine import analyze as run_analysis
from app.services.scoring_service import scoring_service
from app.services.ml_predictor import ml_predictor
from app.services.stock_service import stock_service
from app.config import get_settings
from telegram import Bot

logger = logging.getLogger(__name__)
settings = get_settings()

# Popular tickers to pre-fetch and analyze for recommendations
POPULAR_TICKERS = [
    "BBCA", "BBRI", "BMRI", "TLKM", "ASII",
    "UNVR", "ICBP", "GOTO", "ADRO", "ANTM",
]

# Fallback extended list if database is empty
ALL_TICKERS = [
    "BBCA", "BBRI", "BMRI", "BBNI", "BRIS",
    "TLKM", "ASII", "UNVR", "ICBP", "INDF",
    "GOTO", "BUKA", "EMTK", "ADRO", "ANTM",
    "PTBA", "INCO", "MDKA", "PGAS", "AKRA",
    "KLBF", "SIDO", "HMSP", "GGRM", "EXCL",
    "ISAT", "TOWR", "MNCN", "SMGR", "CPIN",
    "ACES",
]


async def get_all_active_tickers() -> list[str]:
    """Load all active tickers from the database dynamically."""
    from app.db.session import async_session_factory
    from app.models.stock import Stock
    from sqlalchemy import select
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Stock.ticker).where(Stock.is_active == True)
            )
            tickers = [r for r, in result.all()]
            if tickers:
                return tickers
    except Exception as e:
        logger.error(f"Error loading tickers from database: {e}")
    
    return ALL_TICKERS


async def fetch_batch_histories(tickers: list[str], days: int = 90) -> dict[str, list[dict]]:
    """Download OHLCV history for multiple tickers in parallel batch requests."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    jk_tickers = [f"{t}.JK" if not t.endswith(".JK") else t for t in tickers]
    
    loop = asyncio.get_event_loop()
    try:
        # Run yf.download in executor to avoid blocking the event loop
        df = await loop.run_in_executor(
            None, 
            lambda: yf.download(
                jk_tickers, 
                start=start_date, 
                end=end_date, 
                group_by="ticker", 
                threads=True,
                progress=False
            )
        )
        
        histories = {}
        if len(tickers) == 1:
            ticker = tickers[0]
            df = df.dropna(subset=["Close"])
            if not df.empty:
                histories[ticker] = []
                for idx, row in df.iterrows():
                    histories[ticker].append({
                        "date": idx.strftime("%Y-%m-%d"),
                        "open": float(row.get("Open", 0)),
                        "high": float(row.get("High", 0)),
                        "low": float(row.get("Low", 0)),
                        "close": float(row.get("Close", 0)),
                        "volume": int(row.get("Volume", 0)),
                    })
        else:
            for jk_ticker in jk_tickers:
                ticker = jk_ticker.replace(".JK", "")
                if jk_ticker in df.columns.levels[0]:
                    ticker_df = df[jk_ticker].dropna(subset=["Close"])
                    if not ticker_df.empty:
                        histories[ticker] = []
                        for idx, row in ticker_df.iterrows():
                            histories[ticker].append({
                                "date": idx.strftime("%Y-%m-%d"),
                                "open": float(row.get("Open", 0)),
                                "high": float(row.get("High", 0)),
                                "low": float(row.get("Low", 0)),
                                "close": float(row.get("Close", 0)),
                                "volume": int(row.get("Volume", 0)),
                            })
        return histories
    except Exception as e:
        logger.error(f"Error in batch download: {e}")
        return {}


async def update_popular_stocks():
    """Pre-fetch data for popular stocks (runs every 30 minutes during market hours)."""
    logger.info("📊 Updating popular stock data...")
    for ticker in POPULAR_TICKERS:
        try:
            data = await stock_data_fetcher.fetch_stock_data(ticker)
            if data:
                await cache_service.set_stock_data(ticker, data, ttl=1800)
                logger.debug(f"  Updated {ticker}")
        except Exception as e:
            logger.warning(f"  Failed to update {ticker}: {e}")
    logger.info("✅ Popular stock update complete")


async def daily_scoring_job():
    """Score all tracked tickers and persist results to database.

    Runs after market close (16:30 WIB).
    """
    logger.info("🎯 Running daily scoring for all tracked tickers...")
    tickers = await get_all_active_tickers()
    scored = 0
    failed = 0

    for ticker in tickers:
        try:
            data = await stock_service.get_stock_data(ticker)
            if not data:
                logger.warning(f"  No data for {ticker}")
                failed += 1
                continue

            history = data.get("history", [])
            result = run_analysis(ticker, history)

            if result:
                # Try ML prediction
                technicals = data.get("technicals", {})
                technicals["current_price"] = float(data.get("current_price", 0))
                features = ml_predictor.extract_features(technicals)
                ml_pred = ml_predictor.predict(ticker, features)

                if ml_pred:
                    result.ml_probability = ml_pred.probability
                    result.ml_direction = ml_pred.direction
                    # Combined score: tech × 0.6 + ML × 0.4
                    ml_score = ml_pred.probability * 100
                    result.combined_score = round(
                        result.final_score * 0.6 + ml_score * 0.4, 1
                    )

                # Save to database
                saved = await scoring_service.save_score(result)
                if saved:
                    scored += 1
                else:
                    failed += 1
            else:
                failed += 1

        except Exception as e:
            logger.error(f"  Scoring error for {ticker}: {e}")
            failed += 1

    logger.info(f"✅ Daily scoring complete: {scored} scored, {failed} failed")


async def intraday_scanner_job():
    """Scan all active tickers periodically, identify setups, and send Telegram alerts."""
    if not settings.telegram_admin_id or not settings.telegram_bot_token:
        logger.warning("⚠️ Skipping intraday scan: Admin ID or Bot Token not set")
        return

    logger.info("⚡ Running intraday periodic scanner...")
    tickers = await get_all_active_tickers()
    bot = Bot(token=settings.telegram_bot_token)
    
    # 1. Download in batches of 150 to be fast and safe
    batch_size = 150
    all_histories = {}
    
    logger.info(f"Downloading histories for {len(tickers)} tickers in batches...")
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        logger.info(f"  Downloading batch {i//batch_size + 1}/{(len(tickers)-1)//batch_size + 1} ({len(batch)} tickers)")
        batch_hist = await fetch_batch_histories(batch)
        all_histories.update(batch_hist)
        await asyncio.sleep(1) # Small delay between batches to respect Yahoo Finance limits
        
    logger.info(f"Downloaded histories for {len(all_histories)} tickers. Analyzing potential setups...")
    
    # 2. Process and filter tickers in memory
    for ticker, history in all_histories.items():
        try:
            if len(history) < 20:
                continue

            cooldown_key = f"alert_cooldown:{ticker}"
            # Check Redis cooldown
            if await cache_service.redis.get(cooldown_key):
                continue

            # Calculate technical indicators
            technicals = stock_service._calculate_technicals(history)
            if "error" in technicals:
                continue

            current_price = float(history[-1]["close"])
            avg_vol = float(technicals.get("avg_volume_20d", 0))
            daily_value = avg_vol * current_price
            
            # Liquidity filter: Avg Volume 20D * Current Price >= 1,000,000,000 IDR (1 Billion)
            if daily_value < 1_000_000_000:
                continue

            # Run analysis engine rules
            analysis = run_analysis(ticker, history)
            
            # Signal criteria: Technical Score >= 70 and BUY signal
            if analysis and analysis.final_score >= 70 and analysis.signal == "BUY":
                # Fetch AI analysis text
                ai_res = await ai_service.analyze_stock(ticker)
                narrative = "Analisis AI tidak tersedia."
                if isinstance(ai_res, dict):
                    narrative = ai_res.get("analysis", narrative)
                elif isinstance(ai_res, str):
                    narrative = ai_res

                entry_low = analysis.entry_zone.get("low", current_price)
                entry_high = analysis.entry_zone.get("high", current_price)
                
                message = (
                    f"🚨 **IDX AI POTENTIAL SIGNAL DETECTED** 🚨\n\n"
                    f"Ticker: **{ticker}.JK**\n"
                    f"Technical Score: **{analysis.final_score:.1f}/100**\n"
                    f"Trend: **{analysis.trend_status}**\n\n"
                    f"💵 **Entry Area**: Rp {entry_low:,.0f} - Rp {entry_high:,.0f}\n"
                    f"🎯 **Target Profit (TP1)**: Rp {analysis.take_profit:,.0f}\n"
                    f"🛑 **Stop Loss (SL)**: Rp {analysis.stop_loss:,.0f}\n"
                    f"⚖️ **Risk Reward**: 1:{analysis.risk_reward_ratio:.1f}\n\n"
                    f"📝 **Alasan AI**:\n{narrative}\n\n"
                    f"⚠️ *Disclaimer: Bukan ajakan beli. Gunakan manajemen risiko pribadi.*"
                )
                
                await bot.send_message(
                    chat_id=settings.telegram_admin_id,
                    text=message,
                    parse_mode="Markdown"
                )
                logger.info(f"✅ Instantly alerted potential buy signal for {ticker}")
                
                # Set 24 hour cooldown (86400 seconds)
                await cache_service.redis.setex(cooldown_key, 86400, "sent")
                
        except Exception as e:
            logger.error(f"Error scanning {ticker} in intraday: {e}")

    logger.info("✅ Intraday periodic scanner complete.")


async def daily_market_recommendations():
    """Analyze market and send top recommendations to admin.

    Uses the scoring engine for deterministic rankings.
    """
    if not settings.telegram_admin_id or not settings.telegram_bot_token:
        logger.warning("⚠️ Skipping recommendations: Admin ID or Bot Token not set")
        return

    logger.info("🤖 Generating daily market recommendations...")
    bot = Bot(token=settings.telegram_bot_token)

    # Get today's top scores from database
    top_scores = await scoring_service.get_latest_scores(limit=5)

    if not top_scores:
        # Fallback: run scoring inline for popular tickers
        for ticker in POPULAR_TICKERS[:5]:
            try:
                data = await stock_service.get_stock_data(ticker)
                if data:
                    history = data.get("history", [])
                    result = run_analysis(ticker, history)
                    if result:
                        top_scores.append({
                            "ticker": ticker,
                            "name": data.get("name", "Unknown"),
                            "score": result.final_score,
                            "signal": result.signal,
                            "confidence": result.confidence,
                            "trend": result.trend_status,
                        })
            except Exception as e:
                logger.error(f"Error scoring {ticker} for recommendations: {e}")

    if not top_scores:
        return

    # Build message
    message = "🌟 **Rekomendasi Saham Harian IDX AI** 🌟\n\n"
    message += "Peringkat berdasarkan skor analisis teknikal:\n\n"

    for i, rec in enumerate(top_scores, 1):
        conf_emoji = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "⚪"}.get(rec.get("confidence", ""), "⚪")
        signal_emoji = {"BUY": "📈", "SELL": "📉", "HOLD": "⏸"}.get(rec.get("signal", ""), "⏸")

        message += (
            f"{i}. {conf_emoji} **{rec['ticker']}** — {rec.get('name', 'N/A')}\n"
            f"   {signal_emoji} Score: {rec.get('score', 0):.1f}/100 | "
            f"Signal: {rec.get('signal', 'N/A')} | "
            f"Trend: {rec.get('trend', 'N/A')}\n\n"
        )

    message += "💡 *Ketik /analyze <TICKER> untuk detail lengkap.*\n\n"
    message += "⚠️ *Bukan saran investasi. Lakukan riset mandiri.*"

    try:
        await bot.send_message(
            chat_id=settings.telegram_admin_id,
            text=message,
            parse_mode="Markdown"
        )
        logger.info(f"✅ Daily recommendations sent to {settings.telegram_admin_id}")
    except Exception as e:
        logger.error(f"Failed to send recommendations: {e}")


async def weekly_ml_retrain():
    """Retrain the ML model with latest data (runs weekly on Sunday).

    Collects all history data from tracked tickers and trains the model.
    """
    logger.info("🤖 Starting weekly ML model retraining...")
    tickers = await get_all_active_tickers()
    histories = {}
    
    for ticker in tickers:
        try:
            data = await stock_data_fetcher.fetch_stock_data(ticker, days=365)
            if data:
                histories[ticker] = data.get("history", [])
        except Exception as e:
            logger.warning(f"  Failed to fetch history for {ticker}: {e}")

    if len(histories) < 5:
        logger.warning("Not enough ticker data for ML training")
        return

    result = ml_predictor.train(histories)
    if "error" in result:
        logger.warning(f"ML training issue: {result['error']}")
    else:
        logger.info(
            f"✅ ML model retrained: accuracy={result.get('accuracy', 0):.2%}, "
            f"samples={result.get('samples', 0)}"
        )

    # Notify admin
    if settings.telegram_admin_id and settings.telegram_bot_token:
        try:
            bot = Bot(token=settings.telegram_bot_token)
            msg = (
                "🤖 **ML Model Update**\n\n"
                f"Accuracy: {result.get('accuracy', 0):.2%}\n"
                f"Training samples: {result.get('samples', 0)}\n"
                f"Experimental: {'Yes' if result.get('is_experimental') else 'No'}\n"
            )
            if "feature_importance" in result:
                msg += "\nFeature Importance:\n"
                for feat, imp in sorted(
                    result["feature_importance"].items(), key=lambda x: -x[1]
                ):
                    msg += f"  • {feat}: {imp:.1%}\n"

            await bot.send_message(
                chat_id=settings.telegram_admin_id,
                text=msg,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Failed to notify admin about ML training: {e}")


async def daily_cleanup():
    """Clean up old cache entries (runs daily at midnight WIB)."""
    logger.info("🧹 Running daily cleanup...")
    # Future: clean old analysis_history entries, expired sessions, etc.
    logger.info("✅ Daily cleanup complete")


async def crypto_scan_job():
    """Run the Tokocrypto momentum scanner (interval-based)."""
    if not settings.crypto_scanner_enabled:
        logger.info("⏭️ Crypto scanner disabled (CRYPTO_SCANNER_ENABLED=false), skipping job")
        return
    try:
        from app.services.crypto_scanner import crypto_scanner
        summary = await crypto_scanner.run_scan()
        if summary.get("status") != "ok":
            logger.error(f"Crypto scan job failed: {summary}")
    except Exception as e:
        logger.exception(f"Crypto scan job raised: {e}")


async def crypto_real_tp_sl_check():
    """Quick TP/SL check for real crypto positions - runs every 30 seconds."""
    if not settings.crypto_real_trading_enabled:
        logger.debug("Crypto real trading disabled, skipping TP/SL check")
        return
    
    try:
        from app.services.crypto_real import real_trader
        from app.db.session import async_session_factory
        
        async with async_session_factory() as session:
            closed = await real_trader.check_tp_sl_quick(session)
            if closed > 0:
                logger.info(f"⚡ Crypto real TP/SL: {closed} positions closed")
            else:
                logger.debug("⚡ Crypto real TP/SL check: no exits needed")
    except Exception as e:
        logger.error(f"Crypto real TP/SL check failed: {e}", exc_info=True)


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the job scheduler."""
    print("🚀🚀🚀 DEBUG: create_scheduler() STARTED")
    scheduler = AsyncIOScheduler(timezone="Asia/Jakarta")

    # Update popular stocks every 30 min during market hours (Mon-Fri, 09:00-16:00 WIB)
    try:
        scheduler.add_job(
            update_popular_stocks,
            CronTrigger(
                day_of_week="mon-fri",
                hour="9-15",
                minute="*/30",
                timezone="Asia/Jakarta",
            ),
            id="update_popular_stocks",
            name="Update Popular Stocks",
            replace_existing=True,
        )
        print("✅ update_popular_stocks scheduled")
    except Exception as e:
        print(f"❌ ERROR scheduling update_popular_stocks: {e}")

    # Daily scoring at 16:30 WIB (after market close)
    try:
        scheduler.add_job(
            daily_scoring_job,
            CronTrigger(
                day_of_week="mon-fri",
                hour=16,
                minute=30,
                timezone="Asia/Jakarta",
            ),
            id="daily_scoring",
            name="Daily Stock Scoring",
            replace_existing=True,
        )
        print("✅ daily_scoring scheduled")
    except Exception as e:
        print(f"❌ ERROR scheduling daily_scoring: {e}")

    # Intraday scanner every hour during market hours (Mon-Fri, 09:00-15:00 WIB)
    scheduler.add_job(
        intraday_scanner_job,
        CronTrigger(
            day_of_week="mon-fri",
            hour="9-15",
            minute="0",
            timezone="Asia/Jakarta",
        ),
        id="intraday_scanner",
        name="Intraday Periodic Scanner",
        replace_existing=True,
    )

    # Daily recommendations at 08:30 WIB before market open
    scheduler.add_job(
        daily_market_recommendations,
        CronTrigger(hour=8, minute=30, timezone="Asia/Jakarta"),
        id="daily_recommendations",
        name="Daily Market Recommendations",
        replace_existing=True,
    )

    # Weekly ML retraining on Sunday at 02:00 WIB
    scheduler.add_job(
        weekly_ml_retrain,
        CronTrigger(
            day_of_week="sun",
            hour=2,
            minute=0,
            timezone="Asia/Jakarta",
        ),
        id="weekly_ml_retrain",
        name="Weekly ML Model Retraining",
        replace_existing=True,
    )

    # Daily cleanup at midnight WIB
    scheduler.add_job(
        daily_cleanup,
        CronTrigger(hour=0, minute=0, timezone="Asia/Jakarta"),
        id="daily_cleanup",
        name="Daily Cleanup",
        replace_existing=True,
    )

    # Crypto scanner (Tokocrypto) — interval based, enabled via config
    if settings.crypto_scanner_enabled:
        from apscheduler.triggers.interval import IntervalTrigger
        scheduler.add_job(
            crypto_scan_job,
            IntervalTrigger(
                minutes=max(1, settings.crypto_scan_interval_minutes),
                timezone="Asia/Jakarta",
            ),
            id="crypto_scanner",
            name="Crypto Scanner (Tokocrypto)",
            replace_existing=True,
        )
        logger.info(f"Crypto scanner scheduled every {settings.crypto_scan_interval_minutes} minutes")
    
    # Crypto real TP/SL check - runs every 30 seconds for fast exits
    print(f"🔥🔥🔥 DEBUG: crypto_real_trading_enabled = {settings.crypto_real_trading_enabled}")
    try:
        logger.info(f"DEBUG: Checking crypto_real_trading_enabled = {settings.crypto_real_trading_enabled}")
        if settings.crypto_real_trading_enabled:
            from apscheduler.triggers.interval import IntervalTrigger
            scheduler.add_job(
                crypto_real_tp_sl_check,
                IntervalTrigger(
                    seconds=30,
                    timezone="Asia/Jakarta",
                ),
                id="crypto_real_tp_sl_check",
                name="Crypto Real TP/SL Quick Check",
                replace_existing=True,
            )
            logger.info("✅ Crypto real TP/SL quick check scheduled every 30 seconds")
            print("✅✅✅ Crypto real TP/SL check SCHEDULED")
            
            # Verify job was added
            jobs = scheduler.get_jobs()
            tp_sl_jobs = [j for j in jobs if 'TP/SL' in j.name]
            print(f"📋 Verified {len(tp_sl_jobs)} TP/SL jobs in scheduler")
        else:
            logger.warning("⚠️ Crypto real TP/SL check DISABLED (crypto_real_trading_enabled=false)")
            print("❌❌❌ Crypto real TP/SL check DISABLED")
    except Exception as e:
        logger.error(f"Failed to setup crypto real TP/SL check: {e}", exc_info=True)
        print(f"💥💥💥 ERROR setting up TP/SL check: {e}")
        import traceback
        traceback.print_exc()

    return scheduler
