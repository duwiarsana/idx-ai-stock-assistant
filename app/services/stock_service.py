"""Stock service — business logic for stock data operations."""

import logging
from decimal import Decimal
from typing import Optional

import pandas as pd

from app.data.ingestion import stock_data_fetcher
from app.services.cache_service import cache_service

logger = logging.getLogger(__name__)


class StockService:
    """Orchestrates stock data fetching, caching, and processing."""

    def __init__(self):
        self.fetcher = stock_data_fetcher
        self.cache = cache_service

    async def get_stock_data(self, ticker: str) -> Optional[dict]:
        """
        Get full stock data with caching.

        Flow: Cache -> yfinance -> Cache (store)
        """
        ticker = ticker.upper().strip()

        # 1. Check cache first
        cached = await self.cache.get_stock_data(ticker)
        if cached:
            logger.debug(f"Cache hit for {ticker}")
            return cached

        # 2. Fetch from yfinance
        logger.info(f"Fetching fresh data for {ticker}")
        data = await self.fetcher.fetch_stock_data(ticker)
        if not data:
            return None

        # 3. Enrich with technical indicators
        data["technicals"] = self._calculate_technicals(data.get("history", []))

        # 4. Cache the result
        await self.cache.set_stock_data(ticker, data)

        return data

    async def get_quick_quote(self, ticker: str) -> Optional[dict]:
        """Get lightweight stock quote with caching."""
        ticker = ticker.upper().strip()

        cached = await self.cache.get_quick_quote(ticker)
        if cached:
            return cached

        quote = await self.fetcher.fetch_quick_quote(ticker)
        if quote:
            await self.cache.set_quick_quote(ticker, quote)

        return quote

    def _calculate_technicals(self, history: list[dict]) -> dict:
        """Calculate technical indicators from price history.

        Includes: RSI, SMA, MACD, Volume, ATR, Bollinger Bands, HH/HL pattern.
        """
        if len(history) < 14:
            return {"error": "Not enough data for technical analysis"}

        df = pd.DataFrame(history)
        for col in ("open", "high", "low", "close", "volume"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        close = df["close"]
        high = df["high"]
        low = df["low"]

        result = {}

        try:
            # ── RSI (14-period) ──────────────────────────
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            result["rsi_14"] = round(float(rsi.iloc[-1]), 2) if not rsi.empty else None

            # ── Moving Averages ──────────────────────────
            if len(close) >= 20:
                result["sma_20"] = round(float(close.rolling(20).mean().iloc[-1]), 2)
            if len(close) >= 50:
                result["sma_50"] = round(float(close.rolling(50).mean().iloc[-1]), 2)

            # ── MACD ─────────────────────────────────────
            if len(close) >= 26:
                ema12 = close.ewm(span=12, adjust=False).mean()
                ema26 = close.ewm(span=26, adjust=False).mean()
                macd_line = ema12 - ema26
                signal_line = macd_line.ewm(span=9, adjust=False).mean()
                macd_hist = macd_line - signal_line

                result["macd"] = round(float(macd_line.iloc[-1]), 2)
                result["macd_signal"] = round(float(signal_line.iloc[-1]), 2)
                result["macd_histogram"] = round(float(macd_hist.iloc[-1]), 2)

                # MACD signal interpretation
                if macd_hist.iloc[-1] > 0 and macd_hist.iloc[-2] <= 0:
                    result["macd_crossover"] = "bullish"
                elif macd_hist.iloc[-1] < 0 and macd_hist.iloc[-2] >= 0:
                    result["macd_crossover"] = "bearish"
                else:
                    result["macd_crossover"] = "neutral"

            # ── Volume Analysis ──────────────────────────
            vol = df["volume"]
            if len(vol) >= 20:
                avg_vol_20 = vol.rolling(20).mean().iloc[-1]
                current_vol = vol.iloc[-1]
                result["avg_volume_20d"] = int(avg_vol_20)
                result["volume_ratio"] = round(
                    float(current_vol / avg_vol_20), 2
                ) if avg_vol_20 > 0 else 0

            # ── ATR (14-period) ──────────────────────────
            if len(close) >= 15:
                prev_close = close.shift(1)
                tr = pd.concat([
                    high - low,
                    (high - prev_close).abs(),
                    (low - prev_close).abs(),
                ], axis=1).max(axis=1)
                atr_series = tr.rolling(window=14).mean()
                atr_val = float(atr_series.iloc[-1])
                result["atr_14"] = round(atr_val, 2)
                current_price = float(close.iloc[-1])
                result["atr_pct"] = round(atr_val / current_price * 100, 2) if current_price > 0 else 0

            # ── Bollinger Bands (20, 2) ──────────────────
            if len(close) >= 20:
                bb_mid = close.rolling(20).mean()
                bb_std = close.rolling(20).std()
                bb_upper = bb_mid + 2 * bb_std
                bb_lower = bb_mid - 2 * bb_std
                result["bb_upper"] = round(float(bb_upper.iloc[-1]), 2)
                result["bb_mid"] = round(float(bb_mid.iloc[-1]), 2)
                result["bb_lower"] = round(float(bb_lower.iloc[-1]), 2)
                bb_width = float(bb_upper.iloc[-1]) - float(bb_lower.iloc[-1])
                result["bb_width_pct"] = round(
                    bb_width / float(bb_mid.iloc[-1]) * 100, 2
                ) if float(bb_mid.iloc[-1]) > 0 else 0

            # ── Higher Highs / Higher Lows ───────────────
            if len(high) >= 10:
                window = 5
                recent_h = high.tail(window)
                prev_h = high.iloc[-(window * 2):-window]
                recent_l = low.tail(window)
                prev_l = low.iloc[-(window * 2):-window]
                result["higher_highs"] = bool(float(recent_h.max()) > float(prev_h.max()))
                result["higher_lows"] = bool(float(recent_l.min()) > float(prev_l.min()))

            # ── Price Position ───────────────────────────
            current_price = float(close.iloc[-1])
            high_52w = float(close.tail(252).max()) if len(close) >= 252 else float(close.max())
            low_52w = float(close.tail(252).min()) if len(close) >= 252 else float(close.min())

            if high_52w != low_52w:
                result["price_position_pct"] = round(
                    (current_price - low_52w) / (high_52w - low_52w) * 100, 2
                )
            else:
                result["price_position_pct"] = 50.0

            # ── Trend ────────────────────────────────────
            if len(close) >= 5:
                short_trend = close.iloc[-1] - close.iloc[-5]
                result["trend_5d"] = "up" if short_trend > 0 else "down"
                result["change_5d_pct"] = round(
                    float(short_trend / close.iloc[-5] * 100), 2
                ) if close.iloc[-5] != 0 else 0

            # ── Support / Resistance ─────────────────────
            sr_window = min(20, len(low))
            result["support"] = round(float(low.tail(sr_window).min()), 2)
            result["resistance"] = round(float(high.tail(sr_window).max()), 2)

        except Exception as e:
            logger.warning(f"Technical calculation error: {e}")
            result["error"] = str(e)

        return result

    def format_price_table(self, history: list[dict], last_n: int = 10) -> str:
        """Format recent price data as a readable table."""
        if not history:
            return "No data available"

        recent = history[-last_n:]
        lines = ["Date       | Close    | Volume      | Change"]
        lines.append("-" * 50)

        for i, day in enumerate(recent):
            change = ""
            if i > 0:
                prev = recent[i - 1]["close"]
                if prev > 0:
                    pct = (day["close"] - prev) / prev * 100
                    arrow = "📈" if pct > 0 else "📉" if pct < 0 else "➡️"
                    change = f"{arrow} {pct:+.2f}%"

            lines.append(
                f"{day['date']} | Rp {day['close']:>8,.0f} | {day['volume']:>11,} | {change}"
            )

        return "\n".join(lines)


# Singleton
stock_service = StockService()
