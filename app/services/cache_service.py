"""Redis caching service for stock data."""

import json
import logging
from typing import Any, Optional

from app.db.redis import redis_client
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class CacheService:
    """Redis-based caching for stock data and analysis results."""

    STOCK_PREFIX = "stock:"
    QUOTE_PREFIX = "quote:"
    ANALYSIS_PREFIX = "analysis:"

    def __init__(self):
        self.redis = redis_client
        self.default_ttl = settings.stock_cache_ttl

    async def get_stock_data(self, ticker: str) -> Optional[dict]:
        """Get cached stock data."""
        return await self._get(f"{self.STOCK_PREFIX}{ticker.upper()}")

    async def set_stock_data(self, ticker: str, data: dict, ttl: Optional[int] = None):
        """Cache stock data."""
        await self._set(
            f"{self.STOCK_PREFIX}{ticker.upper()}",
            data,
            ttl or self.default_ttl,
        )

    async def get_quick_quote(self, ticker: str) -> Optional[dict]:
        """Get cached quick quote."""
        return await self._get(f"{self.QUOTE_PREFIX}{ticker.upper()}")

    async def set_quick_quote(self, ticker: str, data: dict, ttl: int = 120):
        """Cache quick quote (shorter TTL)."""
        await self._set(f"{self.QUOTE_PREFIX}{ticker.upper()}", data, ttl)

    async def get_analysis(self, ticker: str) -> Optional[dict]:
        """Get cached analysis."""
        return await self._get(f"{self.ANALYSIS_PREFIX}{ticker.upper()}")

    async def set_analysis(self, ticker: str, data: dict, ttl: int = 900):
        """Cache analysis result (15 min TTL)."""
        await self._set(f"{self.ANALYSIS_PREFIX}{ticker.upper()}", data, ttl)

    async def invalidate_stock(self, ticker: str):
        """Remove all cached data for a ticker."""
        ticker = ticker.upper()
        keys = [
            f"{self.STOCK_PREFIX}{ticker}",
            f"{self.QUOTE_PREFIX}{ticker}",
            f"{self.ANALYSIS_PREFIX}{ticker}",
        ]
        try:
            await self.redis.delete(*keys)
            logger.debug(f"Invalidated cache for {ticker}")
        except Exception as e:
            logger.warning(f"Cache invalidation error for {ticker}: {e}")

    async def _get(self, key: str) -> Optional[dict]:
        """Get and deserialize a cached value."""
        try:
            raw = await self.redis.get(key)
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.warning(f"Cache get error for {key}: {e}")
        return None

    async def _set(self, key: str, data: Any, ttl: int):
        """Serialize and cache a value."""
        try:
            serialized = json.dumps(data, default=str)
            await self.redis.setex(key, ttl, serialized)
            logger.debug(f"Cached {key} (TTL={ttl}s)")
        except Exception as e:
            logger.warning(f"Cache set error for {key}: {e}")

    async def check_health(self) -> bool:
        """Check Redis connectivity."""
        try:
            return await self.redis.ping()
        except Exception:
            return False


# Singleton
cache_service = CacheService()
