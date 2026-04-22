"""/stock command handler — quick stock price lookup."""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from app.services.ai_service import ai_service

logger = logging.getLogger(__name__)


async def stock_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /stock <TICKER> command.
    Also handles /s shortcut and plain text ticker input.
    """
    # Extract ticker from args
    if not context.args:
        await update.message.reply_text(
            "❓ Cara penggunaan: `/stock BBCA`\n\n"
            "Contoh saham: BBCA, BBRI, TLKM, ASII",
            parse_mode="Markdown",
        )
        return

    ticker = context.args[0].upper().strip()
    logger.info(f"Stock lookup: {ticker} by user {update.effective_user.id}")

    # Send "typing" indicator while fetching
    await update.message.chat.send_action("typing")

    try:
        result = await ai_service.quick_lookup(ticker)
        await update.message.reply_text(result, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Stock handler error for {ticker}: {e}")
        await update.message.reply_text(
            f"❌ Terjadi kesalahan saat mengambil data untuk **{ticker}**.\n"
            f"Silakan coba lagi dalam beberapa saat.",
            parse_mode="Markdown",
        )
