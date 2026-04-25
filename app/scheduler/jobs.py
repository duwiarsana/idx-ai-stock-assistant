"""Scheduled background jobs for data updates, scoring, and ML retraining."""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

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

# Extended list for full scoring (all tracked tickers)
ALL_TICKERS = [
    "BBCA", "BBRI", "BMRI", "BBNI", "BRIS",
    "TLKM", "ASII", "UNVR", "ICBP", "INDF",
    "GOTO", "BUKA", "EMTK", "ADRO", "ANTM",
    "PTBA", "INCO", "MDKA", "PGAS", "AKRA",
    "KLBF", "SIDO", "HMSP", "GGRM", "EXCL",
    "ISAT", "TOWR", "MNCN", "SMGR", "CPIN",
    "ACES",
]


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
    scored = 0
    failed = 0

    for ticker in ALL_TICKERS:
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

    histories = {}
    for ticker in ALL_TICKERS:
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


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the job scheduler."""
    scheduler = AsyncIOScheduler(timezone="Asia/Jakarta")

    # Update popular stocks every 30 min during market hours (Mon-Fri, 09:00-16:00 WIB)
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

    # Daily scoring at 16:30 WIB (after market close)
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

    return scheduler
