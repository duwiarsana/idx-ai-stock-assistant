"""Telegram bot — main entry point.

Run standalone: python -m app.bot.telegram_bot
"""

import asyncio
import logging
import sys
import os

# Add project root to path when running standalone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

from app.config import get_settings
from app.bot.handlers.start import start_handler, help_handler
from app.bot.handlers.stock import stock_handler
from app.bot.handlers.analyze import analyze_handler
from app.bot.handlers.nlp import nlp_handler
from app.bot.middleware import error_handler, rate_limit_middleware
from app.scheduler.jobs import create_scheduler

logger = logging.getLogger(__name__)
settings = get_settings()

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


async def post_init(application: Application) -> None:
    """Set up bot commands menu after initialization."""
    commands = [
        BotCommand("start", "Mulai menggunakan bot"),
        BotCommand("help", "Tampilkan bantuan"),
        BotCommand("stock", "Cek harga saham (contoh: /stock BBCA)"),
        BotCommand("analyze", "Analisis AI saham (contoh: /analyze BBCA)"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("✅ Bot commands menu set up")


def create_bot() -> Application:
    """Create and configure the Telegram bot application."""
    if not settings.telegram_bot_token:
        logger.error("❌ TELEGRAM_BOT_TOKEN not set!")
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

    # Build application
    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(30)
        .build()
    )

    # Register handlers (order matters!)
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("stock", stock_handler))
    app.add_handler(CommandHandler("s", stock_handler))  # shortcut
    app.add_handler(CommandHandler("analyze", analyze_handler))
    app.add_handler(CommandHandler("a", analyze_handler))  # shortcut

    # Handle plain text messages with NLP
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, nlp_handler)
    )

    # Error handler
    app.add_error_handler(error_handler)

    logger.info("✅ Telegram bot configured")
    return app


async def main():
    """Run the bot with polling (development mode)."""
    logger.info("🤖 Starting IDX AI Telegram Bot...")

    # Start background scheduler
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("⏰ Background scheduler started")

    app = create_bot()

    async with app:
        await app.initialize()
        await app.start()
        logger.info("🔄 Running with polling (development mode)")
        await app.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=False,
        )
        
        # Keep the bot running
        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
            logger.info("🛑 Stopping bot...")
            await app.stop()
            await app.shutdown()
            scheduler.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
