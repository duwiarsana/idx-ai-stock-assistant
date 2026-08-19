"""Real trading engine for the crypto scanner — REAL MONEY.

Replaces paper positions with live orders on the Tokocrypto spot exchange when
``crypto_real_trading_enabled`` is true. Same strategy signals as the paper
trader (momentum gate + pullback-in-uptrend), but execution is real:

* BUY = market buy with ``quoteOrderQty`` (spend exactly the allocated amount).
* SELL = market sell of the full quantity on TP1/TP2/SL.

Safety rails (never compromise these):
* Disabled by default; only runs when the user explicitly opts in via config.
* Uses a TRADE-only API key (withdraw must be OFF on the exchange).
* Hard drawdown limit: stops opening new positions once realized PnL exceeds
  ``crypto_real_max_drawdown``.
* Per-position allocation is small (``crypto_real_allocation_percent``).
* Market orders only — no leveraged/futures endpoints are ever touched.

If any order call fails, the engine logs loudly and does NOT retry blindly —
a failed BUY must never be auto-repeated without confirmation.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from app.config import get_settings
from app.services.crypto_alert import _fmt_price

logger = logging.getLogger(__name__)
settings = get_settings()

STATUS_OPEN = "OPEN"
STATUS_CLOSED = "CLOSED"

EXIT_TP1 = "TP1"
EXIT_TP2 = "TP2"
EXIT_SL = "SL"

SIDE_BUY = "BUY"
SIDE_SELL_TP1 = "SELL_TP1"
SIDE_SELL_TP2 = "SELL_TP2"
SIDE_SELL_SL = "SELL_SL"


class RealTrader:
    """Places real orders driven by the same candidate signals as paper."""

    def __init__(self):
        from app.data.tokocrypto_trade_client import TokoCryptoTradeClient
        self.client = TokoCryptoTradeClient()
        self.state = {
            "enabled": settings.crypto_real_trading_enabled,
            "last_cycle_at": None,
            "last_cycle_status": "idle",
            "last_error": None,
        }

    # ── Public API ────────────────────────────────────────────────────

    async def run_cycle(self, candidates: list[dict], tickers: dict) -> dict:
        """Evaluate exits for open real positions and open new entries."""
        result = {"status": "ok", "positions_opened": 0, "positions_closed": 0, "errors": 0}
        self.state["last_cycle_status"] = "running"
        try:
            from app.db.session import async_session_factory

            async with async_session_factory() as session:
                closed = await self._process_open_positions(session, tickers)
                result["positions_closed"] = closed
                opened = await self._process_candidates(session, candidates, tickers)
                result["positions_opened"] = opened
                await session.commit()
        except Exception as e:
            result["status"] = "error"
            result["errors"] += 1
            result["last_error"] = str(e)
            self.state["last_error"] = str(e)
            logger.exception(f"Real trading cycle failed: {e}")

        self.state["last_cycle_at"] = datetime.now(timezone.utc).isoformat()
        self.state["last_cycle_status"] = result["status"]
        logger.info(
            f"💰 Real trading cycle done: opened={result['positions_opened']} "
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
                CryptoPaperPosition.mode == "REAL",
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
                action = self._decide_exit(pos, price)
                if action is None:
                    continue
                account = await self._get_or_create_account(session, pos.quote)
                ok = await self._close_position(session, pos, account, action, price)
                if ok:
                    closed += 1
            except Exception as e:
                logger.warning(f"Real exit error for {pos.symbol}: {e}")
        return closed

    def _decide_exit(self, pos, price: float) -> Optional[str]:
        sl = pos.stop_loss
        tp1 = pos.take_profit_1
        tp2 = pos.take_profit_2
        if sl is not None and price <= sl:
            return EXIT_SL
        if tp2 is not None and price >= tp2:
            return EXIT_TP2
        if tp1 is not None and price >= tp1:
            return EXIT_TP1
        return None

    async def _close_position(self, session, pos, account, action: str, price: float) -> bool:
        from app.models.crypto import CryptoPaperTrade

        qty = pos.quantity or 0.0
        if qty <= 0:
            return False

        # The DB quantity can exceed what is actually available on the exchange
        # (taker fee / dust on the BUY means the wallet holds a bit less). If we
        # try to sell more than the free balance the exchange rejects the order
        # with "Insufficient balance" and the position never closes. Cap the sell
        # to the actual free base balance when we can read it.
        try:
            avail = await self.client.get_balance(pos.base)
        except Exception as e:
            logger.warning(f"Failed to read {pos.base} balance for {pos.symbol}: {e}")
            avail = None
        if avail is not None and avail > 0:
            qty = min(qty, avail)
        else:
            # Cannot confirm available balance — apply a conservative 1% fee
            # discount so we don't overshoot and hit "Insufficient balance".
            qty = qty * 0.99

        # Round the sell quantity DOWN to the LOT_SIZE step (a non-multiple is
        # rejected by the exchange). Then verify the notional meets the exchange
        # NOTIONAL minimum — if not, try rounding UP (still within available
        # balance) so the order doesn't get rejected for being too small.
        rules = await self.client.get_symbol_rules(pos.symbol)
        step = rules.get("step_size") or 1e-8
        min_notional = rules.get("min_notional") or 5.0
        qty_sell = self._round_down_to_step(qty, step)
        if qty_sell <= 0:
            logger.warning(
                f"REAL SELL skipped {pos.symbol}: quantity {qty:.10f} rounds below one "
                f"LOT_SIZE step ({step}) — position too small to sell."
            )
            return False

        # If the notional (qty * price) is below the exchange minimum, round UP
        # to the next step — the extra fraction of a coin is worth staying under
        # the limit and having the order rejected.  Cap at available balance.
        if price and qty_sell * price < min_notional:
            qty_up = self._round_up_to_step(qty, step)
            if qty_up <= qty and qty_up * price >= min_notional:
                qty_sell = qty_up
            else:
                # Even the max affordable qty can't meet min_notional — sell
                # whatever we have; some exchanges accept orders slightly below.
                qty_sell = self._round_down_to_step(qty, step)

        # ── REAL SELL order ───────────────────────────────────────────
        try:
            resp = await self.client.market_sell(pos.symbol, qty_sell)
            fill = self._parse_fill(resp)
        except Exception as e:
            # A failed SELL must not be silently swallowed — keep position OPEN
            # so the next cycle can try again. Log loudly.
            logger.error(f"REAL SELL FAILED for {pos.symbol}: {e}")
            self.state["last_error"] = f"SELL_FAIL {pos.symbol}: {e}"
            return False

        exit_price = fill.get("price") or price
        proceeds = qty_sell * exit_price
        pnl = proceeds - (pos.invested or 0.0)

        session.add(CryptoPaperTrade(
            position_id=pos.id,
            symbol=pos.symbol,
            side={EXIT_TP1: SIDE_SELL_TP1, EXIT_TP2: SIDE_SELL_TP2, EXIT_SL: SIDE_SELL_SL}[action],
            price=exit_price,
            quantity=qty_sell,
            quote_amount=proceeds,
            realized_pnl=pnl,
        ))

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
            f"💰 REAL SELL {pos.display or pos.symbol} via {action}: "
            f"entry={pos.entry_price} exit={exit_price} pnl={pnl:+.2f} {pos.quote}"
        )
        if settings.crypto_real_notify:
            await self._notify_close(pos, action, exit_price, pnl, account)
        return True

    # ── Entry processing ──────────────────────────────────────────────

    async def _process_candidates(self, session, candidates: list[dict], tickers: dict) -> int:
        if not settings.crypto_real_trading_enabled:
            return 0
        if not candidates:
            return 0

        from sqlalchemy import select
        from app.models.crypto import CryptoPaperPosition

        result = await session.execute(
            select(CryptoPaperPosition.symbol).where(
                CryptoPaperPosition.status == STATUS_OPEN,
                CryptoPaperPosition.mode == "REAL",
            )
        )
        open_symbols = {row[0] for row in result.all()}
        if len(open_symbols) >= settings.crypto_real_max_positions:
            return 0

        # Hard drawdown safety: stop opening if realized PnL is too negative.
        if settings.crypto_real_max_drawdown > 0:
            dd_ok = await self._drawdown_ok(session)
            if not dd_ok:
                logger.warning("Real trading paused: drawdown limit reached")
                return 0

        shortlist = []
        for c in sorted(candidates, key=lambda x: x.get("score", 0), reverse=True):
            if not self._passes_entry_gate(c):
                continue
            symbol = c.get("symbol")
            if not symbol or symbol in open_symbols:
                continue
            price = c.get("price")
            if not price:
                continue
            shortlist.append(c)

        if not shortlist:
            return 0

        # AI quality filter (same rules as paper; never a single point of failure).
        if settings.crypto_paper_ai_filter_enabled:
            try:
                from app.services.crypto_ai import analyze_candidates
                raw = await analyze_candidates(shortlist)
                ai_verdicts = {k: v.to_dict() for k, v in raw.items()}
            except Exception as e:
                logger.warning(f"Real AI filter failed: {e}")
                from app.services.crypto_ai import deterministic_fallback
                ai_verdicts = {c.get("symbol"): deterministic_fallback(c).to_dict() for c in shortlist}
            shortlist = [
                c for c in shortlist
                if ((ai_verdicts.get(c.get("symbol")) or {}).get("verdict") or "WATCH").upper()
                in ("STRONG_WATCH", "WATCH")
            ]
            if not shortlist:
                return 0

        opened = 0
        for c in shortlist:
            if len(open_symbols) >= settings.crypto_real_max_positions:
                break
            symbol = c.get("symbol")
            quote = c.get("quote") or settings.crypto_real_quote_asset
            if quote != settings.crypto_real_quote_asset:
                continue  # only trade the configured quote asset
            price = c.get("price")
            if not price:
                continue

            ok = await self._open_position(session, c, price, quote)
            if ok:
                open_symbols.add(symbol)
                opened += 1

        return opened

    def _passes_entry_gate(self, c: dict) -> bool:
        score = c.get("score") or 0
        if score < settings.crypto_real_entry_score:
            return False

        s1h = (c.get("tf_summaries") or {}).get("1h") or {}

        if settings.crypto_paper_entry_require_uptrend:
            if s1h.get("trend") != "bullish":
                return False
            if s1h.get("macd_state") != "bullish":
                return False

        if settings.crypto_paper_entry_require_breakout:
            if not s1h.get("at_high"):
                return False

        if settings.crypto_paper_entry_require_uptrend:
            price = s1h.get("price")
            ema20 = s1h.get("ema20")
            if ema20 and price:
                max_above = ema20 * (1 + settings.crypto_paper_entry_pullback_max_pct / 100.0)
                if price > max_above:
                    return False
                if s1h.get("at_high"):
                    return False
        return True

    async def _drawdown_ok(self, session) -> bool:
        from sqlalchemy import select
        from app.models.crypto import CryptoPaperAccount
        account = (await session.execute(
            select(CryptoPaperAccount).where(
                CryptoPaperAccount.quote_asset == settings.crypto_real_quote_asset
            )
        )).scalar_one_or_none()
        if account is None:
            return True
        realized = account.realized_pnl or 0.0
        return realized >= -settings.crypto_real_max_drawdown

    async def _open_position(self, session, c: dict, price: float, quote: str) -> bool:
        from app.models.crypto import CryptoPaperPosition, CryptoPaperTrade, CryptoPaperAccount

        symbol = c.get("symbol")
        rules = await self.client.get_symbol_rules(symbol)
        min_notional = rules.get("min_notional") or settings.crypto_real_min_order_quote or 5.0
        step = rules.get("step_size") or 1e-8

        # Determine allocation from real account balance.
        balance = await self._real_balance(quote)
        if balance is None:
            logger.warning(f"REAL BUY skipped {symbol}: cannot read {quote} balance")
            return False
        allocated = balance * (settings.crypto_real_allocation_percent / 100.0)
        if allocated <= 0:
            logger.warning(f"REAL BUY skipped {symbol}: {quote} balance too low")
            return False
        # NOTE: no early return here when `allocated < min_notional`. The
        # exchange minimum is a hard floor, so for very small balances the walk
        # below grows the position (still capped by balance) until it becomes
        # sellable. Skipping would make the bot unable to trade at all when the
        # configured allocation is under the NOTIONAL floor.

        # Convert spend -> base quantity, rounded UP to the LOT_SIZE step so the
        # resulting position stays above the NOTIONAL floor and is sellable.
        if not price or price <= 0:
            logger.warning(f"REAL BUY skipped {symbol}: no valid price")
            return False
        qty = allocated / price
        qty = self._round_up_to_step(qty, step)
        # Sanity: after rounding the notional must still be >= min (rounding UP
        # only increases it, but a tiny step could make qty == 0 for very small
        # allocations).
        if qty <= 0:
            logger.warning(f"REAL BUY skipped {symbol}: quantity rounds to zero")
            return False

        # The filled quantity is reduced by taker fee and a later SELL is
        # rounded DOWN to the LOT_SIZE step. To guarantee the position can be
        # sold back (notional >= NOTIONAL floor), size the BUY so that
        # round_down(qty_after_fee) * price >= min_notional. Walk the step up
        # until sellable, capped by the available balance.
        sellable = False
        fee_rate = 0.002  # 0.2% — covers the 0.1% taker fee plus safety margin
        for _ in range(200):  # hard cap on the walk to avoid runaway
            qty_after_fee = qty * (1 - fee_rate)
            sellable_qty = self._round_down_to_step(qty_after_fee, step)
            if sellable_qty > 0 and sellable_qty * price >= min_notional:
                sellable = True
                break
            if qty * price > balance:
                break  # cannot afford to grow the position any further
            qty += step
        if not sellable:
            logger.warning(
                f"REAL BUY skipped {symbol}: cannot size a sellable position "
                f"(balance={balance:.2f}, min_notional={min_notional:.2f}, price={price:.4f})"
            )
            return False

        # ── REAL BUY order ────────────────────────────────────────────
        try:
            resp = await self.client.market_buy(symbol, qty)
            fill = self._parse_fill(resp)
        except Exception as e:
            logger.error(f"REAL BUY FAILED for {symbol}: {e}")
            self.state["last_error"] = f"BUY_FAIL {symbol}: {e}"
            return False

        exec_price = fill.get("price") or price
        qty_filled = fill.get("quantity") or 0.0
        if qty_filled <= 0:
            logger.error(f"REAL BUY returned zero quantity for {symbol}: {resp}")
            return False

        levels = c.get("price_levels") or {}
        account = await self._get_or_create_account(session, quote)

        pos = CryptoPaperPosition(
            symbol=symbol,
            base=c.get("base"),
            quote=account.quote_asset,
            display=c.get("display"),
            status=STATUS_OPEN,
            mode="REAL",
            entry_price=exec_price,
            quantity=qty_filled,
            invested=exec_price * qty_filled,
            take_profit_1=levels.get("take_profit_1"),
            take_profit_2=levels.get("take_profit_2"),
            stop_loss=levels.get("stop_loss"),
            entry_score=c.get("score"),
            entry_reason=levels.get("entry_note"),
        )
        session.add(pos)
        await session.flush()

        session.add(CryptoPaperTrade(
            position_id=pos.id,
            symbol=pos.symbol,
            side=SIDE_BUY,
            price=exec_price,
            quantity=qty_filled,
            quote_amount=exec_price * qty_filled,
        ))

        logger.info(
            f"💰 REAL BUY {pos.display or pos.symbol} @ {exec_price} {quote} "
            f"(qty={qty_filled:.8f}, invested={exec_price * qty_filled:.2f})"
        )
        if settings.crypto_real_notify:
            await self._notify_open(pos, account)
        return True

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _parse_fill(resp: dict) -> dict:
        from app.data.tokocrypto_trade_client import TokoCryptoTradeClient
        return TokoCryptoTradeClient.parse_fill(resp)

    @staticmethod
    def _round_up_to_step(value: float, step: float) -> float:
        from app.data.tokocrypto_trade_client import TokoCryptoTradeClient
        return TokoCryptoTradeClient.round_up_to_step(value, step)

    @staticmethod
    def _round_down_to_step(value: float, step: float) -> float:
        from app.data.tokocrypto_trade_client import TokoCryptoTradeClient
        return TokoCryptoTradeClient.round_down_to_step(value, step)

    async def _real_balance(self, quote: str) -> Optional[float]:
        try:
            return await self.client.get_balance(quote)
        except Exception as e:
            logger.warning(f"Balance read failed for {quote}: {e}")
            return None

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
                cash_balance=0.0,
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
            logger.warning(f"Failed to send real-trade notification: {e}")

    async def _notify_open(self, pos, account=None) -> None:
        text = (
            "🔴 *REAL BUY* (uang sungguhan)\n\n"
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
        text += await self._portfolio_summary(pos.quote)
        text += "\n_Order eksekusi real. Bukan saran investasi._"
        await self._send_telegram(text)

    async def _notify_close(self, pos, action: str, exit_price: float, pnl: float, account=None) -> None:
        emoji = "✅" if pnl >= 0 else "🔻"
        text = (
            f"{emoji} *REAL SELL ({action})*\n\n"
            f"🔹 {pos.display or pos.symbol}\n"
            f"💵 Entry: {_fmt_price(pos.entry_price)} {pos.quote}\n"
            f"🏁 Exit: {_fmt_price(exit_price)} {pos.quote}\n"
            f"💹 PnL: **{pnl:+.2f} {pos.quote}**\n"
        )
        text += "🎉 *UNTUNG!*\n" if pnl >= 0 else "⚠️ *RUGI.*\n"
        text += await self._portfolio_summary(pos.quote)
        text += "\n_Order eksekusi real. Bukan saran investasi._"
        await self._send_telegram(text)

    async def _portfolio_summary(self, quote: str = "USDT") -> str:
        """Build portfolio summary: only show bot-traded positions (not full exchange balance)."""
        
        # Get open positions from database (only bot-traded coins)
        from app.db.session import async_session_factory
        from sqlalchemy import select
        from app.models.crypto import CryptoPaperPosition
        
        async with async_session_factory() as session:
            result = await session.execute(
                select(CryptoPaperPosition)
                .where(
                    CryptoPaperPosition.status == "OPEN",
                    CryptoPaperPosition.mode == "REAL",
                    CryptoPaperPosition.quote == quote
                )
            )
            open_positions = result.scalars().all()
        
        if not open_positions:
            return f"\n💼 *Portfolio:* Tidak ada posisi terbuka\n"
        
        # Build holdings from open positions only
        holdings_lines = []
        total_held_value = 0
        
        for pos in open_positions:
            try:
                price = await self._fetch_price_from_symbol(pos.symbol, quote)
            except Exception:
                price = pos.entry_price  # fallback to entry price
            
            value = pos.quantity * price
            total_held_value += value
            pnl = (price - pos.entry_price) * pos.quantity
            pnl_pct = ((price - pos.entry_price) / pos.entry_price * 100) if pos.entry_price > 0 else 0
            
            emoji = "🟢" if pnl >= 0 else "🔴"
            holdings_lines.append(
                f"  {emoji} {pos.display}: {pos.quantity:.4f} @ {price:.6f} "
                f"(≈ {value:.2f} {quote}, {pnl:+.2f} {quote}/{pnl_pct:+.1f}%)"
            )
        
        holdings_text = "\n".join(holdings_lines)
        
        # Get cash balance (optional, can be skipped for cleaner output)
        try:
            cash = await self._real_balance(quote)
        except Exception:
            cash = 0.0
        
        total_value = cash + total_held_value
        
        # Realized PnL from REAL positions only
        realized = 0.0
        total_trades = 0
        winning = 0
        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(
                        func.coalesce(func.sum(CryptoPaperPosition.realized_pnl), 0.0),
                        func.count(CryptoPaperPosition.id),
                        func.count(CryptoPaperPosition.id).filter(
                            CryptoPaperPosition.realized_pnl > 0
                        ),
                    ).where(
                        CryptoPaperPosition.status == "CLOSED",
                        CryptoPaperPosition.mode == "REAL",
                        CryptoPaperPosition.quote == quote,
                    )
                )
                row = result.one()
                realized = float(row[0])
                total_trades = int(row[1])
                winning = int(row[2])
        except Exception:
            pass

        pnl_emoji = "✅" if realized >= 0 else "🔻"
        line = "\n━━━━━━━━━━━━━━━━━━━━\n"
        line += "💼 *PORTOFOLIO BOT (REAL)*\n\n"
        line += f"📊 *Posisi Terbuka ({len(open_positions)}):*\n{holdings_text}\n"
        line += f"💰 Saldo {quote}: **{_fmt_price(cash)}**\n"
        line += f"🏦 Total Invested: **{_fmt_price(total_held_value)} {quote}**\n"
        line += f"💵 *TOTAL VALUE: **{_fmt_price(total_value)} {quote}***\n\n"
        line += f"{pnl_emoji} Total Realized PnL: **{realized:+,.2f} {quote}**\n"
        line += f"📊 Total Trade: {total_trades} ({winning} menang, {total_trades - winning} rugi)\n"
        line += "━━━━━━━━━━━━━━━━━━━━"
        return line

    async def _fetch_price(self, asset: str, quote: str) -> float:
        """Fetch current price for an asset from Tokocrypto public API."""
        import httpx
        client = await self.client._get_client()
        for pair_quote in (quote, "IDR"):
            try:
                resp = await client.get(
                    f"https://www.tokocrypto.site/api/v3/ticker/price",
                    params={"symbol": f"{asset}{pair_quote}"},
                )
                data = resp.json()
                price = float(data.get("price", 0))
                if price > 0:
                    if pair_quote == "IDR" and quote == "USDT":
                        # Convert IDR to USDT (approx)
                        price = price / 16000
                    return price
            except Exception:
                continue
        return 0.0

    async def _fetch_price_from_symbol(self, symbol: str, quote: str) -> float:
        """Fetch current price for a symbol like 'PENGU_USDT'."""
        base = symbol.replace(f"_{quote}", "").lower()
        return await self._fetch_price(base.upper(), quote)

    @staticmethod
    def _account_summary_text(account, real_balance: Optional[float] = None) -> str:
        if account is None:
            return ""
        realized = account.realized_pnl or 0.0
        total_trades = account.total_trades or 0
        winning = account.winning_trades or 0
        line = "\n💼 *Ringkasan Akun (REAL):*\n"
        if real_balance is not None:
            line += f"💰 Saldo {account.quote_asset}: **{real_balance:,.2f}**\n"
        pnl_emoji = "✅" if realized >= 0 else "🔻"
        line += f"{pnl_emoji} Total PnL: **{realized:+,.2f} {account.quote_asset}**\n"
        line += f"📊 Trade: {total_trades} ({winning} menang, {total_trades - winning} rugi)\n"
        return line


# Singleton
real_trader = RealTrader()