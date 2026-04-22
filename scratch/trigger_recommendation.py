
import asyncio
import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.scheduler.jobs import daily_market_recommendations

async def main():
    load_dotenv()
    print("🚀 Triggering manual recommendation...")
    await daily_market_recommendations()
    print("✅ Done!")

if __name__ == "__main__":
    asyncio.run(main())
