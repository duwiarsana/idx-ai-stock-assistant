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
from app.services.crypto_exits import dynamic_roi_exit, trailing_stop_effective

logger = logging.getLogger(__name__)
settings = get_settings()

STATUS_OPEN = "OPEN"
STATUS_CLOSED = "CLOSED"

EXIT_TP1 = "TP1"
EXIT_TP2 = "TP2"
EXIT_SL = "SL"
EXIT_ROI = "ROI"
EXIT_MANUAL = "MANUAL"

SIDE_BUY = "BUY"
SIDE_SELL_TP1 = "SELL_TP1"
SIDE_SELL_TP2 = "SELL_TP2"
SIDE_SELL_SL = "SELL_SL"
SIDE_SELL_ROI = "SELL_ROI"
SIDE_SELL_MANUAL = "SELL_MANUAL"


def _is_blacklisted_base(symbol: str) -> bool:
    """True when the base asset is pegged (stablecoin/gold/wrapped-staked)
    and must never be traded with TP/SL levels."""
    blacklist = {
        s.strip().upper()
        for s in (settings.crypto_real_symbol_blacklist or "").split(",")
        if s.strip()
    }
    base = (symbol or "").split("_")[0].strip().upper()
    return base in blacklist


def is_btc_market_bearish(candidates: list[dict]) -> bool:
    """Check if BTC is in a strong bearish breakdown.

    Returns True if BTC is found and its 1h or 15m trend/momentum is bearish.
    When BTC dumps, almost all altcoins get dragged down into stop-losses.
    """
    for c in candidates:
        sym = (c.get("symbol") or "").upper()
        if sym in ("BTC_USDT", "BTCUSDT", "BTC_IDR", "BTCIDR"):
            s1h = (c.get("tf_summaries") or {}).get("1h") or {}
            s15 = (c.get("tf_summaries") or {}).get("15m") or {}
            # 1h strongly bearish (trend and macd)
            if s1h.get("trend") == "bearish" and s1h.get("macd_state") == "bearish":
                return True
            # or 15m sudden breakdown
            if s15.get("trend") == "bearish" and s15.get("macd_state") == "bearish":
                return True
    return False


def passes_entry_gate(c: dict, btc_bearish: bool = False) -> bool:
    """Shared candidate gate used by BOTH the paper and real engines.

    Running them on identical signals is what makes the parallel paper-vs-real
    comparison meaningful: any performance gap then comes purely from live
    execution (fees, slippage, rejections), not from different strategies.
    """
    symbol = c.get("symbol") or ""
    # Pegged assets (stablecoins/gold/wrapped): flat price by design, so
    # TP/SL levels are meaningless and fees guarantee a loss.
    if _is_blacklisted_base(symbol):
        logger.debug(f"🚫 {symbol}: pegged/blacklisted base asset — skipping")
        return False

    # BTC Market Trend Guard: if BTC is dumping, reject non-BTC altcoin entries
    if btc_bearish and getattr(settings, "crypto_btc_filter_enabled", True):
        base = symbol.split("_")[0].upper()
        if base != "BTC":
            logger.info(f"🚫 {symbol}: BTC market trend is bearish — skipping entry to avoid SL")
            return False

    score = c.get("score") or 0
    if score < settings.crypto_real_entry_score:
        return False

    s1h = (c.get("tf_summaries") or {}).get("1h") or {}

    # Volume gate: require above-average volume (filters noise)
    rv_1h = s1h.get("relative_volume")
    if rv_1h is None or rv_1h < 1.2:
        return False

    # Liquidity gate: skip coins with low 24h quote volume (thin books = slippage)
    ticker = c.get("ticker") or {}
    quote_volume = float(ticker.get("quoteVolume", 0) or 0)
    if quote_volume < 500_000:  # min 500K USDT 24h volume
        return False

    # Bear market filter: reject if 24h trend is strongly negative
    price_change_24h = float(ticker.get("priceChangePercent", 0) or 0)
    if price_change_24h < -5:
        return False

    # Use dedicated real trading settings (stricter than paper)
    if settings.crypto_real_entry_require_uptrend:
        if s1h.get("trend") != "bullish":
            return False
        if s1h.get("macd_state") != "bullish":
            return False

    # Short-term confirmation: a pullback entry is only worth taking once the
    # 15m momentum has stopped falling. Reject candidates whose 15m is still
    # clearly bearish — otherwise we buy the middle of a dip that keeps going
    # down and the SL (just below recent low) gets hit as routine.
    if settings.crypto_real_entry_confirm_15m:
        s15 = (c.get("tf_summaries") or {}).get("15m") or {}
        if s15.get("trend") == "bearish" or s15.get("macd_state") == "bearish":
            logger.debug(f"🚫 {symbol}: 15m still bearish — waiting for recovery")
            return False

    if settings.crypto_real_entry_require_breakout:
        if not s1h.get("at_high"):
            return False

    if settings.crypto_real_entry_require_uptrend:
        price = s1h.get("price")
        ema20 = s1h.get("ema20")
        # Pullback-only guard (skipped in breakout mode): reject over-extended
        # prices above EMA20 and prices already at the recent high. When
        # require_breakout is True we WANT to buy at/just past the high, so
        # these two rejection rules would contradict the breakout intent.
        if ema20 and price and not settings.crypto_real_entry_require_breakout:
            max_above = ema20 * (1 + settings.crypto_real_entry_pullback_max_pct / 100.0)
            if price > max_above:
                return False
            if s1h.get("at_high"):
                return False

    # Check risk/reward ratio
    levels = c.get("price_levels") or {}
    risk_reward = levels.get("risk_reward")
    if risk_reward is not None and risk_reward < settings.crypto_real_entry_min_risk_reward:
        return False

    # Check ATR% (avoid high volatility)
    atr = s1h.get("atr")
    price = s1h.get("price")
    if atr and price and price > 0:
        atr_pct = (atr / price) * 100
        if atr_pct > settings.crypto_real_entry_max_atr_pct:
            return False

    # AI quality filter: accept STRONG_WATCH or WATCH (consistent with paper & candidate loop)
    verdict = ((c.get("ai_verdict") or {}).get("verdict") or "").upper()
    if verdict and verdict not in ("STRONG_WATCH", "WATCH"):
        return False

    return True


class RealTrader:
    """Places real orders driven by the same candidate signals as paper."""

    def __init__(self):
        from app.data.tokocrypto_trade_client import TokoCryptoTradeClient
        self.client = TokoCryptoTradeClient()
        # Price cache to avoid rate limiting: {symbol: (price, timestamp)}
        self._price_cache: dict[str, tuple[float, float]] = {}
        self._cache_ttl = 15.0  # 15 seconds TTL
        # Track positions that already triggered and notified BEP (to prevent spam)
        self._bep_notified_positions: set[str] = set()
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
        
        logger.info(f"🔍 Checking {len(positions)} open REAL positions for TP/SL exits")
        
        if not positions:
            return 0

        closed = 0
        for pos in positions:
            try:
                price = self._current_price(tickers, pos.symbol)
                if price is None:
                    logger.warning(f"⚠️ No price for {pos.symbol}, skipping")
                    continue
                
                # Track highest price for trailing stop (persisted to DB)
                highest = pos.highest_price or pos.entry_price
                if price > highest:
                    pos.highest_price = price
                
                # Check auto-BEP notification trigger
                await self._check_bep_notification(pos, price)
                
                action = self._decide_exit(pos, price)
                
                if action is None:
                    # Check if price is close to TP/SL for logging
                    if pos.take_profit_1:
                        dist_tp1 = ((price - pos.take_profit_1) / pos.take_profit_1 * 100)
                        logger.debug(f"📊 {pos.symbol}: price={price:.6f}, TP1={pos.take_profit_1:.6f} (diff: {dist_tp1:+.2f}%), no exit yet")
                    continue
                
                logger.info(f"🎯 {pos.symbol}: Exit signal = {action} at price {price:.6f}")
                account = await self._get_or_create_account(session, pos.quote)
                result = await self._close_position(session, pos, account, action, price)
                if result == "partial":
                    logger.info(
                        f"⚖️ {pos.symbol}: partial TP1 filled, remaining {pos.quantity:.6f} rides to TP2"
                    )
                elif result:
                    closed += 1
                    logger.info(f"✅ {pos.symbol}: Closed successfully ({action})")
            except Exception as e:
                logger.warning(f"❌ Real exit error for {pos.symbol}: {e}")
                import traceback
                logger.debug(traceback.format_exc())
        
        logger.info(f"📝 Real exit cycle done: {closed} positions closed")
        return closed
    
    async def check_tp_sl_quick(self, session) -> int:
        """Quick TP/SL check for real positions - runs every 30 seconds."""
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
        progress = False
        for pos in positions:
            try:
                price = await self._fetch_price_from_symbol(pos.symbol, pos.quote)
                if price is None or price == 0:
                    continue
                
                # Track highest price for trailing stop (persisted to DB)
                highest = pos.highest_price or pos.entry_price
                if price > highest:
                    pos.highest_price = price
                
                # Check auto-BEP notification trigger
                await self._check_bep_notification(pos, price)
                
                action = self._decide_exit(pos, price)
                
                if action is not None:
                    logger.info(f"⚡ {pos.symbol}: Quick TP/SL exit = {action} at {price:.6f}")
                    account = await self._get_or_create_account(session, pos.quote)
                    result = await self._close_position(session, pos, account, action, price)
                    if result == "partial":
                        progress = True
                        logger.info(
                            f"⚖️ {pos.symbol}: Quick partial TP1 filled, "
                            f"remaining {pos.quantity:.6f} rides to TP2"
                        )
                    elif result:
                        closed += 1
                        progress = True
                        logger.info(f"✅ {pos.symbol}: Quick exit successful ({action})")
            except Exception as e:
                logger.warning(f"⚡ {pos.symbol}: Quick exit error: {e}")
        
        if progress:
            await session.commit()
            if closed > 0:
                logger.info(f"⚡ Quick TP/SL check: {closed} positions closed and committed")
        
        return closed

    def _decide_exit(self, pos, price: float) -> Optional[str]:
        sl = pos.stop_loss
        tp1 = pos.take_profit_1
        tp2 = pos.take_profit_2
        entry_price = pos.entry_price or price

        # Freqtrade-style trailing stop (shared pure function — see
        # crypto_exits). Persist any new peak so the trail survives restarts.
        effective_sl, highest_seen = trailing_stop_effective(pos, price)
        if highest_seen > (pos.highest_price or entry_price):
            pos.highest_price = highest_seen

        # Update and notify when dynamic trailing SL raises above previous stop_loss
        if effective_sl and pos.stop_loss and effective_sl > pos.stop_loss * 1.002:  # at least +0.2% higher to avoid spamming
            old_sl = pos.stop_loss
            pos.stop_loss = effective_sl
            logger.info(f"📈 {pos.symbol}: Trailing SL dinaikkan dari {old_sl:.6f} -> {effective_sl:.6f}")
            if settings.crypto_real_notify:
                asyncio.create_task(self._notify_trailing_sl(pos, old_sl, effective_sl, price))

        # Exit checks in priority order: SL first (including trailing), TP2,
        # TP1, then the time-based dynamic ROI release.
        # SL wick guard: tolerate a small overshoot past the stop on a single
        # ticker snapshot. A momentary wick below SL that recovers should not
        # force a market sell at the bottom — exit only when price is genuinely
        # beyond the level by more than the configured tolerance. Real
        # breakdowns are still caught by the next 30s quick-check.
        if effective_sl and price <= effective_sl:
            tol = settings.crypto_real_sl_exit_tolerance_pct / 100.0
            if tol <= 0 or price < effective_sl * (1 - tol):
                return EXIT_SL
            logger.debug(
                f"⏳ {pos.symbol}: price={price:.6f} within {tol*100:.1f}% of SL "
                f"{effective_sl:.6f} — holding for recovery (wick guard)"
            )
            return None
        if tp2 is not None and price >= tp2:
            # Slippage guard: if price dropped >1% from TP level, skip sell
            # (wait for recovery or let it hit SL instead of selling into weakness)
            slippage_pct = (tp2 - price) / tp2 * 100
            if slippage_pct > 1.0:
                logger.debug(
                    f"⏳ {pos.symbol}: TP2={tp2:.6f} but price={price:.6f} "
                    f"({slippage_pct:.2f}% below TP2) — skipping to avoid slippage"
                )
                return None
            return EXIT_TP2
        # TP1 already partially filled? Don't sell the rider at TP1 again —
        # hold it for TP2 / the trailing stop.
        if tp1 is not None and price >= tp1 and not getattr(pos, "tp1_partial_done", False):
            slippage_pct = (tp1 - price) / tp1 * 100
            if slippage_pct > 1.0:
                logger.debug(
                    f"⏳ {pos.symbol}: TP1={tp1:.6f} but price={price:.6f} "
                    f"({slippage_pct:.2f}% below TP1) — skipping to avoid slippage"
                )
                return None
            return EXIT_TP1
        # Dynamic ROI: free capital from old, thin-profit positions instead of
        # waiting for a full TP (only fires in the profit band BELOW TP levels,
        # because TP checks above already returned).
        roi = dynamic_roi_exit(pos, price)
        if roi:
            logger.info(
                f"⏱️ {pos.symbol}: dynamic ROI exit — price={price:.6f} "
                f"profit={(price - entry_price) / entry_price * 100:.2f}%"
            )
            return roi
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

        # ── Partial TP1 ───────────────────────────────────────────────
        # When TP1 fires for the first time, only sell a slice (default 50%)
        # and let the rest ride toward TP2 / the trailing stop. The old engine
        # dumped 100% at TP1 so TP2 (avg +0.55 USDT vs TP1 +0.08) was almost
        # never reached. Partial TP1 is only feasible when BOTH the sold slice
        # AND the leftover sit above the exchange NOTIONAL minimum — otherwise
        # we fall back to the legacy full close (small positions can't spit).
        partial_sell = False
        if action == EXIT_TP1 and not getattr(pos, "tp1_partial_done", False):
            pct = getattr(settings, "crypto_real_sell_pct_at_tp1", None)
            pct = 100.0 if pct is None else float(pct)
            if 0.0 < pct < 100.0:
                partial_qty = self._round_down_to_step(qty * pct / 100.0, step)
                remainder_qty = qty - partial_qty
                if (
                    partial_qty > 0
                    and remainder_qty > 0
                    and (partial_qty * price) >= min_notional
                    and (remainder_qty * price) >= min_notional
                ):
                    partial_sell = True
                    qty_sell = partial_qty
                else:
                    logger.info(
                        f"⚖️ {pos.symbol}: partial TP1 not feasible "
                        f"(partial={partial_qty * price:.2f}, remainder={remainder_qty * price:.2f}, "
                        f"min_notional={min_notional}) — legacy full close at TP1"
                    )

        # If the notional (qty * price) is below the exchange minimum, round UP
        # to the next step — the extra fraction of a coin is worth staying under
        # the limit and having the order rejected.  Cap at available balance.
        if price and qty_sell * price < min_notional:
            qty_up = self._round_up_to_step(qty, step)
            if qty_up <= qty and qty_up * price >= min_notional:
                qty_sell = qty_up
            else:
                # Even the max affordable qty can't meet min_notional — this is
                # dust. Force-close instead of attempting a doomed sell.
                logger.warning(
                    f"⚡ {pos.symbol}: Notional {qty_sell*price:.4f} USDT < min {min_notional}. "
                    f"Force-closing as dust."
                )
                # BUG FIX: book the REAL market value of the holdings as PnL.
                # The coins stay in the wallet (convertible later via the
                # exchange dust-sweep) — booking -invested here faked a -100%
                # loss on every dust close even when price barely moved.
                exit_price = price
                cost_basis = (qty_sell / qty) * (pos.invested or 0.0) if qty else 0.0
                pnl = (qty_sell * exit_price) - cost_basis
                pos.status = STATUS_CLOSED
                pos.exit_price = exit_price
                pos.exit_reason = f"{action}_DUST"
                pos.realized_pnl = pnl
                pos.closed_at = datetime.now(timezone.utc)
                account.realized_pnl += pnl
                account.total_trades += 1
                if settings.crypto_real_notify:
                    await self._notify_close(pos, f"{action}/DUST", exit_price, pnl, account)
                return True

        # ── REAL SELL order ───────────────────────────────────────────
        # For TP exits: attempt limit order first (slippage protection).
        # If rejected or not filled, fallback to market order.
        # For SL/ROI exits: use market order immediately.
        try:
            if action in (EXIT_TP1, EXIT_TP2):
                tp_level = pos.take_profit_2 if action == EXIT_TP2 else pos.take_profit_1
                limit_price = tp_level * 0.998 if tp_level else price
                limit_price = max(limit_price, price)
                rules = await self.client.get_symbol_rules(pos.symbol)
                tick = rules.get("tick_size") or 1e-8
                limit_price = self._round_down_to_step(limit_price, tick)
                resp = await self.client.limit_sell(pos.symbol, qty_sell, limit_price)
            else:
                resp = await self.client.market_sell(pos.symbol, qty_sell)
            fill = self._parse_fill(resp)
        except Exception as e:
            err_str = str(e)
            # Error 3210 = "Total order value should be more than 5 USDT"
            # This position is dust — force-close it to stop the retry loop
            if "3210" in err_str or "min_notional" in err_str.lower() or "more than 5 USDT" in err_str:
                logger.warning(
                    f"⚡ {pos.symbol}: Order value too small to sell ({qty_sell*price:.4f} USDT). "
                    f"Force-closing as dust."
                )
                # BUG FIX: same as the pre-order dust path — book the REAL
                # market value, not -invested. The coins remain in the wallet.
                exit_price = price
                cost_basis = (qty_sell / qty) * (pos.invested or 0.0) if qty else 0.0
                pnl = (qty_sell * exit_price) - cost_basis
                pos.status = STATUS_CLOSED
                pos.exit_price = exit_price
                pos.exit_reason = f"{action}_DUST"
                pos.realized_pnl = pnl
                pos.closed_at = datetime.now(timezone.utc)
                account.realized_pnl += pnl
                account.total_trades += 1
                # Don't count as winning
                if settings.crypto_real_notify:
                    await self._notify_close(pos, f"{action}/DUST", exit_price, pnl, account)
                return True
            # A failed SELL must not be silently swallowed — keep position OPEN
            # so the next cycle can try again. Log loudly.
            # LIMIT-specific rejection (bad tick size / unknown param): retry
            # ONCE as a MARKET sell so a TP exit can never stay stuck open.
            if action in (EXIT_TP1, EXIT_TP2):
                logger.warning(
                    f"⚠️ {pos.symbol}: LIMIT sell rejected ({e}) — falling back to MARKET sell"
                )
                try:
                    resp = await self.client.market_sell(pos.symbol, qty_sell)
                    fill = self._parse_fill(resp)
                except Exception as e2:
                    logger.error(f"REAL SELL FAILED for {pos.symbol}: {e2}")
                    self.state["last_error"] = f"SELL_FAIL {pos.symbol}: {e2}"
                    return False
            else:
                logger.error(f"REAL SELL FAILED for {pos.symbol}: {e}")
                self.state["last_error"] = f"SELL_FAIL {pos.symbol}: {e}"
                return False

        exit_price = fill.get("price") or price
        proceeds = qty_sell * exit_price
        # BUG FIX: Calculate PnL based on qty_sold, not full invested amount.
        # When qty_sell < pos.quantity (due to rounding/fees), the unsold dust
        # stays in the wallet — it should NOT be counted as a loss.
        cost_basis = (qty_sell / qty) * (pos.invested or 0.0) if qty else 0
        pnl = proceeds - cost_basis

        session.add(CryptoPaperTrade(
            position_id=pos.id,
            symbol=pos.symbol,
            side={EXIT_TP1: SIDE_SELL_TP1, EXIT_TP2: SIDE_SELL_TP2,
                  EXIT_SL: SIDE_SELL_SL, EXIT_ROI: SIDE_SELL_ROI,
                  EXIT_MANUAL: SIDE_SELL_MANUAL}.get(action, SIDE_SELL_MANUAL),
            price=exit_price,
            quantity=qty_sell,
            quote_amount=proceeds,
            realized_pnl=pnl,
        ))

        account.realized_pnl += pnl
        account.total_trades += 1
        if pnl > 0:
            account.winning_trades += 1

        if partial_sell:
            # Shrink the position, mark TP1 done, keep it OPEN so the leftover
            # can ride to TP2 or be stopped by the trailing stop.
            pos.quantity = round(max(qty - qty_sell, 0.0), 12)
            pos.invested = max(0.0, (pos.invested or 0.0) - cost_basis)
            pos.tp1_partial_done = True
            logger.info(
                f"⚖️ REAL partial TP1 {pos.display or pos.symbol}: sold {qty_sell:.8f} "
                f"@ {exit_price} pnl={pnl:+.6f} {pos.quote}; {pos.quantity:.8f} left riding to TP2"
            )
            if settings.crypto_real_notify:
                await self._notify_partial_tp1(pos, exit_price, pnl, qty_sell)
            return "partial"

        pos.status = STATUS_CLOSED
        pos.exit_price = exit_price
        pos.exit_reason = action
        pos.realized_pnl = pnl
        pos.closed_at = datetime.now(timezone.utc)

        # Clean up BEP notification tracking
        self._bep_notified_positions.discard(str(pos.id))

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
        btc_bearish = is_btc_market_bearish(candidates)
        if btc_bearish and getattr(settings, "crypto_btc_filter_enabled", True):
            logger.info("⚠️ BTC trend is bearish — gating altcoin entries to prevent stop-outs")

        for c in sorted(candidates, key=lambda x: x.get("score", 0), reverse=True):
            if not self._passes_entry_gate(c, btc_bearish=btc_bearish):
                continue
            
            # Check SL cooldown
            symbol = c.get("symbol")
            if await self._in_sl_cooldown(session, symbol):
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

    def _passes_entry_gate(self, c: dict, btc_bearish: bool = False) -> bool:
        return passes_entry_gate(c, btc_bearish=btc_bearish)

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

        # Position size FLOOR: sizing right at the exchange NOTIONAL minimum
        # means fees + a tiny adverse move push the position below the sellable
        # threshold (dust trap → force-close). Enforce a comfortable floor
        # above the exchange minimum; skip when the balance can't support it.
        floor = settings.crypto_real_min_position_quote or 0
        if floor > min_notional and allocated < floor:
            if balance >= floor * 1.02:
                logger.info(
                    f"REAL BUY {symbol}: allocation {allocated:.2f} {quote} below "
                    f"{floor:.2f} position floor — sizing up to the floor"
                )
                allocated = floor
            else:
                logger.warning(
                    f"REAL BUY skipped {symbol}: balance {balance:.2f} {quote} cannot "
                    f"support the {floor:.2f} minimum position size"
                )
                return False

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
        # Defensive pegged-asset guard right before we commit money: catches
        # newly-listed stablecoins (e.g. U, RLUSD) that slipped past the static
        # blacklist. A peg trades flat ~1.00, so TP/SL levels are meaningless
        # and taker fees guarantee a loss.
        if await self._is_pegged(symbol):
            logger.warning(f"🛡️ REAL BUY refused {symbol}: pegged/stablecoin detected")
            self.state["last_error"] = f"BUY_REFUSED_PEGGED {symbol}"
            return False

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
            atr_value=levels.get("atr"),
            highest_price=exec_price,
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

    @staticmethod
    def _is_blacklisted(symbol: str) -> bool:
        """True when the base asset is pegged (stablecoin/gold/wrapped-staked)
        and must never be traded with TP/SL levels."""
        blacklist = {
            s.strip().upper()
            for s in (settings.crypto_real_symbol_blacklist or "").split(",")
            if s.strip()
        }
        base = (symbol or "").split("_")[0].strip().upper()
        return base in blacklist

    # Cache of symbols already known to be pegged → avoids a network call to
    # rule-check the same stablecoin over and over.
    __pegged_base_cache: set = set()

    async def _is_pegged(self, symbol: str) -> bool:
        """Robust pegged-asset guard: checks the configured blacklist AND,
        as a safety net for newly-listed stablecoins, the exchange LOT_SIZE /
        NOTIONAL rules (stablecoins show ~1.0/step and tiny min_qty). Safe to
        call before opening a REAL position — never trade a peg with TP/SL."""
        base = (symbol or "").split("_")[0].strip().upper()
        if base in RealTrader.__pegged_base_cache:
            return True
        if self._is_blacklisted(symbol):
            RealTrader.__pegged_base_cache.add(base)
            return True
        # Safety net: query symbol rules (cheap, cached) and reject anything
        # that looks like a 1:1 token (stepSize ~ 1.0/0.0001 range with a tiny
        # minQty is a stablecoin-style filter). Marks it so we don't re-check.
        try:
            rules = await self.client.get_symbol_rules(symbol)
            step = rules.get("step_size") or 0
            # Stablecoins peg at ~1.0 and trade in ~1-unit lots; real alts have
            # fractional step sizes well below 1.0.
            if step is not None and 0.5 <= step <= 1.05:
                RealTrader.__pegged_base_cache.add(base)
                logger.warning(f"🛡️ {symbol}: looks like a 1:1 pegged token (step={step}) — refusing REAL entry")
                return True
        except Exception:
            return False
        return False

    async def _in_sl_cooldown(self, session, symbol: str) -> bool:
        """Check if symbol is in SL cooldown period."""
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import select
        from app.models.crypto import CryptoPaperPosition
        
        cooldown_minutes = settings.crypto_real_sl_cooldown_minutes
        if cooldown_minutes <= 0:
            return False
        
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)
        
        result = await session.execute(
            select(CryptoPaperPosition.closed_at).where(
                CryptoPaperPosition.symbol == symbol,
                CryptoPaperPosition.mode == "REAL",
                # Cover both clean stop-outs and dust force-closes.
                # Removed MANUAL per user request so bot can re-enter immediately.
                CryptoPaperPosition.exit_reason.in_(["SL", "SL_DUST"]),
                CryptoPaperPosition.closed_at >= cutoff,
            ).order_by(CryptoPaperPosition.closed_at.desc()).limit(1)
        )
        row = result.first()
        return row is not None


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
            # For REAL mode, use actual exchange balance instead of paper default
            real_balance = await self._real_balance(quote) or 0.0
            account = CryptoPaperAccount(
                quote_asset=quote,
                initial_balance=real_balance,
                cash_balance=real_balance,
            )
            session.add(account)
            await session.flush()
        else:
            # Sync cash_balance with actual exchange balance on each access
            real_balance = await self._real_balance(quote)
            if real_balance is not None:
                account.cash_balance = real_balance
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
        pnl_pct = ((exit_price - pos.entry_price) / pos.entry_price * 100) if pos.entry_price else 0
        # Use 4 decimals for tiny PnL values so they don't show as 0.00
        pnl_str = f"{pnl:+.4f}" if abs(pnl) < 1 else f"{pnl:+.2f}"
        text = (
            f"{emoji} *REAL SELL ({action})*\n\n"
            f"🔹 {pos.display or pos.symbol}\n"
            f"💵 Entry: {_fmt_price(pos.entry_price)} {pos.quote}\n"
            f"🏁 Exit: {_fmt_price(exit_price)} {pos.quote}\n"
            f"💹 PnL: **{pnl_str} {pos.quote}** ({pnl_pct:+.2f}%)\n"
        )
        text += "🎉 *UNTUNG!*\n" if pnl >= 0 else "⚠️ *RUGI.*\n"
        text += await self._portfolio_summary(pos.quote)
        text += "\n_Order eksekusi real. Bukan saran investasi._"
        await self._send_telegram(text)

    async def _notify_partial_tp1(self, pos, exit_price: float, pnl: float, qty_sold: float) -> None:
        pnl_pct = ((exit_price - pos.entry_price) / pos.entry_price * 100) if pos.entry_price else 0
        pnl_str = f"{pnl:+.4f}" if abs(pnl) < 1 else f"{pnl:+.2f}"
        text = (
            f"⚖️ *REAL PARTIAL TP1* (uang sungguhan)\n\n"
            f"🔹 {pos.display or pos.symbol}\n"
            f"💵 Entry: {_fmt_price(pos.entry_price)} {pos.quote}\n"
            f"🏁 Jual {qty_sold:.8f} @ {_fmt_price(exit_price)} {pos.quote}\n"
            f"💹 PnL: **{pnl_str} {pos.quote}** ({pnl_pct:+.2f}%)\n"
            f"📦 Sisa {pos.quantity:.8f} lanjut ke TP2/trailing.\n"
        )
        await self._send_telegram(text)

    async def _notify_trailing_sl(self, pos, old_sl: float, new_sl: float, current_price: float) -> None:
        profit_pct = ((new_sl - pos.entry_price) / pos.entry_price * 100) if pos.entry_price else 0
        cur_profit = ((current_price - pos.entry_price) / pos.entry_price * 100) if pos.entry_price else 0
        text = (
            "📈 *REAL TRAILING SL RAISED* (uang sungguhan)\n\n"
            f"🔹 {pos.display or pos.symbol}\n"
            f"💵 Entry: {_fmt_price(pos.entry_price)} {pos.quote}\n"
            f"🚀 Harga Terkini: {_fmt_price(current_price)} {pos.quote} ({cur_profit:+.2f}%)\n"
            f"🛑 SL Lama: {_fmt_price(old_sl)} {pos.quote}\n"
            f"🔒 SL Baru: {_fmt_price(new_sl)} {pos.quote} (Terkunci {profit_pct:+.2f}%)\n\n"
            "✨ *Stop-Loss otomatis dinaikkan mengikuti kenaikan harga untuk mengamankan profit!*"
        )
        text += await self._portfolio_summary(pos.quote)
        text += "\n_Order eksekusi real. Bukan saran investasi._"
        await self._send_telegram(text)

    async def _notify_bep(self, pos, bep_price: float, current_price: float, side: str = "LONG") -> None:
        profit_pct = (
            ((current_price - pos.entry_price) / pos.entry_price * 100)
            if side == "LONG"
            else ((pos.entry_price - current_price) / pos.entry_price * 100)
        ) if pos.entry_price else 0
        text = (
            "🛡️ *REAL AUTO-BEP ACTIVATED* (uang sungguhan)\n\n"
            f"🔹 {pos.display or pos.symbol} ({side})\n"
            f"💵 Entry: {_fmt_price(pos.entry_price)} {pos.quote}\n"
            f"📈 Harga Saat Ini: {_fmt_price(current_price)} {pos.quote} ({profit_pct:+.2f}%)\n"
            f"🔒 SL Baru (BEP Lock): {_fmt_price(bep_price)} {pos.quote}\n\n"
            "✨ *Stop-Loss disesuaikan menutup round-trip fee (0.10%) + buffer slippage (0.05%).*\n"
            "Posisi kini telah RISK-FREE!"
        )
        text += await self._portfolio_summary(pos.quote)
        text += "\n_Order eksekusi real. Bukan saran investasi._"
        await self._send_telegram(text)

    async def _check_bep_notification(self, pos, current_price: float) -> None:
        """Check if position reached BEP threshold (or 50% to TP1) and send Telegram alert once."""
        if not getattr(settings, "crypto_real_bep_enabled", False):
            return
        entry = pos.entry_price
        if not entry or entry <= 0:
            return

        trigger_pct = getattr(settings, "crypto_real_bep_trigger_pct", 0.8)
        buffer_pct = getattr(settings, "crypto_real_bep_buffer_pct", 0.15)
        side = (getattr(pos, "side", None) or getattr(pos, "direction", "LONG") or "LONG").upper()
        tp1 = getattr(pos, "take_profit_1", None)

        if side == "SHORT":
            lowest = min(getattr(pos, "lowest_price", entry) or entry, current_price)
            profit_pct = (entry - lowest) / entry * 100.0
            half_tp1_pct = ((entry - tp1) / entry * 100.0 * 0.5) if (tp1 and tp1 < entry) else None
            effective_trigger = min(trigger_pct, half_tp1_pct) if half_tp1_pct is not None else trigger_pct
            bep_price = entry * (1.0 - buffer_pct / 100.0)
        else:
            highest = max(pos.highest_price or entry, current_price)
            profit_pct = (highest - entry) / entry * 100.0
            half_tp1_pct = ((tp1 - entry) / entry * 100.0 * 0.5) if (tp1 and tp1 > entry) else None
            effective_trigger = min(trigger_pct, half_tp1_pct) if half_tp1_pct is not None else trigger_pct
            bep_price = entry * (1.0 + buffer_pct / 100.0)

        if profit_pct >= effective_trigger:
            pos_key = str(pos.id)
            if pos_key not in self._bep_notified_positions:
                self._bep_notified_positions.add(pos_key)
                # Persist BEP stop_loss to position record in DB
                pos.stop_loss = bep_price
                logger.info(
                    f"🛡️ {pos.symbol} ({side}): Auto-BEP triggered (profit={profit_pct:+.2f}% >= {effective_trigger:.2f}%), "
                    f"locking SL at {bep_price:.6f}"
                )
                if settings.crypto_real_notify:
                    await self._notify_bep(pos, bep_price, current_price, side=side)

    async def _portfolio_summary(self, quote: str = "USDT") -> str:
        """Build portfolio summary: only show bot-traded positions (not full exchange balance)."""
        
        # Get open positions from database (only bot-traded coins)
        from app.db.session import async_session_factory
        from sqlalchemy import select, func
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
        
        # Realized PnL from REAL positions only — computed even when there are
        # no open positions so sell alerts always carry lifetime stats.
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
        except Exception as e:
            logger.warning(f"⚠️ Portfolio stats query failed: {e}")

        pnl_emoji = "✅" if realized >= 0 else "🔻"
        line = "\n━━━━━━━━━━━━━━━━━━━━\n"
        line += "💼 *PORTOFOLIO BOT (REAL)*\n\n"
        
        if not open_positions:
            line += f"📊 *Posisi Terbuka:* Tidak ada\n"
            try:
                cash = await self._real_balance(quote)
                if cash is not None:
                    line += f"💰 Saldo {quote}: **{_fmt_price(cash)}**\n"
            except Exception:
                pass
        else:
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
            
            line += f"📊 *Posisi Terbuka ({len(open_positions)}):*\n{holdings_text}\n"
            line += f"💰 Saldo {quote}: **{_fmt_price(cash)}**\n"
            line += f"🏦 Total Invested: **{_fmt_price(total_held_value)} {quote}**\n"
            line += f"💵 *TOTAL VALUE: **{_fmt_price(total_value)} {quote}***\n\n"
        
        line += f"{pnl_emoji} Total Realized PnL: **{realized:+,.2f} {quote}**\n"
        line += f"📊 Total Trade: {total_trades} ({winning} menang, {total_trades - winning} rugi)\n"
        line += "━━━━━━━━━━━━━━━━━━━━"
        return line

    async def _fetch_price(self, asset: str, quote: str) -> float:
        """Fetch current price for an asset from Tokocrypto public API with caching."""
        import time
        cache_key = f"{asset}_{quote}"
        now = time.time()
        
        # Check cache first
        if cache_key in self._price_cache:
            cached_price, cached_time = self._price_cache[cache_key]
            if now - cached_time < self._cache_ttl:
                return cached_price
        
        # Fetch from API if cache miss or expired
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
                    # Cache the price
                    self._price_cache[cache_key] = (price, now)
                    return price
            except Exception:
                continue
        # Tokocrypto rate-limited (429) or down — fall back to the Binance
        # public ticker so TP/SL protection never goes blind. USDT pairs only.
        if quote == "USDT":
            try:
                resp = await client.get(
                    "https://data-api.binance.vision/api/v3/ticker/price",
                    params={"symbol": f"{asset}{quote}"},
                )
                price = float(resp.json().get("price", 0))
                if price > 0:
                    logger.warning(
                        f"⚠️ {asset}{quote}: Tokocrypto unavailable, using Binance price"
                    )
                    self._price_cache[cache_key] = (price, now)
                    return price
            except Exception:
                pass
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