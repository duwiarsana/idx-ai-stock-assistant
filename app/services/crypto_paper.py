"""Paper trading engine for the crypto scanner.

Simulates spot trading with virtual balance. On every scan cycle it:
1. Re-prices every open position against the live ticker.
2. Closes positions that hit TP1 (partial), TP2, or SL.
3. Opens new positions for candidates that pass the entry gate:
   score >= entry threshold AND (optionally) a fresh breakout.
4. Persists account / positions / trades to Postgres and notifies Telegram.

Important: this is a SIMULATOR. No real orders are ever placed; no API secret
is used. Real trading would be a separate module gated behind explicit config
(see ``crypto_real_trading_enabled``) and requires a signed private API client.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.config import get_settings
from app.services.crypto_alert import _fmt_price

logger = logging.getLogger(__name__)
settings = get_settings()

# Position lifecycle statuses
STATUS_OPEN = "OPEN"
STATUS_CLOSED = "CLOSED"

# Exit reasons
EXIT_TP1 = "TP1"
EXIT_TP2 = "TP2"
EXIT_SL = "SL"

# Trade sides
SIDE_BUY = "BUY"
SIDE_SELL_TP1 = "SELL_TP1"
SIDE_SELL_TP2 = "SELL_TP2"
SIDE_SELL_SL = "SELL_SL"


class PaperTrader:
    """Simulates a virtual spot account driven by scanner candidates."""

    def __init__(self):
        self.state = {
            "enabled": settings.crypto_paper_trading_enabled,
            "last_cycle_at": None,
            "last_cycle_status": "idle",
            "last_error": None,
            "positions_opened": 0,
            "positions_closed": 0,
        }

    # ── Public API ────────────────────────────────────────────────────

    async def run_cycle(self, candidates: list[dict], tickers: dict) -> dict:
        """Evaluate exits for open positions and open new entries.

        ``candidates`` is the full scored candidate list; ``tickers`` is the
        normalized 24h ticker map keyed by symbol (used for re-pricing).
        """
        result = {
            "status": "ok",
            "positions_opened": 0,
            "positions_closed": 0,
            "errors": 0,
        }
        self.state["last_cycle_status"] = "running"

        try:
            from app.db.session import async_session_factory

            async with async_session_factory() as session:
                # 1. Re-price + close open positions.
                closed = await self._process_open_positions(session, tickers)
                result["positions_closed"] = closed

                # 2. Open new positions for qualifying candidates.
                opened = await self._process_candidates(session, candidates, tickers)
                result["positions_opened"] = opened

                await session.commit()
        except Exception as e:
            result["status"] = "error"
            result["errors"] += 1
            result["last_error"] = str(e)
            self.state["last_error"] = str(e)
            logger.exception(f"Paper trading cycle failed: {e}")

        self.state["last_cycle_at"] = datetime.now(timezone.utc).isoformat()
        self.state["last_cycle_status"] = result["status"]
        self.state["positions_opened"] += result["positions_opened"]
        self.state["positions_closed"] += result["positions_closed"]

        logger.info(
            f"📝 Paper trading cycle done: opened={result['positions_opened']} "
            f"closed={result['positions_closed']} status={result['status']}"
        )
        return result

    # ── Exit processing ───────────────────────────────────────────────

    async def _process_open_positions(self, session, tickers: dict) -> int:
        from sqlalchemy import select
        from app.models.crypto import CryptoPaperPosition, CryptoPaperAccount

        result = await session.execute(
            select(CryptoPaperPosition).where(
                CryptoPaperPosition.status == STATUS_OPEN,
                CryptoPaperPosition.mode == "PAPER",
            )
        )
        positions = result.scalars().all()
        if not positions:
            return 0

        closed = 0
        for pos in positions:
            try:
                price = self._current_price(tickers, pos.symbol)
                if price is None:
                    continue

                # Track highest price for trailing stop (persisted to DB)
                highest = pos.highest_price or pos.entry_price
                if price > highest:
                    pos.highest_price = price

                action = self._decide_exit(pos, price)
                if action is None:
                    continue

                account = await self._get_or_create_account(session, pos.quote)
                await self._close_position(session, pos, account, action, price)
                closed += 1
            except Exception as e:
                logger.warning(f"Paper exit error for {pos.symbol}: {e}")

        return closed

    def _decide_exit(self, pos, price: float) -> Optional[str]:
        """Return EXIT_TP1 / EXIT_TP2 / EXIT_SL, or None if no exit.
        
        Uses a trailing stop mechanism to avoid premature exits from noise.
        The stop loss is dynamic: it trails up as price increases but never
        moves down (protects profits while avoiding false stop-outs).
        """
        sl = pos.stop_loss
        tp1 = pos.take_profit_1
        tp2 = pos.take_profit_2
        entry_price = pos.entry_price or price
        
        # Calculate trailing stop: max of original SL or a percentage below
        # the highest price seen since entry (capped at breakeven initially).
        # This prevents exit during normal pullbacks but locks in profits.
        highest_since_entry = pos.highest_price or entry_price
        if price > highest_since_entry:
            highest_since_entry = price
            pos.highest_price = price
        
        # Trailing distance: 1.2×ATR or 2% of entry, whichever is larger
        atr = pos.atr_value or (entry_price * 0.02)  # fallback to 2%
        trailing_distance = max(atr * 1.2, entry_price * 0.02)
        
        # Trailing stop price (never below original SL)
        trailing_stop = highest_since_entry - trailing_distance
        effective_sl = max(sl or trailing_stop, trailing_stop)
        
        # Exit checks in priority order: SL first (including trailing), then TP
        if price <= effective_sl:
            return EXIT_SL
        if tp2 is not None and price >= tp2:
            return EXIT_TP2
        if tp1 is not None and price >= tp1:
            return EXIT_TP1
        return None

    async def _close_position(self, session, pos, account, action: str, price: float) -> None:
        from app.models.crypto import CryptoPaperTrade

        qty = pos.quantity or 0.0
        if qty <= 0:
            return

        exit_price = {
            EXIT_SL: pos.stop_loss,
            EXIT_TP2: pos.take_profit_2,
            EXIT_TP1: pos.take_profit_1,
        }.get(action) or price

        proceeds = qty * exit_price
        cost_basis = (qty / (pos.quantity or qty)) * (pos.invested or 0.0) if pos.quantity else 0
        pnl = proceeds - cost_basis

        session.add(CryptoPaperTrade(
            position_id=pos.id,
            symbol=pos.symbol,
            side={EXIT_TP1: SIDE_SELL_TP1, EXIT_TP2: SIDE_SELL_TP2, EXIT_SL: SIDE_SELL_SL}[action],
            price=exit_price,
            quantity=qty,
            quote_amount=proceeds,
            realized_pnl=pnl,
        ))

        account.cash_balance += proceeds
        account.realized_pnl += pnl
        account.total_trades += 1
        if pnl > 0:
            account.winning_trades += 1

        pos.status = STATUS_CLOSED
        pos.exit_price = exit_price
        pos.exit_reason = action
        pos.realized_pnl = pnl
        pos.closed_at = datetime.now(timezone.utc)

        logger.info(
            f"🎯 Paper {pos.display or pos.symbol} closed via {action}: "
            f"entry={pos.entry_price} exit={exit_price} pnl={pnl:+.2f} {pos.quote}"
        )

        if settings.crypto_paper_notify:
            await self._notify_close(pos, action, exit_price, pnl, account)

        # MQTT for ESP32 sound alerts (profit vs loss).
        try:
            from app.services.mqtt_client import mqtt_publisher
            if action == EXIT_SL:
                await mqtt_publisher.publish_loss(pos, exit_price, pnl, account)
            else:
                await mqtt_publisher.publish_profit(pos, exit_price, pnl, account)
        except Exception as e:
            logger.warning(f"MQTT close publish failed: {e}")

    # ── Entry processing ──────────────────────────────────────────────

    async def _process_candidates(self, session, candidates: list[dict], tickers: dict) -> int:
        if not settings.crypto_paper_trading_enabled:
            logger.info(f"Paper trading disabled, skipping candidates")
            return 0
        if not candidates:
            logger.info(f"No candidates to process")
            return 0

        logger.info(f"Processing {len(candidates)} paper candidates")

        from sqlalchemy import select
        from app.models.crypto import CryptoPaperPosition

        result = await session.execute(
            select(CryptoPaperPosition.symbol).where(
                CryptoPaperPosition.status == STATUS_OPEN,
                CryptoPaperPosition.mode == "PAPER",
            )
        )
        open_symbols = {row[0] for row in result.all()}
        logger.info(f"Open positions: {open_symbols}")

        # Symbols that hit SL recently are in cooldown — skip re-entry until
        # the window passes (avoids buying back into a falling knife).
        cooldown_symbols: set[str] = set()
        cooldown_minutes = settings.crypto_paper_sl_cooldown_minutes or 0
        if cooldown_minutes > 0:
            from datetime import datetime, timezone, timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)
            cooldown_result = await session.execute(
                select(CryptoPaperPosition.symbol).where(
                    CryptoPaperPosition.status == STATUS_CLOSED,
                    CryptoPaperPosition.mode == "PAPER",
                    CryptoPaperPosition.exit_reason == EXIT_SL,
                    CryptoPaperPosition.closed_at >= cutoff,
                )
            )
            cooldown_symbols = {row[0] for row in cooldown_result.all()}

        opened = 0
        # Shortlist = candidates passing the deterministic gate and not already
        # open / in cooldown, sorted by score. AI (if enabled) runs on this
        # shortlist only — the scanner no longer burns LLM tokens on every
        # candidate when telegram alerts are off.
        shortlist = []
        for c in sorted(candidates, key=lambda x: x.get("score", 0), reverse=True):
            symbol = c.get("symbol")
            score = c.get("score", 0)
            passes_gate = self._passes_entry_gate(c)
            logger.info(f"Candidate {symbol} score={score} passes_gate={passes_gate}")
            if not passes_gate:
                continue
            if not symbol or symbol in open_symbols or symbol in cooldown_symbols:
                logger.info(f"Skipping {symbol}: in open={symbol in open_symbols} or cooldown={symbol in cooldown_symbols}")
                continue
            price = c.get("price")
            if not price:
                continue
            shortlist.append(c)

        logger.info(f"Shortlist: {[c.get('symbol') for c in shortlist]}")

        if not shortlist:
            return 0

        # AI quality filter: keep only STRONG_WATCH / WATCH. If the AI fails or
        # returns nothing we fall back to the deterministic verdict — never a
        # single point of failure.
        ai_verdicts: dict[str, dict] = {}
        if settings.crypto_paper_ai_filter_enabled:
            try:
                from app.services.crypto_ai import analyze_candidates
                raw = await analyze_candidates(shortlist)
                ai_verdicts = {k: v.to_dict() for k, v in raw.items()}
            except Exception as e:
                logger.warning(f"Paper AI filter failed: {e}; using deterministic verdicts")
            from app.services.crypto_ai import deterministic_fallback
            for c in shortlist:
                symbol = c.get("symbol")
                c["ai_verdict"] = ai_verdicts.get(
                    symbol, deterministic_fallback(c).to_dict()
                )

        for c in shortlist:
            if settings.crypto_paper_ai_filter_enabled:
                verdict = ((c.get("ai_verdict") or {}).get("verdict") or "").upper()
                if verdict and verdict not in ("STRONG_WATCH", "WATCH"):
                    continue
            symbol = c.get("symbol")

            quote = c.get("quote") or settings.crypto_paper_quote_asset
            price = c.get("price")

            account = await self._get_or_create_account(session, quote)
            open_count = await self._open_position_count(session, quote)
            if open_count >= settings.crypto_paper_max_positions:
                break  # sorted by score — no point checking lower scores

            allocated = account.cash_balance * (settings.crypto_paper_allocation_percent / 100.0)
            if allocated < price:
                continue

            await self._open_position(session, account, c, price)
            open_symbols.add(symbol)
            opened += 1

        return opened

    def _passes_entry_gate(self, c: dict) -> bool:
        score = c.get("score") or 0
        if score < settings.crypto_paper_entry_score:
            return False

        s1h = (c.get("tf_summaries") or {}).get("1h") or {}

        # Volume gate: require above-average volume (filters noise)
        rv_1h = s1h.get("relative_volume")
        if rv_1h is None or rv_1h < 1.2:
            return False

        # Bear market filter: reject if 24h trend is strongly negative
        ticker = c.get("ticker") or {}
        price_change_24h = float(ticker.get("priceChangePercent", 0) or 0)
        if price_change_24h < -5:
            return False

        # Uptrend filter: buy only coins in a confirmed 1h uptrend
        # (EMA9 > EMA20 > EMA50 aligned + MACD bullish).
        if settings.crypto_paper_entry_require_uptrend:
            if s1h.get("trend") != "bullish":
                return False
            if s1h.get("macd_state") != "bullish":
                return False

        # Legacy breakout gate (kept for backward compat, default off).
        if settings.crypto_paper_entry_require_breakout:
            if not s1h.get("at_high"):
                return False

        # Pullback gate (only in pullback/uptrend strategy): don't chase the
        # top. Price must be within pullback_max_pct above EMA20 (a healthy
        # pullback in the uptrend), and NOT at the recent high.
        if settings.crypto_paper_entry_require_uptrend:
            price = s1h.get("price")
            ema20 = s1h.get("ema20")
            if ema20 and price:
                max_above = ema20 * (1 + settings.crypto_paper_entry_pullback_max_pct / 100.0)
                if price > max_above:
                    return False  # too extended above EMA20 → chasing
                if s1h.get("at_high"):
                    return False  # buying the top of a breakout spike

        # AI quality filter: ONLY accept STRONG_WATCH (stricter for higher win rate)
        if settings.crypto_paper_ai_filter_enabled:
            verdict = ((c.get("ai_verdict") or {}).get("verdict") or "").upper()
            if verdict and verdict != "STRONG_WATCH":
                return False

        return True

    async def _open_position_count(self, session, quote: str) -> int:
        from sqlalchemy import select, func
        from app.models.crypto import CryptoPaperPosition

        result = await session.execute(
            select(func.count()).select_from(CryptoPaperPosition).where(
                CryptoPaperPosition.status == STATUS_OPEN,
                CryptoPaperPosition.mode == "PAPER",
                CryptoPaperPosition.quote == quote,
            )
        )
        return int(result.scalar() or 0)

    async def _open_position(self, session, account, c: dict, price: float) -> None:
        from app.models.crypto import CryptoPaperPosition, CryptoPaperTrade

        levels = c.get("price_levels") or {}
        tp1 = levels.get("take_profit_1")
        tp2 = levels.get("take_profit_2")
        sl = levels.get("stop_loss")

        # Store ATR for trailing stop calculation
        tf_summaries = c.get("tf_summaries") or {}
        s1h = tf_summaries.get("1h") or {}
        atr = s1h.get("atr") or (price * 0.02)  # fallback to 2% of price

        allocated = account.cash_balance * (settings.crypto_paper_allocation_percent / 100.0)
        qty = allocated / price

        pos = CryptoPaperPosition(
            symbol=c.get("symbol"),
            base=c.get("base"),
            quote=account.quote_asset,
            display=c.get("display"),
            status=STATUS_OPEN,
            mode="PAPER",
            entry_price=price,
            quantity=qty,
            invested=allocated,
            take_profit_1=tp1,
            take_profit_2=tp2,
            stop_loss=sl,
            entry_score=c.get("score"),
            entry_reason=levels.get("entry_note"),
            atr_value=levels.get("atr"),
            highest_price=price,
        )
        session.add(pos)
        await session.flush()  # assign pos.id

        session.add(CryptoPaperTrade(
            position_id=pos.id,
            symbol=pos.symbol,
            side=SIDE_BUY,
            price=price,
            quantity=qty,
            quote_amount=allocated,
        ))

        account.cash_balance -= allocated

        logger.info(
            f"💎 Paper BUY {pos.display or pos.symbol} @ {price} {account.quote_asset} "
            f"(qty={qty:.6f}, invested={allocated:.2f}, ATR={atr:.4f})"
        )

        if settings.crypto_paper_notify:
            await self._notify_open(pos, account)

        # MQTT for ESP32 sound alerts.
        try:
            from app.services.mqtt_client import mqtt_publisher
            await mqtt_publisher.publish_buy(pos, account)
        except Exception as e:
            logger.warning(f"MQTT buy publish failed: {e}")

    # ── Helpers ───────────────────────────────────────────────────────

    async def _get_or_create_account(self, session, quote: str):
        from sqlalchemy import select
        from app.models.crypto import CryptoPaperAccount

        result = await session.execute(
            select(CryptoPaperAccount).where(CryptoPaperAccount.quote_asset == quote)
        )
        account = result.scalar_one_or_none()
        if account is None:
            account = CryptoPaperAccount(
                quote_asset=quote,
                initial_balance=settings.crypto_paper_initial_balance,
                cash_balance=settings.crypto_paper_initial_balance,
            )
            session.add(account)
            await session.flush()
        return account

    @staticmethod
    def _current_price(tickers: dict, symbol: str) -> Optional[float]:
        normalized = symbol.replace("_", "")
        ticker = tickers.get(normalized) or tickers.get(symbol)
        if not ticker:
            return None
        return ticker.get("lastPrice")

    # ── Telegram notifications ────────────────────────────────────────

    async def _send_telegram(self, text: str) -> None:
        chat_id = settings.telegram_chat_id or settings.telegram_admin_id
        if not settings.telegram_bot_token or not chat_id:
            return
        try:
            from telegram import Bot
            bot = Bot(token=settings.telegram_bot_token)
            await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Failed to send paper notification: {e}")

    async def _notify_open(self, pos, account=None) -> None:
        text = (
            "🟢 *PAPER BUY* (simulasi)\n\n"
            f"🔹 {pos.display or pos.symbol}\n"
            f"💵 Entry: {_fmt_price(pos.entry_price)} {pos.quote}\n"
            f"📦 Qty: {pos.quantity:.6f}\n"
            f"💰 Invested: {pos.invested:.2f} {pos.quote}\n"
        )
        if pos.take_profit_1:
            text += f"🎯 TP1: {_fmt_price(pos.take_profit_1)}\n"
        if pos.take_profit_2:
            text += f"🎯 TP2: {_fmt_price(pos.take_profit_2)}\n"
        if pos.stop_loss:
            text += f"🛑 SL: {_fmt_price(pos.stop_loss)}\n"
        if pos.entry_score is not None:
            text += f"📊 Skor entry: {pos.entry_score:.0f}/100\n"
        text += self._account_summary_text(account)
        text += "\n_Signal monitoring only, not financial advice._"
        await self._send_telegram(text)

    async def _notify_close(self, pos, action: str, exit_price: float, pnl: float, account=None) -> None:
        emoji = "✅" if pnl >= 0 else "🔻"
        pnl_pct = ((exit_price - pos.entry_price) / pos.entry_price * 100) if pos.entry_price else 0
        pnl_str = f"{pnl:+.4f}" if abs(pnl) < 1 else f"{pnl:+.2f}"
        text = (
            f"{emoji} *PAPER SELL ({action})* (simulasi)\n\n"
            f"🔹 {pos.display or pos.symbol}\n"
            f"💵 Entry: {_fmt_price(pos.entry_price)} {pos.quote}\n"
            f"🏁 Exit: {_fmt_price(exit_price)} {pos.quote}\n"
            f"💹 PnL: **{pnl_str} {pos.quote}** ({pnl_pct:+.2f}%)\n"
        )
        if pnl >= 0:
            text += "🎉 *UNTUNG!*\n"
        else:
            text += "⚠️ *RUGI.*\n"
        text += self._account_summary_text(account)
        text += "\n_Signal monitoring only, not financial advice._"
        await self._send_telegram(text)

    @staticmethod
    def _account_summary_text(account) -> str:
        """Format saldo & PnL akun untuk ditampilkan di Telegram."""
        if account is None:
            return ""
        cash = account.cash_balance or 0.0
        realized = account.realized_pnl or 0.0
        total_trades = account.total_trades or 0
        winning = account.winning_trades or 0
        line = "\n💼 *Ringkasan Akun:*\n"
        line += f"💰 Saldo: {cash:,.2f} {account.quote_asset}\n"
        pnl_emoji = "✅" if realized >= 0 else "🔻"
        line += f"{pnl_emoji} Total PnL: **{realized:+,.2f} {account.quote_asset}**\n"
        line += f"📊 Trade: {total_trades} ({winning} menang, {total_trades - winning} rugi)\n"
        return line


# Singleton
paper_trader = PaperTrader()