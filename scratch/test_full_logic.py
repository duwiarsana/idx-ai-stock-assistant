
import asyncio
import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.ai_service import ai_service

async def test_logic():
    load_dotenv()
    ticker = "BBCA"
    print(f"Testing full logic for {ticker}...")
    
    try:
        print("Fetching quick lookup...")
        quick = await ai_service.quick_lookup(ticker)
        print(f"Quick Lookup Result:\n{quick}\n")
        
        print("Fetching full analysis (this may take a while)...")
        analysis = await ai_service.analyze_stock(ticker)
        print(f"Analysis Ticker: {analysis.get('ticker')}")
        print(f"Analysis length: {len(analysis.get('analysis', ''))}")
        print(f"Analysis Preview: {analysis.get('analysis')[:200]}...")
        
        print("\n✅ Full logic test SUCCESSFUL!")
    except Exception as e:
        print(f"\n❌ Logic test FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_logic())
