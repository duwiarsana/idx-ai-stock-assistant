"""/crypto command handler — interactive Tokocrypto scanner access.

Commands:
    /crypto              — scanner status + latest candidates
    /crypto scan         — trigger a manual scan (alerts sent to TELEGRAM_CHAT_ID)
    /crypto scan --dry   — manual scan without sending alerts / AI
    /crypto alerts       — recent sent alerts (from DB)
    /crypto help         — this help
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from app.config import get_settings
from app.services.crypto_scanner import crypto_scanner
from app.services.crypto_alert import _fmt_price

logger = logging.getLogger(__name__)
settings = get_settings()

MAX_TELEGRAM_MSG_LENGTH = 4096


CRYPTO_HELP_MESSAGE = """
🪙 **Crypto Scanner (Tokocrypto)**

Berikut perintah yang tersedia:

/crypto — Status & kandidat terbaru
/crypto scan — Jalankan scan manual
   (kirim alert ke Telegram)
/crypto scan --dry — Scan simulasi
   (tidak kirim alert / AI)
/crypto alerts — Riwayat alert terkirim
/crypto paper — Status paper trading (simulasi)
/crypto paper positions — Posisi terbuka (paper)
/crypto paper history — Riwayat transaksi (paper)
/crypto help — Bantuan ini

━━━━━━━━━━━━━━━━━━━━━━
⚠️ *Informasi bukan saran investasi.*
"""


async def crypto_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Main /crypto dispatcher."""
    args = context.args or []
    sub = args[0].lower().strip() if args else "status"

    await update.message.chat.send_action("typing")

    if sub == "scan":
        await _crypto_scan(update, context)
    elif sub == "alerts":
        await _crypto_alerts(update, context)
    elif sub == "paper":
        await _crypto_paper(update, context)
    elif sub in ("help", "bantuan"):
        await update.message.reply_text(CRYPTO_HELP_MESSAGE, parse_mode="Markdown")
    else:
        await _crypto_status(update, context)


async def _crypto_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show scanner status + latest candidates."""
    state = crypto_scanner.state
    last_scan = state.get("last_scan_at")
    last_status = state.get("last_scan_status", "idle")
    last_error = state.get("last_error")
    results = state.get("last_results", []) or []

    lines = [
        "🪙 **CRYPTO SCANNER (Tokocrypto)**",
        "",
        f"Status: {_status_emoji(last_status)} {last_status}",
        f"Enabled: {'✅' if settings.crypto_scanner_enabled else '⛔'}",
        f"Dry-run: {'✅' if settings.crypto_scanner_dry_run else '❌'}",
        f"Interval: {settings.crypto_scan_interval_minutes} menit",
    ]

    if last_scan:
        try:
            ts = datetime.fromisoformat(str(last_scan))
            local = ts.astimezone().strftime("%Y-%m-%d %H:%M")
            lines.append(f"Scan terakhir: {local}")
        except Exception:
            lines.append(f"Scan terakhir: {last_scan}")
    else:
        lines.append("Scan terakhir: _belum pernah_")

    lines.append(f"Pair ditemukan: {state.get('pairs_found', 0)}")
    lines.append(f"Pair dianalisis: {state.get('pairs_analysed', 0)}")
    lines.append(f"Threshold skor: {settings.crypto_min_score_alert}")

    if last_error:
        lines.append("")
        lines.append(f"⚠️ Error terakhir: `{str(last_error)[:200]}`")

    lines.append("")

    if results:
        lines.append("📊 **Kandidat terbaru:**")
        for r in results[:10]:
            verdict = r.get("ai_verdict", {}) or {}
            score = r.get("score")
            display = r.get("display", r.get("symbol", "?"))
            arrow = {"bullish": "🟢", "bearish": "🔴"}.get(r.get("trend"), "⚪")
            lines.append(
                f"{arrow} {display} — skor **{score:.0f}** | "
                f"{verdict.get('verdict', '?')} (risk {verdict.get('risk', '?')})"
            )
        lines.append("")
        lines.append("💡 Gunakan `/crypto scan` untuk scan baru.")
    else:
        lines.append("Belum ada hasil scan. Gunakan `/crypto scan` untuk memulai.")

    lines.append("")
    lines.append("⚠️ *Informasi bukan saran investasi.*")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def _crypto_scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Trigger a manual scan (with optional --dry flag)."""
    dry = any(a.lower() in ("--dry", "dry", "--dry-run", "dry-run") for a in (context.args or []))

    status_msg = await update.message.reply_text(
        "🔍 Menjalankan crypto scan..."
        + (" _(mode simulasi, tanpa alert/AI)_" if dry else "")
        + "\n_Memuat data Tokocrypto, menghitung indikator & skor..._",
        parse_mode="Markdown",
    )

    try:
        summary = await crypto_scanner.run_scan(dry_run=dry)
        await status_msg.delete()

        if summary.get("status") == "skipped":
            await update.message.reply_text(
                "⏳ Scan sedang berjalan (scan lain masih aktif). Coba lagi dalam beberapa menit.",
                parse_mode="Markdown",
            )
            return

        lines = [
            "📊 **Hasil Crypto Scan**"
            + (" _(dry-run, tidak ada alert/AI)_" if dry else ""),
            "",
            f"Status: {summary.get('status')}",
            f"Pair ditemukan: {summary.get('pairs_found')}",
            f"Pair likuid: {summary.get('pairs_liquid')}",
            f"Pair dianalisis: {summary.get('pairs_analysed')}",
            f"Kandidat (≥{settings.crypto_min_score_alert}): {summary.get('candidates')}",
            f"AI dianalisis: {summary.get('ai_analysed')}",
            f"Alert terkirim: {summary.get('alerts_sent')}",
            f"Durasi: {summary.get('duration_ms')} ms",
        ]

        if summary.get("errors"):
            lines.append(f"⚠️ Error: {summary.get('errors')}")

        lines.append("")

        results = summary.get("results", [])[:10]
        if results:
            lines.append("🏆 **Top kandidat:**")
            for r in results:
                verdict = r.get("ai_verdict", {}) or {}
                score = r.get("score")
                display = r.get("display", r.get("symbol", "?"))
                pc1h = (r.get("price_change") or {}).get("1h")
                pc = f" | 1H {pc1h:+.1f}%" if pc1h is not None else ""
                lines.append(
                    f"• {display} — **{score:.0f}** "
                    f"({verdict.get('verdict', '?')}){pc}"
                )
                pl = r.get("price_levels") or {}
                if pl.get("entry") and pl.get("take_profit_1"):
                    lines.append(
                        f"   💎 Entry {_fmt_price(pl['entry'])} → "
                        f"TP1 {_fmt_price(pl['take_profit_1'])} / "
                        f"TP2 {_fmt_price(pl['take_profit_2'])} | "
                        f"SL {_fmt_price(pl['stop_loss'])}"
                    )
        else:
            lines.append("Tidak ada kandidat yang memenuhi threshold.")

        lines.append("")
        lines.append("⚠️ *Informasi bukan saran investasi.*")

        # Telegram limit: split if needed.
        text = "\n".join(lines)
        if len(text) <= MAX_TELEGRAM_MSG_LENGTH:
            await update.message.reply_text(text, parse_mode="Markdown")
        else:
            await update.message.reply_text(text[:MAX_TELEGRAM_MSG_LENGTH], parse_mode="Markdown")

    except Exception as e:
        logger.exception(f"Crypto scan handler error: {e}")
        try:
            await status_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(
            f"❌ Terjadi kesalahan saat menjalankan crypto scan.\n"
            f"Silakan coba lagi nanti.\n\n`{str(e)[:200]}`",
            parse_mode="Markdown",
        )


async def _crypto_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show recent sent alerts from the database."""
    try:
        from sqlalchemy import select, desc
        from app.db.session import async_session_factory
        from app.models.crypto import CryptoAlert

        async with async_session_factory() as session:
            result = await session.execute(
                select(CryptoAlert).order_by(desc(CryptoAlert.created_at)).limit(10)
            )
            alerts = result.scalars().all()
    except Exception as e:
        logger.warning(f"Failed to load crypto alerts for bot: {e}")
        await update.message.reply_text(
            "❌ Tidak bisa memuat riwayat alert (database tidak tersedia).",
            parse_mode="Markdown",
        )
        return

    if not alerts:
        await update.message.reply_text(
            "📭 Belum ada alert crypto yang terkirim.",
            parse_mode="Markdown",
        )
        return

    lines = ["🚨 **Alert Crypto Terakhir:**", ""]
    for a in alerts:
        ts = ""
        if a.created_at:
            try:
                ts = a.created_at.astimezone().strftime("%d %b %H:%M")
            except Exception:
                ts = ""
        score = f"{a.score:.0f}" if a.score is not None else "?"
        display = a.display or a.symbol
        risk = a.risk or "?"
        delivery = a.delivery_status or "?"
        lines.append(
            f"• {ts} **{display}** — skor {score} | risk {risk}"
            f"\n  _delivery: {delivery}_"
        )

    lines.append("")
    lines.append("⚠️ *Informasi bukan saran investasi.*")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


def _status_emoji(status: str) -> str:
    return {"ok": "✅", "error": "❌", "running": "🔄", "skipped": "⏳"}.get(status, "⚪")


async def _crypto_paper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Paper trading sub-commands: status / positions / history."""
    args = context.args or []
    sub = args[0].lower().strip() if args else "status"

    try:
        from sqlalchemy import select, desc, func
        from app.db.session import async_session_factory
        from app.models.crypto import CryptoPaperAccount, CryptoPaperPosition, CryptoPaperTrade

        async with async_session_factory() as session:
            if sub in ("positions", "pos"):
                result = await session.execute(
                    select(CryptoPaperPosition)
                    .where(CryptoPaperPosition.status == "OPEN")
                    .order_by(desc(CryptoPaperPosition.created_at))
                    .limit(10)
                )
                positions = result.scalars().all()
                if not positions:
                    await update.message.reply_text(
                        "📭 Belum ada posisi paper trading yang terbuka.",
                        parse_mode="Markdown",
                    )
                    return
                lines = ["💼 **Posisi Paper Terbuka:**", ""]
                for p in positions:
                    entry = _fmt_price(p.entry_price) if p.entry_price is not None else "?"
                    tp1 = _fmt_price(p.take_profit_1) if p.take_profit_1 else "?"
                    sl = _fmt_price(p.stop_loss) if p.stop_loss else "?"
                    qty = f"{p.quantity:.6f}" if p.quantity is not None else "?"
                    lines.append(
                        f"• **{p.display or p.symbol}** ({p.quote})\n"
                        f"   Entry {entry} | Qty {qty}\n"
                        f"   TP1 {tp1} | SL {sl}"
                    )
                lines.append("")
                lines.append("⚠️ *Simulasi — bukan transaksi sungguhan.*")
                await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
                return

            if sub in ("history", "riwayat"):
                result = await session.execute(
                    select(CryptoPaperTrade)
                    .order_by(desc(CryptoPaperTrade.created_at))
                    .limit(10)
                )
                trades = result.scalars().all()
                if not trades:
                    await update.message.reply_text(
                        "📭 Belum ada transaksi paper trading.",
                        parse_mode="Markdown",
                    )
                    return
                lines = ["📜 **Riwayat Paper Trading:**", ""]
                for t in trades:
                    ts = ""
                    if t.created_at:
                        try:
                            ts = t.created_at.astimezone().strftime("%d %b %H:%M")
                        except Exception:
                            ts = ""
                    price = _fmt_price(t.price) if t.price is not None else "?"
                    pnl = f"PnL {t.realized_pnl:+.2f}" if t.realized_pnl is not None else ""
                    lines.append(
                        f"• {ts} **{t.symbol}** {t.side} @ {price} {pnl}"
                    )
                lines.append("")
                lines.append("⚠️ *Simulasi — bukan transaksi sungguhan.*")
                await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
                return

            # Default: status
            result = await session.execute(select(CryptoPaperAccount))
            accounts = result.scalars().all()
            open_count = await session.execute(
                select(func.count()).select_from(CryptoPaperPosition).where(
                    CryptoPaperPosition.status == "OPEN"
                )
            )
            open_total = int(open_count.scalar() or 0)

            lines = [
                "📝 **PAPER TRADING (Simulasi)**",
                "",
                f"Enabled: {'✅' if settings.crypto_paper_trading_enabled else '⛔'}",
                f"Alokasi per posisi: {settings.crypto_paper_allocation_percent}%",
                f"Maks posisi: {settings.crypto_paper_max_positions}",
                f"Entry skor min: {settings.crypto_paper_entry_score}",
                "",
                f"Posisi terbuka: **{open_total}**",
            ]

            if accounts:
                for a in accounts:
                    equity = a.cash_balance + (a.realized_pnl)
                    lines.append("")
                    lines.append(f"**Akun {a.quote_asset}:**")
                    lines.append(f"   Saldo: {a.cash_balance:,.2f} {a.quote_asset}")
                    lines.append(f"   PnL realisasi: **{a.realized_pnl:+.2f}** {a.quote_asset}")
                    lines.append(f"   Trades: {a.total_trades} ({a.winning_trades} profit)")
            else:
                lines.append("")
                lines.append("_Akun belum dibuat — tunggu siklus scan berikutnya._")

            lines.append("")
            lines.append("💡 `/crypto paper positions` & `/crypto paper history`")
            lines.append("⚠️ *Simulasi — bukan transaksi sungguhan.*")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
            return
    except Exception as e:
        logger.warning(f"Crypto paper handler error: {e}")
        await update.message.reply_text(
            "❌ Tidak bisa memuat data paper trading (database tidak tersedia).",
            parse_mode="Markdown",
        )
