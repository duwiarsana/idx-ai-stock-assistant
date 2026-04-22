"""Stock data ingestion via yfinance.

Fetches OHLCV data for IDX stocks by appending .JK suffix to tickers.
All data is fetched asynchronously via thread executor to avoid blocking.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import pandas as pd
import yfinance as yf

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


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

    def _fetch_sync(self, jk_ticker: str, days: int) -> Optional[dict]:
        """Synchronous fetch (runs in thread pool)."""
        try:
            stock = yf.Ticker(jk_ticker)
            info = stock.info

            # Check if ticker is valid
            if not info or info.get("regularMarketPrice") is None:
                logger.warning(f"Ticker {jk_ticker} not found or has no data")
                return None

            # Fetch historical data
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            history = stock.history(start=start_date, end=end_date)

            if history.empty:
                logger.warning(f"No historical data for {jk_ticker}")
                return None

            # Build response
            current_price = info.get("regularMarketPrice", 0)
            prev_close = info.get("regularMarketPreviousClose", 0)
            change = current_price - prev_close if prev_close else 0
            change_pct = (change / prev_close * 100) if prev_close else 0

            return {
                "ticker": jk_ticker.replace(".JK", ""),
                "name": info.get("longName", info.get("shortName", "Unknown")),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "current_price": Decimal(str(current_price)),
                "previous_close": Decimal(str(prev_close)),
                "change": Decimal(str(round(change, 2))),
                "change_pct": Decimal(str(round(change_pct, 4))),
                "volume": info.get("regularMarketVolume", 0),
                "market_cap": info.get("marketCap"),
                "high_52w": info.get("fiftyTwoWeekHigh"),
                "low_52w": info.get("fiftyTwoWeekLow"),
                "avg_volume": info.get("averageVolume"),
                "avg_volume_10d": info.get("averageDailyVolume10Day"),
                "currency": info.get("currency", "IDR"),
                "history": self._process_history(history),
                "raw_info": {
                    k: v for k, v in info.items()
                    if k in self._USEFUL_INFO_KEYS
                },
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
        """Fetch just the current quote (lighter than full data)."""
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
        """Quick quote sync fetch."""
        try:
            stock = yf.Ticker(jk_ticker)
            info = stock.info

            if not info or info.get("regularMarketPrice") is None:
                return None

            current = info.get("regularMarketPrice", 0)
            prev = info.get("regularMarketPreviousClose", 0)
            change = current - prev if prev else 0
            change_pct = (change / prev * 100) if prev else 0

            return {
                "ticker": jk_ticker.replace(".JK", ""),
                "name": info.get("longName", info.get("shortName", "Unknown")),
                "price": Decimal(str(current)),
                "change": Decimal(str(round(change, 2))),
                "change_pct": Decimal(str(round(change_pct, 2))),
                "volume": info.get("regularMarketVolume", 0),
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
