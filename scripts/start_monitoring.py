#!/usr/bin/env python3
"""Start monitoring mode - Scan stocks and log alerts without sending Telegram notifications.

This script:
1. Fetches current stock prices for all active stocks
2. Runs technical + fundamental + ML analysis
3. Calculates combined scores
4. Logs potential buy signals
5. Does NOT send Telegram alerts (monitoring only)

Usage:
    python scripts/start_monitoring.py
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import pandas as pd
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session
from app.models.stock import Stock, StockPrice
from app.services.enhanced_technicals import TechnicalAnalyzer
from app.services.fundamental_analyzer import FundamentalAnalyzer
from app.services.combined_analyzer import CombinedAnalyzer
from app.services.foreign_flow import ForeignFlowAnalyzer
from app.services.ml_ensemble import MLEnsemble
from app.config import get_settings

settings = get_settings()

logger = __import__('logging').getLogger(__name__)
logging = __import__('logging')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


async def fetch_stock_prices(session: AsyncSession, ticker: str, days: int = 60) -> pd.DataFrame:
    """Fetch historical prices for a stock."""
    from sqlalchemy import func
    
    stmt = select(StockPrice).where(
        StockPrice.ticker == ticker
    ).order_by(StockPrice.date.desc()).limit(days)
    
    result = await session.execute(stmt)
    prices = result.scalars().all()
    
    if not prices:
        return pd.DataFrame()
    
    df = pd.DataFrame([{
        'date': p.date,
        'open': p.open,
        'high': p.high,
        'low': p.low,
        'close': p.close,
        'volume': p.volume,
    } for p in prices])
    
    return df.sort_values('date')


async def get_active_stocks(session: AsyncSession) -> list[str]:
    """Get list of active stock tickers."""
    stmt = select(Stock.ticker).where(Stock.is_active == True)
    result = await session.execute(stmt)
    return [row[0] for row in result.all()]


async def analyze_stock(
    ticker: str,
    prices_df: pd.DataFrame,
    technical_analyzer: TechnicalAnalyzer,
    fundamental_analyzer: FundamentalAnalyzer,
    combined_analyzer: CombinedAnalyzer,
    flow_analyzer: ForeignFlowAnalyzer,
) -> dict:
    """Analyze a single stock."""
    try:
        # Technical analysis
        technical_data = technical_analyzer.analyze(prices_df)
        
        # Fundamental analysis (mock for now)
        fundamental_data = await fundamental_analyzer.analyze(ticker)
        
        # Combined score
        combined = combined_analyzer.calculate_combined_score(
            technical_data,
            fundamental_data,
        )
        
        # Foreign flow
        flow = flow_analyzer.analyze(ticker)
        
        return {
            'ticker': ticker,
            'technical_score': technical_data.get('score', 0),
            'fundamental_score': fundamental_data.get('score', 0) if fundamental_data else 0,
            'combined_score': combined.get('combined_score', 0),
            'bandar_score': flow.bandar_score if flow else 0,
            'signal': combined.get('signal', 'HOLD'),
            'conviction': combined.get('conviction', 0),
        }
    
    except Exception as e:
        logger.error(f"Error analyzing {ticker}: {e}")
        return None


async def monitoring_loop():
    """Main monitoring loop."""
    logger.info("=" * 80)
    logger.info("🔍 IDX AI STOCK ASSISTANT - MONITORING MODE")
    logger.info("=" * 80)
    logger.info("This script will scan stocks and log potential alerts")
    logger.info("Telegram alerts are DISABLED in monitoring mode")
    logger.info("=" * 80)
    
    # Initialize analyzers
    technical_analyzer = TechnicalAnalyzer()
    fundamental_analyzer = FundamentalAnalyzer()
    combined_analyzer = CombinedAnalyzer()
    flow_analyzer = ForeignFlowAnalyzer()
    
    # Try to load ML ensemble (optional)
    try:
        ml_ensemble = MLEnsemble()
        ml_ensemble.load()
        logger.info("✅ ML Ensemble loaded")
    except Exception as e:
        logger.warning(f"ML Ensemble not available: {e}")
        ml_ensemble = None
    
    scan_count = 0
    
    while True:
        scan_count += 1
        logger.info(f"\n{'='*80}")
        logger.info(f"📊 SCAN #{scan_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"{'='*80}")
        
        async with async_session() as session:
            try:
                # Get active stocks
                tickers = await get_active_stocks(session)
                logger.info(f"Found {len(tickers)} active stocks")
                
                # Analyze each stock
                results = []
                for i, ticker in enumerate(tickers[:50], 1):  # Limit to 50 for demo
                    if i % 10 == 0:
                        logger.info(f"  Analyzing {i}/{len(tickers)} stocks...")
                    
                    # Fetch prices
                    prices_df = await fetch_stock_prices(session, ticker)
                    
                    if prices_df.empty or len(prices_df) < 30:
                        continue
                    
                    # Analyze
                    result = await analyze_stock(
                        ticker,
                        prices_df,
                        technical_analyzer,
                        fundamental_analyzer,
                        combined_analyzer,
                        flow_analyzer,
                    )
                    
                    if result:
                        results.append(result)
                
                # Sort by combined score
                results.sort(key=lambda x: x['combined_score'], reverse=True)
                
                # Show top opportunities
                logger.info(f"\n🏆 TOP 10 OPPORTUNITIES:")
                logger.info(f"{'Rank':<5} {'Ticker':<8} {'Score':>8} {'Bandar':>8} {'Signal':<15} {'Conviction':>10}")
                logger.info("-" * 80)
                
                for i, r in enumerate(results[:10], 1):
                    if r['combined_score'] >= 65:  # Only show good opportunities
                        emoji = "🟢" if r['bandar_score'] >= 65 else "🟡" if r['bandar_score'] >= 45 else "🔴"
                        logger.info(
                            f"{emoji} {i:<4} {r['ticker']:<6} {r['combined_score']:>7.1f} "
                            f"{r['bandar_score']:>7.1f} {r['signal']:<15} {r['conviction']:>9.2f}"
                        )
                
                # Show summary
                high_score_count = sum(1 for r in results if r['combined_score'] >= 65)
                accumulation_count = sum(1 for r in results if r['bandar_score'] >= 65)
                
                logger.info(f"\n📈 SUMMARY:")
                logger.info(f"  Total analyzed: {len(results)}")
                logger.info(f"  High score (≥65): {high_score_count}")
                logger.info(f"  Bandar accumulation: {accumulation_count}")
                
                if high_score_count > 0:
                    logger.info(f"\n⚠️  Found {high_score_count} potential opportunities!")
                    logger.info("    Check detailed analysis in dashboard or run demo_scanner.py")
                
            except Exception as e:
                logger.error(f"Scan error: {e}", exc_info=True)
        
        # Wait for next scan (15 minutes in production, 5 minutes for demo)
        wait_minutes = 5
        logger.info(f"\n⏳ Next scan in {wait_minutes} minutes...")
        await asyncio.sleep(wait_minutes * 60)


if __name__ == "__main__":
    try:
        asyncio.run(monitoring_loop())
    except KeyboardInterrupt:
        logger.info("\n👋 Monitoring stopped by user")
