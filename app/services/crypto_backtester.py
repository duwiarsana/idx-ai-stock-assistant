"""Backtesting engine for the Tokocrypto momentum paper-trading strategy.

Simulates the exact entry gate + SL/TP exit logic used by ``crypto_paper``
on historical klines, so parameters (entry score, pullback %, ATR multiples,
cooldown) can be validated / tuned from data instead of guesswork.

The engine reuses the *same* primitives as production:
  - ``compute_indicator_summary`` (indicators)
  - ``compute_momentum_score`` (scoring)
  - ``compute_price_levels`` (entry / TP1 / TP2 / SL)
  - the paper entry-gate rules (uptrend + MACD bullish + pullback)
so a positive backtest result means the live strategy has a real edge.

Usage:
    python -m app.services.crypto_backtester --days 60 --symbols BTCUSDT,ETHUSDT
    python -m app.services.crypto_backtester --days 60 --top 15
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.config import get_settings
from app.data.tokocrypto_client import TokocryptoClient
from app.services.crypto_indicators import compute_indicator_summary, candles_to_closes
from app.services.crypto_levels import compute_price_levels, TP1_ATR_MULT, TP2_ATR_MULT, SL_ATR_MULT
from app.services.crypto_scoring import compute_momentum_score

logger = logging.getLogger(__name__)

PRICE_CHANGE_LOOKBACKS = {"1h": 1, "4h": 4, "24h": 24}
WARMUP_BARS = 200  # matching KLINE_LIMIT used by the live scanner


@dataclass
class BacktestParams:
    entry_score: float = 80.0
    require_uptrend: bool = True
    pullback_max_pct: float = 3.0
    tp1_mult: float = TP1_ATR_MULT
    tp2_mult: float = TP2_ATR_MULT
    sl_mult: float = SL_ATR_MULT
    cooldown_bars: int = 2  # 2 x 1h bars ~= the 120-min live cooldown


@dataclass
class Trade:
    symbol: str
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    exit_reason: str  # TP1 / TP2 / SL
    pnl_pct: float = 0.0
    bars_held: int = 0


@dataclass
class BacktestResult:
    symbol: str
    start: datetime
    end: datetime
    trades: list[Trade] = field(default_factory=list)

    @property
    def n_trades(self) -> int:
        return len(self.trades)

    def metrics(self) -> dict:
        """Win rate, expectancy, profit factor, drawdown on cumulative return."""
        if not self.trades:
            return {
                "trades": 0, "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
                "expectancy_pct": 0.0, "profit_factor": 0.0, "total_return_pct": 0.0,
                "max_drawdown_pct": 0.0, "avg_bars_held": 0.0,
                "tp1": 0, "tp2": 0, "sl": 0,
            }

        wins = [t.pnl_pct for t in self.trades if t.pnl_pct > 0]
        losses = [t.pnl_pct for t in self.trades if t.pnl_pct <= 0]
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        gross_win = sum(wins)
        gross_loss = -sum(losses)
        profit_factor = gross_win / gross_loss if gross_loss > 0 else float("inf")

        # Cumulative compounded return and max drawdown from the PnL sequence.
        equity = 1.0
        peak = 1.0
        max_dd = 0.0
        for t in self.trades:
            equity *= (1 + t.pnl_pct / 100.0)
            peak = max(peak, equity)
            dd = (peak - equity) / peak * 100.0
            max_dd = max(max_dd, dd)

        win_rate = len(wins) / len(self.trades) * 100.0
        return {
            "trades": self.n_trades,
            "win_rate": round(win_rate, 1),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "expectancy_pct": round((avg_win * len(wins) + avg_loss * len(losses)) / len(self.trades), 2),
            "profit_factor": round(profit_factor, 2) if math.isfinite(profit_factor) else None,
            "total_return_pct": round((equity - 1) * 100, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "avg_bars_held": round(sum(t.bars_held for t in self.trades) / self.n_trades, 1),
            "tp1": sum(1 for t in self.trades if t.exit_reason == "TP1"),
            "tp2": sum(1 for t in self.trades if t.exit_reason == "TP2"),
            "sl": sum(1 for t in self.trades if t.exit_reason == "SL"),
        }


class CryptoBacktester:
    def __init__(self, client: Optional[TokocryptoClient] = None, params: Optional[BacktestParams] = None):
        self.client = client or TokocryptoClient()
        self.params = params or BacktestParams()

    async def close(self) -> None:
        await self.client.close()

    async def fetch_history(self, symbol: str, days: int = 60) -> dict[str, list[dict]]:
        """Paginate 15m klines back from now; resample to 1h.

        Returns ``{"15m": [...], "1h": [...]}``. Using 15m for the summary +
        exit simulation is closer to the live scanner (which uses 5m/15m/1h).
        """
        end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_ms = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)

        async def _page(interval: str) -> list[dict]:
            cursor = start_ms
            out: list[dict] = []
            while cursor < end_ms:
                payload = await self.client._request("https://www.tokocrypto.site/api/v3/klines", params={
                    "symbol": symbol.replace("_", ""),
                    "interval": interval,
                    "limit": 1000,
                    "startTime": cursor,
                    "endTime": end_ms,
                })
                rows = payload if isinstance(payload, list) else payload.get("data", [])
                parsed = []
                for row in rows:
                    if not isinstance(row, (list, tuple)) or len(row) < 6:
                        continue
                    try:
                        parsed.append({
                            "openTime": int(row[0]),
                            "open": float(row[1]),
                            "high": float(row[2]),
                            "low": float(row[3]),
                            "close": float(row[4]),
                            "volume": float(row[5]),
                            "quoteVolume": float(row[7]) if len(row) > 7 else None,
                            "numTrades": int(row[8]) if len(row) > 8 else None,
                        })
                    except (TypeError, ValueError):
                        continue
                if not parsed:
                    break
                out = out + parsed
                newest = parsed[-1]["openTime"]
                if len(parsed) < 1000 or newest >= end_ms:
                    break
                cursor = newest + 1
                await asyncio.sleep(0.15)
            return out

        c15 = await _page("15m")
        c1h = _resample_1h(c15)
        return {"15m": c15, "1h": c1h}

    def _candidate_at(self, klines: dict[str, list[dict]], end_idx: int) -> Optional[dict]:
        """Build the same candidate dict the live scanner produces.

        ``end_idx`` indexes the 1h bars; 15m bars are those strictly before the
        end of 1h bar ``end_idx``.
        """
        c1h = klines["1h"]
        c15 = klines["15m"]
        window1h = c1h[max(0, end_idx - WARMUP_BARS):end_idx]
        if len(window1h) < 60:
            return None
        s1h = compute_indicator_summary(window1h)

        # 15m bars inside the same trailing window (end of 1h bar end_idx-1).
        end_15m = c1h[end_idx - 1]["openTime"] + 3600_000 if end_idx >= 1 else window1h[-1]["openTime"] + 3600_000
        win15 = [b for b in c15 if b["openTime"] < end_15m][-WARMUP_BARS:]
        s15 = compute_indicator_summary(win15) if len(win15) >= 60 else {}

        closes = candles_to_closes(window1h)
        price_change = {k: _pct_change(closes, bars) for k, bars in PRICE_CHANGE_LOOKBACKS.items()}
        score, _ = compute_momentum_score({"5m": s15, "15m": s15, "1h": s1h}, price_change)
        levels = compute_price_levels(
            {"1h": s1h},
            window1h,
            ticker={"lastPrice": s1h.get("price")},
            tp1_mult=self.params.tp1_mult,
            tp2_mult=self.params.tp2_mult,
            sl_mult=self.params.sl_mult,
        )
        return {
            "symbol": "",
            "score": score,
            "price": s1h.get("price"),
            "price_change": price_change,
            "tf_summaries": {"5m": s15, "15m": s15, "1h": s1h},
            "price_levels": levels.to_dict(),
        }

    def _passes_gate(self, c: dict) -> bool:
        """Mirror of crypto_paper._passes_entry_gate for the backtest params."""
        p = self.params
        if (c.get("score") or 0) < p.entry_score:
            return False
        s1h = (c.get("tf_summaries") or {}).get("1h") or {}
        if p.require_uptrend:
            if s1h.get("trend") != "bullish":
                return False
            if s1h.get("macd_state") != "bullish":
                return False
        price = s1h.get("price")
        ema20 = s1h.get("ema20")
        if ema20 and price:
            max_above = ema20 * (1 + p.pullback_max_pct / 100.0)
            if price > max_above:
                return False
            if s1h.get("at_high"):
                return False
        return True

    def run_symbol(self, klines: dict[str, list[dict]], symbol: str) -> BacktestResult:
        """Walk the 1h bars bar-by-bar, opening trades when the gate passes.

        No look-ahead: the signal uses only bars strictly before the entry bar,
        and entry executes at the OPEN of the bar after the signal. Exits are
        checked on each 15m bar for finer resolution (closer to the live
        per-scan check).
        """
        p = self.params
        c1h = klines["1h"]
        c15 = klines["15m"]
        result = BacktestResult(symbol=symbol, start=datetime.fromtimestamp(c1h[0]["openTime"] / 1000, tz=timezone.utc),
                                end=datetime.fromtimestamp(c1h[-1]["openTime"] / 1000, tz=timezone.utc))

        i = WARMUP_BARS
        last_exit_ms = 0
        while i < len(c1h) - 1:
            entry_bar = c1h[i]  # bar AFTER the signal
            if (entry_bar["openTime"] - last_exit_ms) < (p.cooldown_bars * 3600_000):
                i += 1
                continue
            cand = self._candidate_at(klines, i)
            if cand and self._passes_gate(cand):
                levels = cand.get("price_levels") or {}
                entry_price = levels.get("entry") or cand.get("price") or entry_bar["open"]
                tp1 = levels.get("take_profit_1")
                tp2 = levels.get("take_profit_2")
                sl = levels.get("stop_loss")
                if not (entry_price and tp1 and tp2 and sl and sl < entry_price < tp1):
                    i += 1
                    continue

                # Scan 15m bars forward (starting at entry bar) for TP/SL hits.
                # Simulates realistic exit: SL triggers with slippage (worse price).
                entry_ts = entry_bar["openTime"]
                exit_reason = None
                exit_price = None
                exit_15m_idx = None
                highest_price = entry_price  # for trailing stop logic
                for j, bar in enumerate(c15):
                    if bar["openTime"] < entry_ts:
                        continue
                    
                    # Track highest price for potential trailing stop
                    if bar["high"] > highest_price:
                        highest_price = bar["high"]
                    
                    # Trailing stop: 1.2×ATR below highest (mimics paper trading)
                    atr = (entry_price * 0.02)  # approximate ATR
                    trailing_stop = highest_price - (atr * 1.2)
                    effective_sl = max(sl, trailing_stop)
                    
                    # Check exits in priority: SL first (with slippage), then TP
                    if bar["low"] <= effective_sl:
                        # SL hit with 0.1% slippage (realistic in volatile market)
                        slippage = entry_price * 0.001
                        exit_reason, exit_price, exit_15m_idx = "SL", max(sl - slippage, bar["low"]), j
                        break
                    if bar["high"] >= tp2:
                        exit_reason, exit_price, exit_15m_idx = "TP2", tp2, j
                        break
                    if bar["high"] >= tp1:
                        exit_reason, exit_price, exit_15m_idx = "TP1", tp1, j
                        break

                if exit_15m_idx is None:
                    exit_price = c15[-1]["close"]
                    exit_reason = "END"
                    exit_15m_idx = len(c15) - 1

                pnl_pct = (exit_price - entry_price) / entry_price * 100.0
                exit_time = datetime.fromtimestamp(c15[exit_15m_idx]["openTime"] / 1000, tz=timezone.utc)
                result.trades.append(Trade(
                    symbol=symbol,
                    entry_time=datetime.fromtimestamp(entry_ts / 1000, tz=timezone.utc),
                    entry_price=entry_price,
                    exit_time=exit_time,
                    exit_price=exit_price,
                    exit_reason=exit_reason,
                    pnl_pct=pnl_pct,
                    bars_held=round((c15[exit_15m_idx]["openTime"] - entry_ts) / 3600_000, 1),
                ))
                last_exit_ms = c15[exit_15m_idx]["openTime"]

                # Advance i to the 1h bar containing the exit + cooldown.
                exit_hour_ts = c15[exit_15m_idx]["openTime"]
                i = next((k for k in range(i, len(c1h)) if c1h[k]["openTime"] > exit_hour_ts), len(c1h) - 1)
                continue
            i += 1

        return result


def _pct_change(closes: list[float], bars: int) -> Optional[float]:
    if len(closes) <= bars or bars <= 0:
        return None
    if closes[-1 - bars] == 0:
        return None
    return (closes[-1] - closes[-1 - bars]) / closes[-1 - bars] * 100.0


def _resample_1h(c15: list[dict]) -> list[dict]:
    """Aggregate 15m candles into 1h OHLCV bars (aligned to the hour)."""
    out: list[dict] = []
    current: Optional[dict] = None
    hour_start: Optional[int] = None
    for b in c15:
        h = b["openTime"] - (b["openTime"] % 3600_000)
        if hour_start is None or h != hour_start:
            if current is not None:
                out.append(current)
            hour_start = h
            current = {
                "openTime": h,
                "open": b["open"],
                "high": b["high"],
                "low": b["low"],
                "close": b["close"],
                "volume": b["volume"],
                "quoteVolume": b.get("quoteVolume"),
            }
        else:
            current["high"] = max(current["high"], b["high"])
            current["low"] = min(current["low"], b["low"])
            current["close"] = b["close"]
            current["volume"] += b["volume"]
    if current is not None:
        out.append(current)
    return out


async def pick_liquid_symbols(client: TokocryptoClient, quote: str, top: int) -> list[str]:
    """Return the top-N liquid symbols for a quote asset by 24h quote volume.

    Stablecoins / pegged assets are excluded — their tiny ATR produces noise
    trades that distort backtest results.
    """
    from app.config import get_settings
    stable = {
        b.strip().upper()
        for b in get_settings().crypto_stablecoin_quotes.split(",")
    } | {"USDC", "USD1", "RLUSD", "TUSD", "DAI", "FDUSD", "EUR", "EURT", "AEUR", "USDE", "USDL", "PAXG"}

    symbols = await client.fetch_symbols()
    tickers = await client.fetch_tickers()
    candidates = []
    for s in symbols:
        if s.quote != quote or s.symbol_type != 1:
            continue
        if s.base.upper() in stable:
            continue
        t = tickers.get(f"{s.base}{quote}") or tickers.get(s.raw_symbol.replace("_", ""))
        if not t:
            continue
        qv = t.get("quoteVolume") or 0.0
        if qv <= 0:
            continue
        candidates.append((s.raw_symbol, qv))
    candidates.sort(key=lambda x: x[1], reverse=True)
    return [sym for sym, _ in candidates[:top]]


async def run_backtest(args) -> None:
    client = TokocryptoClient()
    params = BacktestParams(
        entry_score=args.entry_score,
        pullback_max_pct=args.pullback,
    )
    backtester = CryptoBacktester(client=client, params=params)

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        logger.info("Picking liquid symbols by 24h quote volume...")
        symbols = await pick_liquid_symbols(client, "USDT", args.top)
        logger.info(f"Selected {len(symbols)} symbols: {', '.join(symbols[:8])}...")

    all_trades = 0
    agg_metrics = {}
    per_symbol = []
    for sym in symbols:
        try:
            klines = await backtester.fetch_history(sym, days=args.days)
            c1h = klines["1h"]
            if len(c1h) < WARMUP_BARS + 20:
                logger.warning(f"  {sym}: not enough history ({len(c1h)} bars), skipped")
                continue
            res = backtester.run_symbol(klines, sym)
            m = res.metrics()
            per_symbol.append((sym, m))
            all_trades += m["trades"]
            for k, v in m.items():
                if k in ("tp1", "tp2", "sl"):
                    continue
                if isinstance(v, (int, float)):
                    agg_metrics[k] = agg_metrics.get(k, 0) + (v * m["trades"] if k != "trades" else v)
            logger.info(f"  {sym}: {m['trades']} trades, WR {m['win_rate']}%, "
                        f"PF {m['profit_factor']}, ret {m['total_return_pct']}%")
        except Exception as e:
            logger.warning(f"  {sym}: failed ({e})")

    print("\n" + "=" * 70)
    print("BACKTEST SUMMARY — crypto momentum paper strategy")
    print(f"Window: {args.days} days, {len(per_symbol)} symbols, {all_trades} trades")
    print("=" * 70)
    for sym, m in per_symbol:
        print(f"  {sym:16s} n={m['trades']:3d} WR={m['win_rate']:5.1f}% "
              f"avgW={m['avg_win']:6.2f}% avgL={m['avg_loss']:6.2f}% "
              f"PF={m['profit_factor']} ret={m['total_return_pct']:7.2f}% dd={m['max_drawdown_pct']:.2f}%")
    print("-" * 70)
    n = len(per_symbol)
    if n and all_trades:
        total_ret = sum(m["total_return_pct"] for _, m in per_symbol) / n
        avg_wr = sum(m["win_rate"] for _, m in per_symbol) / n
        print(f"AVERAGE per symbol: {avg_wr:.1f}% win rate, {total_ret:+.2f}% return")
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest crypto momentum paper strategy")
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--symbols", type=str, default="")
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--entry-score", type=float, default=80.0)
    parser.add_argument("--pullback", type=float, default=3.0)
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    asyncio.run(run_backtest(args))


if __name__ == "__main__":
    main()