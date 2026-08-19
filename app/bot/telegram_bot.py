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
    ContextTypes,
    MessageHandler,
    filters,
)

from app.config import get_settings
from app.bot.handlers.start import start_handler, help_handler
from app.bot.handlers.stock import stock_handler
from app.bot.handlers.analyze import analyze_handler
from app.bot.handlers.crypto import crypto_handler
from app.bot.handlers.nlp import nlp_handler
from app.bot.middleware import error_handler, rate_limit_middleware
from app.scheduler.jobs import create_scheduler


async def log_all_updates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log every incoming update for debugging."""
    msg = update.message or update.edited_message or update.channel_post
    if msg:
        logger.info(
            f"📥 RECEIVED update_id={update.update_id} "
            f"chat={msg.chat.id} user={msg.from_user.id if msg.from_user else '?'} "
            f"text={msg.text!r}"
        )
    else:
        logger.info(f"📥 RECEIVED update_id={update.update_id} type={update.update_type}")

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
        BotCommand("crypto", "Scanner crypto Tokocrypto"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("✅ Bot commands menu set up")


def create_bot() -> Application:
    """Create and configure the Telegram bot application."""
    if not settings.telegram_bot_token:
        logger.error("❌ TELEGRAM_BOT_TOKEN not set!")
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

    # Build application
    # NOTE: read_timeout must be >= the long-polling timeout (default 50s).
    # A short read_timeout (30s) causes getUpdates to time out client-side while
    # the server still holds the request open, so the retry overlaps the old
    # request and Telegram aborts it with 409 Conflict.
    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .read_timeout(60)
        .write_timeout(60)
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
    app.add_handler(CommandHandler("crypto", crypto_handler))

    # Debug: log every incoming update (group -1 runs before all handlers)
    app.add_handler(MessageHandler(filters.ALL, log_all_updates), group=-1)

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

    # Start MQTT heartbeat (ESP32 sound alerts) if enabled
    from app.services.mqtt_client import mqtt_publisher
    await mqtt_publisher.start()
    if mqtt_publisher.enabled():
        logger.info("📡 MQTT publisher enabled")

    app = create_bot()

    # NOTE: `async with app` only calls initialize()/shutdown(). We MUST call
    # app.start() explicitly — it launches the background task that processes
    # updates from the queue. Without it the bot fetches updates (getUpdates
    # returns 200) but handlers never run.
    async with app:
        await app.start()
        logger.info("🔄 Running with polling (development mode)")
        await app.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=False,
            timeout=50,
            read_timeout=60,
            write_timeout=60,
            connect_timeout=30,
        )

        # Keep the bot running until interrupted
        stop_event = asyncio.Event()
        await stop_event.wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
