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
🪙 **Crypto Bot & Scanner (Tokocrypto)**

Berikut perintah yang tersedia:

📊 **Portofolio & Posisi Real:**
• `/portofolio` atau `/porto` — Ringkasan saldo, PnL & posisi terbuka
• `/posisi` — Detail posisi real yang sedang berjalan
• `/riwayat` — 10 transaksi real terakhir
• `/audit [koin]` — Laporan forensic & analisa detail keputusan bot
• `/detail <koin>` — Chart candlestick & analisa koin (misal: `/detail POL`)

🔍 **Scanner & Sinyal:**
• `/crypto` — Status scanner & koin kandidat
• `/crypto scan` — Jalankan scan manual sekarang
• `/crypto alerts` — Riwayat sinyal/alert terkirim

📝 **Paper Trading (Simulasi):**
• `/crypto paper` — Status paper trading
• `/crypto paper positions` — Posisi paper terbuka
• `/crypto paper history` — Riwayat transaksi paper

❓ `/crypto help` — Tampilkan bantuan ini
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
    elif sub in ("paper", "simulasi"):
        await _crypto_paper(update, context)
    elif sub in ("portfolio", "portofolio", "porto", "saldo"):
        await _crypto_real_portfolio(update, context)
    elif sub in ("positions", "posisi", "pos"):
        await _crypto_real_positions(update, context)
    elif sub in ("history", "riwayat"):
        await _crypto_real_history(update, context)
    elif sub in ("audit", "forensic", "jurnal"):
        await crypto_audit_handler(update, context)
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


async def _crypto_real_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show REAL portfolio summary with cash balance, open holdings, and realized PnL."""
    try:
        from app.services.crypto_real import real_trader
        summary = await real_trader._portfolio_summary("USDT")
        if not summary or not summary.strip():
            await update.message.reply_text("📭 Belum ada data portofolio real.", parse_mode="Markdown")
            return
        await update.message.reply_text(summary.strip(), parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"Failed to load real portfolio: {e}")
        await update.message.reply_text(f"❌ Gagal memuat portofolio: {e}", parse_mode="Markdown")


async def _crypto_real_positions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show detailed open positions currently active on REAL account."""
    try:
        from sqlalchemy import select, desc
        from app.db.session import async_session_factory
        from app.models.crypto import CryptoPaperPosition
        from app.services.crypto_real import real_trader

        async with async_session_factory() as session:
            result = await session.execute(
                select(CryptoPaperPosition)
                .where(
                    CryptoPaperPosition.status == "OPEN",
                    CryptoPaperPosition.mode == "REAL",
                )
                .order_by(desc(CryptoPaperPosition.created_at))
            )
            positions = result.scalars().all()

        if not positions:
            await update.message.reply_text(
                "📭 **Tidak ada posisi REAL yang terbuka saat ini.**\n"
                "Bot siap membuka posisi saat sinyal entry terdeteksi.",
                parse_mode="Markdown",
            )
            return

        lines = [f"📊 **POSISI REAL TERBUKA ({len(positions)}):**", ""]
        for p in positions:
            quote = p.quote or "USDT"
            try:
                cur_price = await real_trader._fetch_price_from_symbol(p.symbol, quote)
            except Exception:
                cur_price = p.entry_price or 0.0

            cur_pnl = (cur_price - p.entry_price) * p.quantity if p.entry_price else 0.0
            cur_pnl_pct = ((cur_price - p.entry_price) / p.entry_price * 100) if p.entry_price else 0.0
            emoji = "🟢" if cur_pnl >= 0 else "🔴"

            tp1_str = _fmt_price(p.take_profit_1) if p.take_profit_1 else "—"
            tp2_str = _fmt_price(p.take_profit_2) if p.take_profit_2 else "—"
            sl_str = _fmt_price(p.stop_loss) if p.stop_loss else "—"

            lines.append(
                f"{emoji} **{p.display or p.symbol}**\n"
                f"   💵 Entry: {_fmt_price(p.entry_price)} | Now: {_fmt_price(cur_price)}\n"
                f"   📦 Qty: {p.quantity:.4f} (≈ {p.quantity * cur_price:.2f} {quote})\n"
                f"   💹 Floating PnL: **{cur_pnl:+.4f} {quote}** ({cur_pnl_pct:+.2f}%)\n"
                f"   🎯 TP1: {tp1_str} | TP2: {tp2_str}\n"
                f"   🛑 SL: {sl_str}\n"
            )

        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("💡 _Gunakan /portofolio untuk total saldo & riwayat akumulasi._")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"Failed to load real positions: {e}")
        await update.message.reply_text(f"❌ Gagal memuat posisi terbuka: {e}", parse_mode="Markdown")


async def _crypto_real_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show recent 10 closed REAL trades."""
    try:
        from sqlalchemy import select, desc
        from app.db.session import async_session_factory
        from app.models.crypto import CryptoPaperPosition

        async with async_session_factory() as session:
            result = await session.execute(
                select(CryptoPaperPosition)
                .where(
                    CryptoPaperPosition.status == "CLOSED",
                    CryptoPaperPosition.mode == "REAL",
                )
                .order_by(desc(CryptoPaperPosition.closed_at))
                .limit(10)
            )
            trades = result.scalars().all()

        if not trades:
            await update.message.reply_text("📭 Belum ada riwayat transaksi REAL.", parse_mode="Markdown")
            return

        lines = ["📜 **10 TRANSAKSI REAL TERAKHIR:**", ""]
        for t in trades:
            quote = t.quote or "USDT"
            pnl = t.realized_pnl or 0.0
            pnl_pct = (pnl / t.invested * 100) if t.invested and t.invested > 0 else 0.0
            emoji = "🟢" if pnl >= 0 else "🔴"
            exit_time = t.closed_at.astimezone().strftime("%d/%m %H:%M") if t.closed_at else ""

            lines.append(
                f"{emoji} **{t.display or t.symbol}** [{t.exit_reason or 'CLOSED'}]\n"
                f"   💵 In: {_fmt_price(t.entry_price)} ➔ Out: {_fmt_price(t.exit_price)}\n"
                f"   💹 PnL: **{pnl:+.4f} {quote}** ({pnl_pct:+.2f}%) · {exit_time}\n"
            )

        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("💡 _Ketik `/audit` atau `/audit <koin>` untuk analisa detail keputusan bot & post-mortem._")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"Failed to load real history: {e}")
        await update.message.reply_text(f"❌ Gagal memuat riwayat: {e}", parse_mode="Markdown")


async def crypto_detail_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show detailed coin technicals and candlestick chart for /detail <coin>."""
    args = context.args or []
    if not args:
        # Check if there are open positions and suggest them
        try:
            from sqlalchemy import select
            from app.db.session import async_session_factory
            from app.models.crypto import CryptoPaperPosition

            async with async_session_factory() as session:
                res = await session.execute(
                    select(CryptoPaperPosition.symbol)
                    .where(CryptoPaperPosition.status == "OPEN", CryptoPaperPosition.mode == "REAL")
                )
                open_syms = [r[0] for r in res.all()]
        except Exception:
            open_syms = []

        hint_txt = "❓ **Format Perintah:** `/detail <nama_koin>`\n\nContoh:\n• `/detail POL`\n• `/detail BTC`\n• `/detail ACE`"
        if open_syms:
            hint_txt += "\n\n📊 **Posisi Real Terbuka Saat Ini:**\n" + "\n".join(
                f"• `/detail {s.split('_')[0]}`" for s in open_syms
            )
        await update.message.reply_text(hint_txt, parse_mode="Markdown")
        return

    raw_coin = args[0].strip().upper()
    # Normalize: POL -> POL_USDT, POLUSDT -> POL_USDT, POL/USDT -> POL_USDT
    clean_sym = raw_coin.replace("/", "_")
    if "_" not in clean_sym:
        clean_sym += "_USDT"

    display_name = clean_sym.replace("_", "/")
    await update.message.chat.send_action("upload_photo")

    try:
        from app.services.crypto_chart import fetch_klines_for_chart, generate_candlestick_chart, calculate_rsi
        from sqlalchemy import select
        from app.db.session import async_session_factory
        from app.models.crypto import CryptoPaperPosition

        # 1. Check if there is an active open position for this coin
        pos_data = None
        async with async_session_factory() as session:
            res = await session.execute(
                select(CryptoPaperPosition)
                .where(
                    CryptoPaperPosition.symbol == clean_sym,
                    CryptoPaperPosition.status == "OPEN",
                    CryptoPaperPosition.mode == "REAL",
                )
                .order_by(CryptoPaperPosition.created_at.desc())
                .limit(1)
            )
            open_pos = res.scalars().first()
            if open_pos:
                pos_data = {
                    "entry_price": open_pos.entry_price,
                    "take_profit_1": open_pos.take_profit_1,
                    "take_profit_2": open_pos.take_profit_2,
                    "stop_loss": open_pos.stop_loss,
                    "quantity": open_pos.quantity,
                    "invested": open_pos.invested,
                }

        # 2. Fetch candles (15m interval, 60 candles)
        candles = await fetch_klines_for_chart(clean_sym, interval="15m", limit=60)
        if not candles or len(candles) < 5:
            await update.message.reply_text(
                f"❌ Data candlestick tidak ditemukan untuk **{display_name}** di Tokocrypto/Binance.\nPastikan simbol koin benar.",
                parse_mode="Markdown",
            )
            return

        # 3. Render dark candlestick chart image
        chart_buf = generate_candlestick_chart(
            symbol_display=display_name,
            candles=candles,
            interval="15m",
            position_data=pos_data,
        )

        # 4. Calculate technical metrics
        closes = [c["close"] for c in candles]
        last_price = closes[-1]
        first_price = candles[0]["open"]
        high_60 = max(c["high"] for c in candles)
        low_60 = min(c["low"] for c in candles)
        pct_60 = ((last_price - first_price) / first_price) * 100.0
        rsi = calculate_rsi(closes)

        # Build caption
        arrow = "🟢 ▲" if pct_60 >= 0 else "🔴 ▼"
        lines = [
            f"📊 **DETAIL KOIN: {display_name}**",
            f"💵 **Harga Terkini:** `{last_price:g} USDT` ({arrow} {pct_60:+.2f}% dlm 60 candle)",
            f"📈 **High/Low (15h):** `{high_60:g}` / `{low_60:g}`",
        ]
        if rsi is not None:
            rsi_status = "Overbought ⚠️" if rsi >= 70 else ("Oversold 💎" if rsi <= 30 else "Neutral")
            lines.append(f"⚡ **RSI (14):** `{rsi}` ({rsi_status})")

        if pos_data:
            entry = pos_data["entry_price"]
            pnl_val = (last_price - entry) * (pos_data.get("quantity") or 0.0)
            pnl_pct = ((last_price - entry) / entry * 100.0) if entry else 0.0
            pnl_emoji = "🟢" if pnl_pct >= 0 else "🔴"

            lines.extend([
                "",
                f"💼 **STATUS POSISI REAL BOT:**",
                f"• {pnl_emoji} Floating PnL: **{pnl_val:+.4f} USDT** ({pnl_pct:+.2f}%)",
                f"• 💵 Entry: `{entry:g} USDT`",
            ])
            if pos_data.get("take_profit_1"):
                tp1 = pos_data['take_profit_1']
                dist_tp1 = ((tp1 - last_price) / last_price * 100.0) if last_price else 0.0
                lines.append(f"• 🎯 TP1: `{tp1:g} USDT` ({dist_tp1:+.2f}% lagi)")
            if pos_data.get("stop_loss"):
                sl = pos_data['stop_loss']
                dist_sl = ((sl - last_price) / last_price * 100.0) if last_price else 0.0
                is_bep = sl >= entry
                bep_mark = " (BEP Locked 🔒)" if is_bep else ""
                lines.append(f"• 🛑 Stop Loss: `{sl:g} USDT` ({dist_sl:+.2f}%){bep_mark}")
        else:
            lines.extend([
                "",
                "ℹ️ *Tidak ada posisi real terbuka untuk koin ini.*",
            ])

        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        caption = "\n".join(lines)

        if chart_buf:
            await update.message.reply_photo(
                photo=chart_buf,
                caption=caption,
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(caption, parse_mode="Markdown")

    except Exception as e:
        logger.exception(f"Error in crypto_detail_handler: {e}")
        await update.message.reply_text(f"❌ Terjadi kesalahan saat memproses chart {display_name}: {e}", parse_mode="Markdown")


async def crypto_audit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Provide a comprehensive forensic breakdown and post-mortem analysis of a trade."""
    args = context.args or []
    filter_sym = args[0].strip().upper() if args else None
    if filter_sym:
        filter_sym = filter_sym.replace("/", "_")
        if "_" not in filter_sym:
            filter_sym += "_USDT"

    await update.message.chat.send_action("typing")

    try:
        from sqlalchemy import select
        from app.db.session import async_session_factory
        from app.models.crypto import CryptoPaperPosition

        async with async_session_factory() as session:
            query = (
                select(CryptoPaperPosition)
                .where(
                    CryptoPaperPosition.status == "CLOSED",
                    CryptoPaperPosition.mode == "REAL",
                )
            )
            if filter_sym:
                query = query.where(CryptoPaperPosition.symbol.ilike(f"%{filter_sym}%"))
            query = query.order_by(CryptoPaperPosition.closed_at.desc()).limit(1)

            result = await session.execute(query)
            pos = result.scalar_one_or_none()

        if not pos:
            target_name = f" koin **{filter_sym}**" if filter_sym else ""
            await update.message.reply_text(
                f"ℹ️ Belum ada riwayat transaksi real yang selesai untuk{target_name}.\n"
                f"Ketik `/riwayat` untuk melihat daftar transaksi yang pernah ada.",
                parse_mode="Markdown",
            )
            return

        meta = pos.trade_metadata if isinstance(pos.trade_metadata, dict) else {}
        entry_snap = meta.get("entry_snapshot") or {}
        telemetry = meta.get("telemetry") or {}
        exit_snap = meta.get("exit_snapshot") or {}
        post_mortem = exit_snap.get("post_mortem") or {}

        pnl = pos.realized_pnl or 0.0
        quote = pos.quote or "USDT"
        cost_basis = pos.invested or (pos.quantity * pos.entry_price if pos.quantity and pos.entry_price else 1.0)
        pnl_pct = (pnl / cost_basis * 100.0) if cost_basis else 0.0
        pnl_emoji = "🟢" if pnl >= 0 else "🔴"

        closed_time = pos.closed_at.astimezone().strftime("%d/%m/%Y %H:%M") if pos.closed_at else "-"
        entry_time = pos.created_at.astimezone().strftime("%d/%m/%Y %H:%M") if pos.created_at else "-"
        dur_str = exit_snap.get("duration_formatted") or "-"

        safe_symbol = (pos.display or pos.symbol or "").replace("_", "\\_")
        safe_diag = post_mortem.get('diagnosis', 'Evaluasi selesai. Disiplin rencana trading.').replace("_", " ").replace("*", "")
        safe_exit = str(pos.exit_reason or 'CLOSED').replace("_", "\\_")

        lines = [
            f"🔬 **AUDIT FORENSIC BOT: {safe_symbol}**",
            f"Status: **{safe_exit}** | Waktu Selesai: `{closed_time}`",
            f"Durasi Trade: `{dur_str}` (Entry: `{entry_time}`)",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "📥 **1. KEPUTUSAN ENTRY (Snapshot Bot):**",
            f"• Strategi: `{str(entry_snap.get('strategy', 'PULLBACK'))}`",
            f"• Skor Algoritma: `{entry_snap.get('score', pos.entry_score or '-')}/100`",
            f"• Harga Beli: `{_fmt_price(pos.entry_price)} {quote}`",
            f"• Investasi: `{cost_basis:.2f} {quote}` (Qty: `{pos.quantity or 0.0:.6f}`)",
        ]

        t1h = entry_snap.get("technicals_1h") or {}
        if t1h:
            lines.append(
                f"• 1h: RSI `{t1h.get('rsi', '-')}` · MACD `{str(t1h.get('macd_state', '-'))}` · "
                f"RV `{t1h.get('relative_volume', '-')}` · EMA20 Dist `{t1h.get('distance_to_ema20_pct', '-')}%`"
            )
        t15 = entry_snap.get("technicals_15m") or {}
        if t15:
            lines.append(
                f"• 15m Konfirmasi: Trend `{str(t15.get('trend', '-'))}` · MACD `{str(t15.get('macd_state', '-'))}`"
            )
        btc_info = (entry_snap.get("market_context") or {}).get("btc") or {}
        if btc_info:
            lines.append(
                f"• Kondisi BTC Saat Entry: `{str(btc_info.get('btc_trend_1h', '-'))}` (MACD `{str(btc_info.get('btc_macd_1h', '-'))}`)"
            )
        ai_v = entry_snap.get("ai_verdict") or {}
        if ai_v:
            lines.append(
                f"• AI Verdict: `{str(ai_v.get('verdict', '-'))}` (Keyakinan: `{ai_v.get('confidence', '-')}%`)"
            )

        lines.extend([
            "",
            "📈 **2. TELEMETRI SELAMA POSISI BERJALAN:**",
            f"• Peak Floating Gain: `+{telemetry.get('max_floating_profit_pct', 0.0):.2f}%` (High: `{_fmt_price(telemetry.get('highest_price', pos.entry_price))}`)",
            f"• Max Drawdown: `{telemetry.get('max_floating_loss_pct', 0.0):.2f}%` (Low: `{_fmt_price(telemetry.get('lowest_price', pos.entry_price))}`)",
            f"• Auto-BEP Status: `{'Aktif Terkunci' if telemetry.get('bep_activated') else 'Tidak Aktif'}`",
            f"• Trailing SL: `{len(telemetry.get('trailing_updates', []))} kali penyesuaian`",
        ])

        fees = exit_snap.get("fees") or {}
        tot_fee = fees.get("total_fees", 0.0)
        lines.extend([
            "",
            "🏁 **3. HASIL EKSEKUSI & BIAYA (Tokocrypto):**",
            f"• Harga Keluar: `{_fmt_price(pos.exit_price)} {quote}`",
            f"• Gross Price Move: `{exit_snap.get('gross_move_pct', 0.0):+.2f}%`",
            f"• Total Fee Beli + Jual (0.5%): `-{tot_fee:.4f} {quote}`",
            f"• {pnl_emoji} **Realized Net PnL:** **{pnl:+.4f} {quote}** ({pnl_pct:+.2f}%)",
            "",
            "🧠 **4. DIAGNOSA BOT & BAHAN KOREKSI:**",
            f"💡 {safe_diag}",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "📔 Jurnal detail otomatis diarsipkan ke server.",
        ])

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.exception(f"Error in crypto_audit_handler: {e}")
        await update.message.reply_text(f"❌ Terjadi kesalahan saat memproses audit: {e}", parse_mode="Markdown")
