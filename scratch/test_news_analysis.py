
import asyncio
import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.ai_service import ai_service
from app.data.news_fetcher import news_fetcher

async def test_news_integration():
    load_dotenv()
    ticker = "TLKM" # Using TLKM as it usually has lots of news
    print(f"🚀 Testing News Integration for {ticker}...")
    
    try:
        # 1. Test Fetching
        print("Fetching news directly...")
        news = await news_fetcher.fetch_news(ticker)
        for i, item in enumerate(news, 1):
            print(f"  {i}. {item['title']} ({item['source']})")
        
        if not news:
            print("⚠️ No news found, check connection or ticker.")
            
        # 2. Test Full Analysis
        print("\nRunning full analysis with sentiment...")
        # Flush cache to force new analysis
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.flushall()
        
        result = await ai_service.analyze_stock(ticker)
        print(f"\nAnalysis Result Preview:\n{result.get('analysis')[:500]}...")
        
        if "Analisis Sentimen Berita" in result.get('analysis'):
            print("\n✅ News Sentiment Analysis found in response!")
        else:
            print("\n❌ News Sentiment Analysis NOT found in response.")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_news_integration())
