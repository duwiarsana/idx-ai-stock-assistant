#!/usr/bin/env python3
"""Demo script to test Enhanced Technical Analysis.

This script demonstrates the new enhanced technical analysis capabilities:
- 130+ technical indicators
- Multi-timeframe analysis
- Divergence detection
- Candlestick patterns
- Professional support/resistance levels

Usage:
    python scripts/demo_enhanced_technicals.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import yfinance as yf

from app.services.enhanced_technicals import (
    EnhancedTechnicalEngine,
    format_technical_summary,
)

from app.services.multi_timeframe import (
    MultiTimeframeAnalyzer,
    TimeframeResampler,
    Timeframe,
    format_multi_timeframe_summary,
)

from app.services.analysis_engine import (
    analyze_enhanced,
    get_enhanced_signal_summary,
)


def fetch_stock_data(ticker: str, period: str = "1y") -> pd.DataFrame:
    """Fetch stock data from Yahoo Finance."""
    jk_ticker = f"{ticker}.JK"
    print(f"📥 Fetching data for {jk_ticker}...")
    
    stock = yf.Ticker(jk_ticker)
    df = stock.history(period=period)
    
    if df.empty:
        raise ValueError(f"No data found for {jk_ticker}")
    
    # Reset index to have 'date' column
    df = df.reset_index()
    
    # Normalize column names (yfinance may return different casing)
    df.columns = df.columns.str.lower()
    df = df.rename(columns={'date': 'date'})
    
    # Ensure required columns exist
    required_cols = ['open', 'high', 'low', 'close', 'volume']
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"Missing columns from yfinance: {missing}")
    
    print(f"✓ Fetched {len(df)} bars from {df['date'].min().date()} to {df['date'].max().date()}")
    
    return df


def test_enhanced_analysis(ticker: str):
    """Test enhanced technical analysis on a stock."""
    print("\n" + "=" * 60)
    print(f"🔍 ENHANCED TECHNICAL ANALYSIS: {ticker}")
    print("=" * 60)
    
    try:
        # Fetch data
        df = fetch_stock_data(ticker)
        
        # Run enhanced analysis
        print("\n⚙️  Running enhanced analysis (130+ indicators)...")
        engine = EnhancedTechnicalEngine()
        result = engine.analyze(df, ticker)
        
        # Print formatted summary
        print("\n" + format_technical_summary(result))
        
        # Print detailed indicator breakdown
        print("\n📊 DETAILED INDICATOR BREAKDOWN:")
        print("-" * 60)
        
        if 'trend' in result.indicators:
            trend = result.indicators['trend']
            print("\n📈 TREND INDICATORS:")
            for key, value in trend.items():
                if value is not None:
                    print(f"  {key:25s}: {value}")
        
        if 'momentum' in result.indicators:
            momentum = result.indicators['momentum']
            print("\n📊 MOMENTUM INDICATORS:")
            for key, value in momentum.items():
                if value is not None:
                    print(f"  {key:25s}: {value}")
        
        if 'volatility' in result.indicators:
            volatility = result.indicators['volatility']
            print("\n⚡ VOLATILITY INDICATORS:")
            for key, value in volatility.items():
                if value is not None:
                    print(f"  {key:25s}: {value}")
        
        if 'volume' in result.indicators:
            volume = result.indicators['volume']
            print("\n💰 VOLUME INDICATORS:")
            for key, value in volume.items():
                if value is not None:
                    print(f"  {key:25s}: {value}")
        
        # Print patterns
        if result.candlestick_patterns:
            print("\n🕯️  CANDLESTICK PATTERNS DETECTED:")
            for pattern in result.candlestick_patterns:
                emoji = "📈" if pattern['type'] == 'bullish' else "📉" if pattern['type'] == 'bearish' else "⏸"
                print(f"  {emoji} {pattern['name']} ({pattern['strength']} strength)")
        
        # Print divergences
        if result.divergences:
            print("\n🔄 DIVERGENCES DETECTED:")
            for div in result.divergences:
                emoji = "📈" if div['type'] == 'bullish' else "📉"
                print(f"  {emoji} {div['indicator']} {div['type'].upper()} divergence (confidence: {div['confidence']:.0%})")
        
        # Print key levels
        print("\n🎯 KEY LEVELS:")
        if result.support_levels:
            print("  Support:")
            for supp in result.support_levels[:3]:
                print(f"    🛑 Rp {supp['level']:>12,.0f} ({supp['type']:12s}) - {supp['strength']}")
        
        if result.resistance_levels:
            print("  Resistance:")
            for res in result.resistance_levels[:3]:
                print(f"    🎯 Rp {res['level']:>12,.0f} ({res['type']:12s}) - {res['strength']}")
        
        # Get signal summary for AI/LLM
        print("\n🤖 AI/LLM SIGNAL SUMMARY:")
        signal_summary = get_enhanced_signal_summary(result)
        print(f"  Signal: {signal_summary['signal']} ({signal_summary['signal_strength']})")
        print(f"  Composite Score: {signal_summary['composite_score']:.1f}/100")
        print(f"  Trend: {signal_summary['trend_direction']}")
        print(f"  Category Scores:")
        for category, score in signal_summary['category_scores'].items():
            bar = "█" * int(score / 10)
            print(f"    {category:12s}: {score:5.1f} {bar}")
        
        return result
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_multi_timeframe(ticker: str):
    """Test multi-timeframe analysis on a stock."""
    print("\n" + "=" * 60)
    print(f"📊 MULTI-TIMEFRAME ANALYSIS: {ticker}")
    print("=" * 60)
    
    try:
        # Fetch minute data (for demo, we'll use daily and simulate)
        df = fetch_stock_data(ticker, period="2y")
        df = df.set_index('date')
        
        # For demo purposes, we'll use daily data for all timeframes
        # In production, you'd fetch actual intraday data
        print("\n⚠️  Note: Using daily data for all timeframes (demo mode)")
        print("   In production, use actual 15m and 1h data")
        
        data = {
            Timeframe.LONG: df,  # Daily
            Timeframe.MEDIUM: df.iloc[-150:],  # Last 150 days as "hourly"
            Timeframe.SHORT: df.iloc[-100:],  # Last 100 days as "15min"
        }
        
        # Run multi-timeframe analysis
        print("\n⚙️  Analyzing multiple timeframes...")
        analyzer = MultiTimeframeAnalyzer()
        result = analyzer.analyze(ticker, data)
        
        # Print formatted summary
        print("\n" + format_multi_timeframe_summary(result))
        
        # Detailed breakdown
        print("\n📋 DETAILED BREAKDOWN:")
        print("-" * 60)
        
        for tf_name, tf_result in [
            ('Long-term (Daily)', result.long_term),
            ('Medium-term (Hourly)', result.medium_term),
            ('Short-term (15min)', result.short_term),
        ]:
            if tf_result:
                r = tf_result.result
                print(f"\n{tf_name}:")
                print(f"  Signal: {r.signal} (score: {r.composite_score:.1f})")
                print(f"  Trend: {r.trend_direction}")
                print(f"  Category Scores:")
                print(f"    Trend: {r.trend_score:.1f}, Momentum: {r.momentum_score:.1f}")
                print(f"    Volatility: {r.volatility_score:.1f}, Volume: {r.volume_score:.1f}")
        
        print(f"\n🎯 Confluence Score: {result.confluence_score:.1f}/100")
        print(f"   Alignment: {result.alignment_type}")
        print(f"   Final Signal: {result.final_signal} ({result.final_strength})")
        print(f"   Confidence: {result.confidence}")
        
        return result
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Main demo function."""
    print("\n" + "╔" + "=" * 58 + "╗")
    print("║" + " " * 10 + "IDX AI Stock Assistant - Enhanced Technicals Demo" + " " * 6 + "║")
    print("╚" + "=" * 58 + "╝")
    
    # Test stocks
    test_tickers = ["BBCA", "BBRI", "TLKM"]
    
    for ticker in test_tickers:
        try:
            # Test enhanced analysis
            test_enhanced_analysis(ticker)
            
            # Test multi-timeframe (optional, takes longer)
            # test_multi_timeframe(ticker)
            
            print("\n" + "─" * 60 + "\n")
        
        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted by user")
            break
        except Exception as e:
            print(f"\n❌ Error testing {ticker}: {e}")
            continue
    
    print("\n✅ Demo completed!")
    print("\n📝 Next Steps:")
    print("   1. Review the analysis results above")
    print("   2. Check tests/test_enhanced_technicals.py for unit tests")
    print("   3. Integrate with existing analysis pipeline")
    print("   4. Run backtests to validate new indicators")
    print()


if __name__ == "__main__":
    main()
