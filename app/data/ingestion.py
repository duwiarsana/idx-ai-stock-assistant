"""Stock data ingestion via yfinance.

Fetches OHLCV data for IDX stocks by appending .JK suffix to tickers.
Uses history() as the *primary* data source (reliable) and info as
optional enrichment (often rate-limited by Yahoo Finance — 429 errors).

All data is fetched asynchronously via thread executor to avoid blocking.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import pandas as pd
import yfinance as yf

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Max retries for yfinance history fetch
_MAX_RETRIES = 3
_RETRY_DELAY = 2  # seconds


class StockDataFetcher:
    """Fetches stock data from Yahoo Finance for IDX tickers."""

    @staticmethod
    def _to_jk_ticker(ticker: str) -> str:
        """Convert IDX ticker to Yahoo Finance format (e.g., BBCA -> BBCA.JK)."""
        ticker = ticker.upper().strip()
        if not ticker.endswith(".JK"):
            ticker = f"{ticker}.JK"
        return ticker

    async def fetch_stock_data(
        self,
        ticker: str,
        days: Optional[int] = None,
    ) -> Optional[dict]:
        """
        Fetch stock data (info + history) for an IDX ticker.

        Strategy: history() first (reliable), info optional (often 429).

        Returns:
            dict with keys: info, history, current_price, etc.
            None if ticker not found or error.
        """
        if days is None:
            days = settings.stock_data_days

        jk_ticker = self._to_jk_ticker(ticker)
        loop = asyncio.get_event_loop()

        try:
            result = await loop.run_in_executor(
                None, self._fetch_sync, jk_ticker, days
            )
            return result
        except Exception as e:
            logger.error(f"Error fetching data for {ticker}: {e}")
            return None

    def _fetch_history_with_retry(
        self, stock: yf.Ticker, start_date, end_date, retries: int = _MAX_RETRIES
    ) -> pd.DataFrame:
        """Fetch history with retry & exponential backoff."""
        for attempt in range(retries):
            try:
                history = stock.history(start=start_date, end=end_date)
                if not history.empty:
                    return history
            except Exception as e:
                logger.warning(
                    f"History fetch attempt {attempt + 1}/{retries} failed: {e}"
                )

            if attempt < retries - 1:
                delay = _RETRY_DELAY * (2 ** attempt)
                logger.info(f"Retrying in {delay}s…")
                time.sleep(delay)

        return pd.DataFrame()

    def _fetch_sync(self, jk_ticker: str, days: int) -> Optional[dict]:
        """Synchronous fetch — history-first strategy.

        Unlike the previous approach that required ``stock.info`` (which hits
        the ``quoteSummary`` endpoint that is heavily rate-limited), this
        fetches OHLCV history first and derives price data from it.  ``info``
        is attempted only *optionally* for enrichment (name, sector, etc.).
        """
        try:
            stock = yf.Ticker(jk_ticker)

            # ── 1. Fetch history (primary — most reliable) ────────────
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            history = self._fetch_history_with_retry(stock, start_date, end_date)

            if history.empty:
                logger.warning(f"No historical data for {jk_ticker}")
                return None

            # ── 2. Derive price data from history ─────────────────────
            processed = self._process_history(history)
            if not processed:
                return None

            last_bar = processed[-1]
            current_price = last_bar["close"]
            current_volume = last_bar["volume"]

            # Previous close from 2nd-to-last bar
            prev_close = processed[-2]["close"] if len(processed) >= 2 else current_price
            change = current_price - prev_close
            change_pct = (change / prev_close * 100) if prev_close else 0

            # 52-week high/low from history
            all_highs = [bar["high"] for bar in processed]
            all_lows = [bar["low"] for bar in processed]
            high_52w = max(all_highs) if all_highs else current_price
            low_52w = min(all_lows) if all_lows else current_price

            # Average volume from last 20 bars
            recent_vols = [bar["volume"] for bar in processed[-20:]]
            avg_volume = int(sum(recent_vols) / len(recent_vols)) if recent_vols else 0

            # ── 3. Try to get info (optional — may fail with 429) ─────
            name = jk_ticker.replace(".JK", "")
            sector = None
            industry = None
            market_cap = None
            raw_info = {}

            try:
                info = stock.info
                if info and isinstance(info, dict):
                    name = info.get("longName") or info.get("shortName") or name
                    sector = info.get("sector")
                    industry = info.get("industry")
                    market_cap = info.get("marketCap")

                    # Override with more accurate real-time values if available
                    rt_price = info.get("regularMarketPrice")
                    if rt_price and rt_price > 0:
                        current_price = rt_price
                    rt_prev = info.get("regularMarketPreviousClose")
                    if rt_prev and rt_prev > 0:
                        prev_close = rt_prev
                        change = current_price - prev_close
                        change_pct = (change / prev_close * 100) if prev_close else 0
                    rt_vol = info.get("regularMarketVolume")
                    if rt_vol and rt_vol > 0:
                        current_volume = rt_vol
                    h52 = info.get("fiftyTwoWeekHigh")
                    if h52:
                        high_52w = h52
                    l52 = info.get("fiftyTwoWeekLow")
                    if l52:
                        low_52w = l52
                    avg_vol_info = info.get("averageVolume")
                    if avg_vol_info:
                        avg_volume = avg_vol_info

                    raw_info = {
                        k: v for k, v in info.items()
                        if k in self._USEFUL_INFO_KEYS
                    }
            except Exception as info_err:
                logger.info(
                    f"stock.info skipped for {jk_ticker} (rate-limited): "
                    f"{type(info_err).__name__}"
                )
                # Proceed with history-derived data — this is OK

            return {
                "ticker": jk_ticker.replace(".JK", ""),
                "name": name,
                "sector": sector,
                "industry": industry,
                "current_price": Decimal(str(round(current_price, 2))),
                "previous_close": Decimal(str(round(prev_close, 2))),
                "change": Decimal(str(round(change, 2))),
                "change_pct": Decimal(str(round(change_pct, 4))),
                "volume": current_volume,
                "market_cap": market_cap,
                "high_52w": high_52w,
                "low_52w": low_52w,
                "avg_volume": avg_volume,
                "avg_volume_10d": None,
                "currency": "IDR",
                "history": processed,
                "raw_info": raw_info,
            }

        except Exception as e:
            logger.error(f"yfinance error for {jk_ticker}: {e}")
            return None

    def _process_history(self, df: pd.DataFrame) -> list[dict]:
        """Convert pandas DataFrame to list of dicts."""
        records = []
        for idx, row in df.iterrows():
            records.append({
                "date": idx.strftime("%Y-%m-%d"),
                "open": float(row.get("Open", 0)),
                "high": float(row.get("High", 0)),
                "low": float(row.get("Low", 0)),
                "close": float(row.get("Close", 0)),
                "volume": int(row.get("Volume", 0)),
            })
        return records

    async def fetch_quick_quote(self, ticker: str) -> Optional[dict]:
        """Fetch just the current quote — uses history as fallback."""
        jk_ticker = self._to_jk_ticker(ticker)
        loop = asyncio.get_event_loop()

        try:
            return await loop.run_in_executor(
                None, self._fetch_quick_sync, jk_ticker
            )
        except Exception as e:
            logger.error(f"Quick quote error for {ticker}: {e}")
            return None

    def _fetch_quick_sync(self, jk_ticker: str) -> Optional[dict]:
        """Quick quote sync fetch — info first, history fallback."""
        ticker_clean = jk_ticker.replace(".JK", "")

        # Try info first
        try:
            stock = yf.Ticker(jk_ticker)
            info = stock.info

            if info and info.get("regularMarketPrice") is not None:
                current = info.get("regularMarketPrice", 0)
                prev = info.get("regularMarketPreviousClose", 0)
                change = current - prev if prev else 0
                change_pct = (change / prev * 100) if prev else 0

                return {
                    "ticker": ticker_clean,
                    "name": info.get("longName", info.get("shortName", ticker_clean)),
                    "price": Decimal(str(current)),
                    "change": Decimal(str(round(change, 2))),
                    "change_pct": Decimal(str(round(change_pct, 2))),
                    "volume": info.get("regularMarketVolume", 0),
                }
        except Exception:
            pass  # Fall through to history

        # Fallback: derive from last 5 days of history
        try:
            stock = yf.Ticker(jk_ticker)
            hist = stock.history(period="5d")

            if hist.empty or len(hist) < 1:
                return None

            current = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current
            change = current - prev
            change_pct = (change / prev * 100) if prev else 0
            volume = int(hist["Volume"].iloc[-1])

            return {
                "ticker": ticker_clean,
                "name": ticker_clean,
                "price": Decimal(str(round(current, 2))),
                "change": Decimal(str(round(change, 2))),
                "change_pct": Decimal(str(round(change_pct, 2))),
                "volume": volume,
            }
        except Exception:
            return None

    # Keys we want to extract from yfinance info dict
    _USEFUL_INFO_KEYS = {
        "longName", "shortName", "sector", "industry",
        "regularMarketPrice", "regularMarketPreviousClose",
        "regularMarketVolume", "marketCap",
        "fiftyTwoWeekHigh", "fiftyTwoWeekLow",
        "averageVolume", "averageDailyVolume10Day",
        "trailingPE", "forwardPE", "priceToBook",
        "dividendYield", "beta", "currency",
        "recommendationKey", "numberOfAnalystOpinions",
    }


# Singleton
stock_data_fetcher = StockDataFetcher()
