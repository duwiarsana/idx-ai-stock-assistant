"""IDX scraper for official IDX data (Phase 2).

This module will scrape additional company data from the official
IDX website (idx.co.id) in future phases.
"""

import logging

from typing import Optional

logger = logging.getLogger(__name__)


class IDXScraper:
    """Scraper for official IDX website data.

    Phase 2 implementation will add:
    - Company financials (balance sheet, income statement)
    - Dividend history
    - Shareholder composition
    - Corporate actions
    """

    BASE_URL = "https://www.idx.co.id"

    async def fetch_company_profile(self, ticker: str) -> Optional[dict]:
        """Fetch company profile from IDX. (Phase 2)"""
        logger.info(f"IDX scraper not yet implemented for {ticker}")
        return None

    async def fetch_financial_report(self, ticker: str) -> Optional[dict]:
        """Fetch financial report from IDX. (Phase 2)"""
        logger.info(f"IDX financial report scraper not yet implemented for {ticker}")
        return None


idx_scraper = IDXScraper()
