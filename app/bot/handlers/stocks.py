"""/stocks command — view IDX stock scanner results and suggestions.

Commands:
    /stocks           — top scored stocks from today's scan
    /stocks scan      — trigger a manual scan now
    /stocks watchlist — show stocks being monitored
    /stocks help      — this help
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from app.config import get_settings
from app.services.scoring_service import get_latest_scores

logger = logging.getLogger(__name__)
settings = get_settings()

STOCKS_HELP_MESSAGE = """
📈 **IDX Stock Scanner**

Perintah yang tersedia:

/stocks — Top saham dari hasil scan hari ini
/stocks scan — Jalankan scan manual sekarang
/stocks watchlist — Daftar saham yang dipantau
/stocks help — Bantuan ini

━━━━━━━━━━━━━━━━━━━━━━
⚠️ *Informasi bukan saran investasi.*
"""


async def stocks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Main /stocks dispatcher."""
    args = context.args or []
    sub = args[0].lower().strip() if args else "top"

    await update.message.chat.send_action("typing")

    if sub == "scan":
        await _stocks_scan(update, context)
    elif sub in ("watchlist", "list"):
        await _stocks_watchlist(update, context)
    elif sub in ("help", "bantuan"):
        await update.message.reply_text(STOCKS_HELP_MESSAGE, parse_mode="Markdown")
    else:
        await _stocks_top(update, context)


async def _stocks_top(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show top-scored stocks from recent scans."""
    try:
        scores = await get_latest_scores(limit=10)
        if not scores:
            await update.message.reply_text(
                "📊 **IDX Stock Scanner**\n\n"
                "Belum ada hasil scan hari ini.\n"
                "Jalankan `/stocks scan` untuk scan manual.",
                parse_mode="Markdown"
            )
            return

        lines = ["📈 **TOP SAHAM IDX (Hasil Scan)**", ""]

        for i, s in enumerate(scores, 1):
            ticker = s.get("ticker", "?")
            score = s.get("final_score", 0)
            signal = s.get("signal", "?")
            trend = s.get("trend_status", "?")
            confidence = s.get("confidence", "?")

            # Score emoji
            if score >= 70:
                emoji = "🟢"
            elif score >= 55:
                emoji = "🟡"
            else:
                emoji = "⚪"

            # Signal emoji
            signal_emoji = "🟢" if signal == "BUY" else ("🔴" if signal == "SELL" else "⏸️")

            lines.append(
                f"{emoji} **{ticker}** — Score: **{score:.0f}**/100\n"
                f"   Signal: {signal_emoji} {signal} | Trend: {trend} | Confidence: {confidence}"
            )

        lines.append("")
        lines.append("💡 Gunakan `/analyze BBRI` untuk analisis detail")
        lines.append("⚠️ *Bukan saran investasi*")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error in _stocks_top: {e}")
        await update.message.reply_text(f"❌ Error: {e}")


async def _stocks_scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Trigger a manual stock scan."""
    await update.message.reply_text("🔄 Scanning IDX stocks... (butuh ~2 menit)")

    try:
        from app.scheduler.jobs import intraday_scanner_job
        await intraday_scanner_job()
        await update.message.reply_text(
            "✅ Scan selesai! Cek `/stocks` untuk hasilnya."
        )
    except Exception as e:
        logger.error(f"Error in manual stock scan: {e}")
        await update.message.reply_text(f"❌ Scan gagal: {e}")


async def _stocks_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show list of monitored stocks."""
    try:
        from app.services.stock_service import get_all_active_tickers
        tickers = await get_all_active_tickers()
        if not tickers:
            tickers = []

        lines = ["📋 **WATCHLIST (Saham Dipantau)**", ""]
        for i, t in enumerate(sorted(tickers), 1):
            lines.append(f"  {i}. {t}.JK")

        lines.append("")
        lines.append(f"Total: {len(tickers)} saham")
        lines.append("💡 Gunakan `/analyze BBRI` untuk analisis detail")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error in _stocks_watchlist: {e}")
        await update.message.reply_text(f"❌ Error: {e}")
