import asyncio
import logging
import sys

sys.path.append(".")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
logger = logging.getLogger("test_intraday_scanner")

from app.scheduler.jobs import intraday_scanner_job

async def main():
    logger.info("Starting manual intraday scanner test...")
    # Clear any cooldowns for testing
    from app.services.cache_service import cache_service
    # Flush alert keys if needed, but we don't need to do that unless testing twice
    await intraday_scanner_job()
    logger.info("Intraday scanner test complete.")

if __name__ == "__main__":
    asyncio.run(main())
