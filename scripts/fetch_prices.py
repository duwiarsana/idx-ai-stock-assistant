#!/usr/bin/env python3
"""Fetch historical prices for all active stocks."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import yfinance as yf
from sqlalchemy import select
from app.db.session import async_session_factory
from app.models.stock import Stock, StockPrice


async def fetch_all_prices():
    """Fetch prices for all active stocks."""
    async with async_session_factory() as session:
        # Get active stocks
        result = await session.execute(select(Stock).where(Stock.is_active == True))
        stocks = result.scalars().all()
        
        print(f"Found {len(stocks)} active stocks")
        
        fetched = 0
        errors = 0
        
        for i, stock in enumerate(stocks[:50], 1):  # First 50 for demo
            ticker = stock.ticker
            print(f"[{i}/{len(stocks)}] Fetching {ticker}...")
            
            try:
                jk_ticker = f"{ticker}.JK"
                data = yf.download(jk_ticker, period="60d", progress=False)
                
                if data.empty:
                    print(f"  Warning: No data for {ticker}")
                    errors += 1
                    continue
                
                # Save to database
                for date, row in data.iterrows():
                    price = StockPrice(
                        ticker=ticker,
                        date=date.date() if hasattr(date, 'date') else date,
                        open=float(row['Open']),
                        high=float(row['High']),
                        low=float(row['Low']),
                        close=float(row['Close']),
                        volume=int(row['Volume']) if 'Volume' in row else 0,
                    )
                    session.add(price)
                
                await session.commit()
                fetched += 1
                print(f"  OK: {ticker} - {len(data)} days")
                
            except Exception as e:
                print(f"  Error: {ticker} - {e}")
                errors += 1
                await session.rollback()
        
        print(f"\nComplete: {fetched} fetched, {errors} errors")


if __name__ == "__main__":
    asyncio.run(fetch_all_prices())
