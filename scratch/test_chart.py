
import asyncio
import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.stock_service import stock_service
from app.services.chart_service import chart_service

async def test_chart_generation():
    load_dotenv()
    ticker = "BBCA"
    print(f"🚀 Testing Chart Generation for {ticker}...")
    
    # 1. Fetch data
    data = await stock_service.get_stock_data(ticker)
    history = data.get("history", [])
    
    if not history:
        print("❌ Failed to fetch history data.")
        return

    # 2. Generate chart
    print("Generating chart...")
    chart_path = await chart_service.generate_candlestick_chart(ticker, history)
    
    if chart_path and os.path.exists(chart_path):
        print(f"✅ Chart generated successfully at: {chart_path}")
        print(f"File size: {os.path.getsize(chart_path)} bytes")
    else:
        print("❌ Failed to generate chart.")

if __name__ == "__main__":
    asyncio.run(test_chart_generation())
