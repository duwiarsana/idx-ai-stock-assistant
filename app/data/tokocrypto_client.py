"""Tokocrypto public market data client.

Only public (security type NONE) endpoints are used, so no API secret is
required. The adapter is intentionally tolerant to response-shape variance:

* Tokocrypto wraps some responses in ``{code, msg, data, timestamp}`` envelopes
  while other endpoints return a bare JSON list/object.
* Pair symbols appear as ``BTC_USDT`` in ``/open/v1/common/symbols`` but as
  ``BTCUSDT`` on the v3 market-data endpoints (engine type 1).
* Some pairs moved to a new engine (type 3) served from a different host.

This module normalises all of that so the rest of the codebase only ever sees
plain lists of dicts.
"""

import asyncio
import logging
from typing import Any, Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

BASE_URL_MAIN = "https://www.tokocrypto.com"
BASE_URL_MARKET_V3 = "https://www.tokocrypto.site"
BASE_URL_MARKET_V1 = "https://cloudme-toko.2meta.app"

KLINES_INTERVALS = ("1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M")

# Stablecoin quote assets used for pair filtering (there is no metadata API).
DEFAULT_STABLEQUOTES = {"USDT", "USDC", "BUSD", "DAI", "TUSD", "FRAX", "PAX", "FDUSD"}


class TokocryptoError(Exception):
    """Base error for Tokocrypto client failures."""


class TokocryptoResponseError(TokocryptoError):
    """Non-zero API code or invalid payload shape."""


class TokocryptoSymbol:
    """Normalised view of a trading pair from ``/open/v1/common/symbols``."""

    __slots__ = ("raw_symbol", "base", "quote", "symbol_type", "spot_trading")

    def __init__(self, raw_symbol: str, base: str, quote: str, symbol_type: Any, spot_trading: bool):
        self.raw_symbol = raw_symbol          # e.g. "BTC_USDT"
        self.base = base
        self.quote = quote
        self.symbol_type = int(symbol_type or 1) if symbol_type not in (None, "") else 1
        self.spot_trading = spot_trading

    @property
    def normalized_symbol(self) -> str:
        """Symbol as used on v3 (engine type 1) endpoints, e.g. ``BTCUSDT``."""
        return self.raw_symbol.replace("_", "")

    @property
    def display(self) -> str:
        """Human friendly form, e.g. ``BTC/USDT``."""
        return f"{self.base}/{self.quote}"

    def market_url(self, endpoint: str) -> str:
        """Pick the correct market-data base URL for this symbol."""
        if self.symbol_type == 1:
            return f"{BASE_URL_MARKET_V3}/api/v3/{endpoint}"
        return f"{BASE_URL_MARKET_V1}/api/v1/{endpoint}"

    def to_dict(self) -> dict:
        return {
            "symbol": self.raw_symbol,
            "baseAsset": self.base,
            "quoteAsset": self.quote,
            "type": self.symbol_type,
            "spotTradingEnable": int(self.spot_trading),
        }


class TokocryptoClient:
    """Async client for Tokocrypto public market data."""

    def __init__(self, timeout: Optional[int] = None, max_retries: int = 3):
        self.timeout = timeout or settings.crypto_api_timeout
        self.max_retries = max_retries or settings.crypto_max_retries
        self._client: Optional[httpx.AsyncClient] = None
        self._semaphore = asyncio.Semaphore(settings.crypto_max_concurrency)
        # (cache_ts, list[TokocryptoSymbol])
        self._symbols_cache: tuple[Optional[float], Optional[list[TokocryptoSymbol]]] = (None, None)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def _request(self, url: str, params: Optional[dict] = None) -> Any:
        """GET with concurrency guard + simple retry with exponential backoff."""
        client = await self._get_client()
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            async with self._semaphore:
                try:
                    resp = await client.get(url, params=params)
                    if resp.status_code in (429, 418, 403):
                        retry_after = resp.headers.get("Retry-After")
                        delay = float(retry_after) if retry_after else 2 ** attempt
                        logger.warning(
                            f"Tokocrypto rate limited ({resp.status_code}) for {url}, "
                            f"waiting {delay}s (attempt {attempt}/{self.max_retries})"
                        )
                        await asyncio.sleep(delay)
                        last_error = TokocryptoResponseError(f"rate limited: {resp.status_code}")
                        continue
                    resp.raise_for_status()
                    return self._extract_data(resp.json(), url)
                except httpx.TimeoutException as e:
                    logger.warning(f"Tokocrypto timeout for {url}: {e}")
                    last_error = e
                except httpx.HTTPStatusError as e:
                    logger.warning(f"Tokocrypto HTTP error for {url}: {e}")
                    last_error = e
                except ValueError as e:  # invalid JSON
                    logger.warning(f"Tokocrypto invalid JSON for {url}: {e}")
                    last_error = e
                except TokocryptoResponseError as e:
                    last_error = e

            await asyncio.sleep(2 ** attempt)  # exponential backoff between attempts

        raise TokocryptoResponseError(f"request failed after {self.max_retries} retries: {last_error}")

    @staticmethod
    def _extract_data(payload: Any, url: str = "") -> Any:
        """Unwrap the ``{code, msg, data}`` envelope when present.

        Tokocrypto sometimes returns the payload directly (bare list/object) and
        sometimes wrapped. We only trust the ``code`` field to detect failure.
        """
        if isinstance(payload, dict):
            if "code" in payload and payload.get("code") not in (0, "0", None):
                raise TokocryptoResponseError(f"Tokocrypto API error code={payload.get('code')} msg={payload.get('msg')} for {url}")
            if "data" in payload and isinstance(payload["data"], (dict, list)):
                return payload["data"]
            if "code" in payload:
                return payload
        return payload

    async def fetch_symbols(self, cache_ttl: int = 300, force: bool = False) -> list[TokocryptoSymbol]:
        """Fetch and cache the supported trading symbols list."""
        import time

        now = time.monotonic()
        cache_ts, cached = self._symbols_cache
        if not force and cached is not None and cache_ts is not None and (now - cache_ts) < cache_ttl:
            return cached

        payload = await self._request(f"{BASE_URL_MAIN}/open/v1/common/symbols")
        raw_list = payload if isinstance(payload, list) else payload.get("list", [])

        symbols: list[TokocryptoSymbol] = []
        for raw in raw_list:
            try:
                sym = self.parse_symbol(raw)
                if sym is not None:
                    symbols.append(sym)
            except Exception as e:  # never let a single bad entry kill the whole list
                logger.debug(f"Skipping unparseable symbol {raw.get('symbol', '?')}: {e}")

        self._symbols_cache = (now, symbols)
        logger.info(f"Fetched {len(symbols)} trading symbols from Tokocrypto")
        return symbols

    @staticmethod
    def parse_symbol(raw: dict) -> Optional[TokocryptoSymbol]:
        """Tolerant parser for a single symbol entry."""
        symbol = raw.get("symbol") or raw.get("s")
        if not symbol or not isinstance(symbol, str) or "_" not in symbol:
            return None

        base, quote = symbol.split("_", 1)
        if not base or not quote:
            return None

        # spotTradingEnable can be 1/0, True/False, or absent.
        spot = raw.get("spotTradingEnable", raw.get("isSpotTradingAllowed", raw.get("status")))
        spot_trading = spot in (1, "1", True, "true", "TRADING", "ENABLED")

        return TokocryptoSymbol(
            raw_symbol=symbol,
            base=base,
            quote=quote,
            symbol_type=raw.get("type", raw.get("symbolType", 1)),
            spot_trading=spot_trading,
        )

    async def fetch_tickers(self) -> dict[str, dict]:
        """Fetch 24h tickers for ALL symbols at once.

        Returns a dict keyed by normalized (no-underscore) symbol.
        """
        url = f"{BASE_URL_MARKET_V3}/api/v3/ticker/24hr"
        payload = await self._request(url)
        rows = payload if isinstance(payload, list) else payload.get("data", [])

        tickers: dict[str, dict] = {}
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            sym = row.get("symbol")
            if not sym:
                continue
            tickers[str(sym).replace("_", "")] = self._normalize_ticker(row)
        return tickers

    @staticmethod
    def _normalize_ticker(row: dict) -> dict:
        """Flatten a ticker row, coercing numeric strings to floats where safe."""
        def num(key: str) -> Optional[float]:
            val = row.get(key)
            if val in (None, ""):
                return None
            try:
                return float(val)
            except (TypeError, ValueError):
                return None

        out: dict = {
            "symbol": row.get("symbol", ""),
            "lastPrice": num("lastPrice"),
            "priceChangePercent": num("priceChangePercent"),
            "priceChange": num("priceChange"),
            "highPrice": num("highPrice"),
            "lowPrice": num("lowPrice"),
            "volume": num("volume"),
            "quoteVolume": num("quoteVolume"),
            "count": row.get("count") or row.get("tradeCount"),
            "openPrice": num("openPrice"),
            "prevClosePrice": num("prevClosePrice"),
        }
        return out

    async def fetch_klines(
        self,
        symbol: TokocryptoSymbol,
        interval: str,
        limit: int = 200,
    ) -> list[dict]:
        """Fetch OHLCV candles for a pair on a given interval.

        Handles the engine type differences (v3 vs v1 endpoint, symbol format).
        Returns a list of ``{openTime, open, high, low, close, volume, quoteVolume,
        numTrades}`` dicts, oldest first.
        """
        if interval not in KLINES_INTERVALS:
            raise ValueError(f"Unsupported kline interval: {interval}")

        url = symbol.market_url("klines")
        symbol_param = symbol.normalized_symbol if symbol.symbol_type == 1 else symbol.raw_symbol

        payload = await self._request(url, params={
            "symbol": symbol_param,
            "interval": interval,
            "limit": limit,
        })
        rows = payload if isinstance(payload, list) else payload.get("data", [])

        candles: list[dict] = []
        for row in rows if isinstance(rows, list) else []:
            # Expected Binance-style array: [openTime, open, high, low, close,
            # volume, closeTime, quoteVolume, trades, takerBuyBase, takerBuyQuote, ignore]
            if not isinstance(row, (list, tuple)) or len(row) < 6:
                continue
            try:
                candles.append({
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

        if not candles and (not isinstance(payload, list) or (isinstance(payload, list) and not payload)):
            logger.debug(f"No candles returned for {symbol.raw_symbol} {interval}")
        return candles


# Singleton
tokocrypto_client = TokocryptoClient()
