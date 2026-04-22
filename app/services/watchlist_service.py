"""Watchlist service (Phase 4)."""

import logging

logger = logging.getLogger(__name__)


class WatchlistService:
    """User watchlist management. (Phase 4)

    Will support:
    - Add/remove stocks from watchlist
    - Price alerts
    - Daily watchlist summary
    """

    async def add_to_watchlist(self, user_id: str, ticker: str) -> dict:
        logger.info("Watchlist service not yet implemented")
        return {"status": "not_implemented"}

    async def remove_from_watchlist(self, user_id: str, ticker: str) -> dict:
        logger.info("Watchlist service not yet implemented")
        return {"status": "not_implemented"}

    async def get_watchlist(self, user_id: str) -> list:
        logger.info("Watchlist service not yet implemented")
        return []


watchlist_service = WatchlistService()
