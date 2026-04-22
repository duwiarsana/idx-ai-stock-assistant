"""Bot middleware — error handling and rate limiting."""

import logging
import time
from collections import defaultdict

from telegram import Update
from telegram.ext import ContextTypes

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Simple in-memory rate limiter (use Redis in production with multiple instances)
_user_requests: dict[int, list[float]] = defaultdict(list)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler for the bot."""
    logger.error(f"Bot error: {context.error}", exc_info=context.error)

    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ Maaf, terjadi kesalahan internal.\n"
                "Silakan coba lagi dalam beberapa saat.",
            )
        except Exception:
            pass


def check_rate_limit(user_id: int) -> bool:
    """
    Check if user has exceeded rate limit.

    Returns True if allowed, False if rate limited.
    """
    now = time.time()
    window = settings.rate_limit_window
    max_requests = settings.rate_limit_per_user

    # Clean old entries
    _user_requests[user_id] = [
        t for t in _user_requests[user_id]
        if now - t < window
    ]

    if len(_user_requests[user_id]) >= max_requests:
        return False

    _user_requests[user_id].append(now)
    return True


async def rate_limit_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Rate limiting middleware. Call at the start of handlers.

    Returns True if request is allowed.
    """
    if not update.effective_user:
        return True

    if not check_rate_limit(update.effective_user.id):
        await update.effective_message.reply_text(
            "⏳ Anda terlalu sering mengirim permintaan.\n"
            f"Silakan tunggu {settings.rate_limit_window} detik.",
        )
        return False

    return True
