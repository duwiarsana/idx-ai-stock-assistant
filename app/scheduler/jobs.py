"""Scheduled background jobs for data updates."""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.data.ingestion import stock_data_fetcher
from app.services.cache_service import cache_service
from app.services.ai_service import ai_service
from app.config import get_settings
from telegram import Bot

logger = logging.getLogger(__name__)
settings = get_settings()

# Popular tickers to pre-fetch and analyze for recommendations
POPULAR_TICKERS = [
    "BBCA", "BBRI", "BMRI", "TLKM", "ASII",
    "UNVR", "ICBP", "GOTO", "ADRO", "ANTM",
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


async def daily_market_recommendations():
    """Analyze market and send top 3 recommendations to admin (runs daily before market open)."""
    if not settings.telegram_admin_id or not settings.telegram_bot_token:
        logger.warning("⚠️ Skipping recommendations: Admin ID or Bot Token not set")
        return

    logger.info("🤖 Generating daily market recommendations...")
    bot = Bot(token=settings.telegram_bot_token)
    
    recommendations = []
    
    # Analyze the popular tickers
    for ticker in POPULAR_TICKERS[:5]: # Analyze top 5 for speed
        try:
            analysis = await ai_service.analyze_stock(ticker)
            recommendations.append(analysis)
        except Exception as e:
            logger.error(f"Error analyzing {ticker} for recommendations: {e}")

    if not recommendations:
        return

    # Create a summary message
    message = "🌟 **Rekomendasi Saham Harian IDX AI** 🌟\n\n"
    message += "Berikut adalah ringkasan analisis untuk saham populer hari ini:\n\n"
    
    for rec in recommendations:
        summary = rec.get("data_summary", {})
        message += f"🔹 **{rec['ticker']}** ({rec['company_name']})\n"
        message += f"   • Harga: Rp {summary.get('price', 0):,.0f}\n"
        message += f"   • Tren: {summary.get('trend_5d', 'N/A')}\n"
        message += f"   • RSI: {summary.get('rsi', 'N/A')}\n\n"
    
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

    # Daily recommendations at 08:30 WIB before market open
    scheduler.add_job(
        daily_market_recommendations,
        CronTrigger(hour=8, minute=30, timezone="Asia/Jakarta"),
        id="daily_recommendations",
        name="Daily Market Recommendations",
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
