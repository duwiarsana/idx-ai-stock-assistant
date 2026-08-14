#!/usr/bin/env python3
"""Comprehensive Test Script - Full System Demo.

Tests all components:
1. Enhanced Technical Analysis (130+ indicators)
2. Fundamental Analysis (Financial ratios, scoring)
3. Combined Analysis (Technical + Fundamental)
4. Backtesting Engine (Performance metrics)

Usage:
    python scripts/test_full_system.py
"""

import sys
import time
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import yfinance as yf

from app.services.enhanced_technicals import (
    EnhancedTechnicalEngine,
    format_technical_summary,
)
from app.services.fundamental_analyzer import (
    FundamentalAnalyzer,
    format_fundamental_summary,
)
from app.services.combined_analyzer import (
    CombinedAnalyzer,
    format_combined_summary,
)
from app.services.backtester import (
    Backtester,
    TechnicalSignalStrategy,
    format_backtest_results,
)


def fetch_price_data(ticker: str, period: str = "2y") -> pd.DataFrame:
    """Fetch historical price data."""
    jk_ticker = f"{ticker}.JK"
    stock = yf.Ticker(jk_ticker)
    df = stock.history(period=period)
    
    if df.empty:
        return None
    
    df = df.reset_index()
    df.columns = df.columns.str.lower()
    
    return df


def test_technical_analysis(ticker: str, price_data: pd.DataFrame) -> dict:
    """Test technical analysis."""
    print(f"\n{'=' * 70}")
    print(f"📊 TECHNICAL ANALYSIS: {ticker}")
    print("=" * 70)
    
    start_time = time.time()
    
    engine = EnhancedTechnicalEngine()
    result = engine.analyze(price_data, ticker)
    
    elapsed = time.time() - start_time
    
    if result:
        print(format_technical_summary(result))
        print(f"\n⏱️  Analysis time: {elapsed:.2f}s")
        
        return {
            'ticker': ticker,
            'signal': result.signal,
            'score': result.composite_score,
            'trend': result.trend_direction,
            'success': True,
        }
    else:
        print("❌ Technical analysis failed")
        return {'ticker': ticker, 'success': False}


def test_fundamental_analysis(ticker: str) -> dict:
    """Test fundamental analysis."""
    print(f"\n{'=' * 70}")
    print(f"📈 FUNDAMENTAL ANALYSIS: {ticker}")
    print("=" * 70)
    
    start_time = time.time()
    
    analyzer = FundamentalAnalyzer()
    result = analyzer.analyze(ticker)
    
    elapsed = time.time() - start_time
    
    if result:
        print(format_fundamental_summary(result))
        
        # Key ratios
        print("\n📊 KEY RATIOS:")
        ratios = result.ratios
        print(f"  P/E: {ratios.pe_ratio:.1f}" if ratios.pe_ratio else "  P/E: N/A")
        print(f"  P/B: {ratios.pb_ratio:.1f}" if ratios.pb_ratio else "  P/B: N/A")
        print(f"  ROE: {ratios.roe * 100:.1f}%" if ratios.roe else "  ROE: N/A")
        print(f"  DER: {ratios.debt_to_equity:.2f}" if ratios.debt_to_equity else "  DER: N/A")
        
        print(f"\n⏱️  Analysis time: {elapsed:.2f}s")
        
        return {
            'ticker': ticker,
            'grade': result.investment_grade,
            'score': result.overall_score,
            'health': result.financial_health,
            'success': True,
        }
    else:
        print("❌ Fundamental analysis failed")
        return {'ticker': ticker, 'success': False}


def test_combined_analysis(ticker: str, price_data: pd.DataFrame) -> dict:
    """Test combined technical + fundamental analysis."""
    print(f"\n{'=' * 70}")
    print(f"🎯 COMBINED ANALYSIS: {ticker}")
    print("=" * 70)
    
    start_time = time.time()
    
    analyzer = CombinedAnalyzer(investment_horizon="medium")
    result = analyzer.analyze(ticker, price_data)
    
    elapsed = time.time() - start_time
    
    if result:
        print(format_combined_summary(result))
        print(f"\n⏱️  Analysis time: {elapsed:.2f}s")
        
        return {
            'ticker': ticker,
            'combined_signal': result.combined_signal,
            'combined_score': result.combined_score,
            'confidence': result.confidence,
            'conviction': result.conviction,
            'success': True,
        }
    else:
        print("❌ Combined analysis failed")
        return {'ticker': ticker, 'success': False}


def test_backtest(ticker: str, price_data: pd.DataFrame) -> dict:
    """Test backtesting engine."""
    print(f"\n{'=' * 70}")
    print(f"🧪 BACKTEST: {ticker}")
    print("=" * 70)
    
    start_time = time.time()
    
    # Add signals to price data using enhanced technicals
    engine = EnhancedTechnicalEngine()
    
    signals = []
    scores = []
    window = 50
    
    for i in range(window, len(price_data)):
        history = price_data.iloc[:i+1].to_dict('records')
        result = engine.analyze(pd.DataFrame(history), ticker)
        signals.append(result.signal)
        scores.append(result.composite_score)
    
    test_data = price_data.iloc[window:].copy()
    test_data['signal'] = signals
    test_data['composite_score'] = scores
    
    # Run backtest
    backtester = Backtester(
        initial_capital=100_000_000,
        commission=0.0003,
        slippage=0.001,
        position_sizing="fixed_fractional",
    )
    
    strategy = TechnicalSignalStrategy(signal_column='signal')
    result = backtester.run(strategy, test_data)
    
    elapsed = time.time() - start_time
    
    print(format_backtest_results(result))
    print(f"\n⏱️  Backtest time: {elapsed:.2f}s")
    
    return {
        'ticker': ticker,
        'return': result.total_return_pct,
        'sharpe': result.sharpe_ratio,
        'max_dd': result.max_drawdown_pct,
        'trades': result.total_trades,
        'win_rate': result.win_rate,
        'success': True,
    }


def generate_summary_report(results: dict):
    """Generate comprehensive summary report."""
    print("\n" + "=" * 90)
    print("📊 COMPREHENSIVE TEST SUMMARY")
    print("=" * 90)
    
    # Technical Summary
    print("\n🔹 TECHNICAL ANALYSIS:")
    print("-" * 90)
    print(f"{'Ticker':<8} {'Signal':<10} {'Score':>8} {'Trend':<20} {'Status':<10}")
    print("-" * 90)
    
    for ticker, tech in results['technical'].items():
        if tech['success']:
            status = "✅"
            print(f"{ticker:<8} {tech['signal']:<10} {tech['score']:>8.1f} {tech['trend']:<20} {status:<10}")
        else:
            print(f"{ticker:<8} {'FAILED':<10} {'-':>8} {'-':<20} ❌")
    
    # Fundamental Summary
    print("\n🔹 FUNDAMENTAL ANALYSIS:")
    print("-" * 90)
    print(f"{'Ticker':<8} {'Grade':<12} {'Score':>8} {'Health':<15} {'Status':<10}")
    print("-" * 90)
    
    for ticker, fund in results['fundamental'].items():
        if fund['success']:
            status = "✅"
            grade_emoji = "🟢" if fund['grade'] in ['STRONG_BUY', 'BUY'] else "🟡" if fund['grade'] == 'HOLD' else "🔴"
            print(f"{ticker:<8} {grade_emoji} {fund['grade']:<10} {fund['score']:>8.1f} {fund['health']:<15} {status:<10}")
        else:
            print(f"{ticker:<8} {'FAILED':<12} {'-':>8} {'-':<15} ❌")
    
    # Combined Summary
    print("\n🔹 COMBINED ANALYSIS:")
    print("-" * 90)
    print(f"{'Ticker':<8} {'Signal':<12} {'Score':>8} {'Confidence':<12} {'Conviction':>10} {'Status':<10}")
    print("-" * 90)
    
    for ticker, combined in results['combined'].items():
        if combined['success']:
            status = "✅"
            conf_emoji = "🟢" if combined['confidence'] == 'HIGH' else "🟡" if combined['confidence'] == 'MEDIUM' else "🔴"
            print(f"{ticker:<8} {combined['combined_signal']:<12} {combined['combined_score']:>8.1f} {conf_emoji} {combined['confidence']:<10} {combined['conviction']*100:>9.0f}% {status:<10}")
        else:
            print(f"{ticker:<8} {'FAILED':<12} {'-':>8} {'-':<12} {'-':>10} ❌")
    
    # Backtest Summary
    print("\n🔹 BACKTEST RESULTS:")
    print("-" * 90)
    print(f"{'Ticker':<8} {'Return':>10} {'Sharpe':>10} {'MaxDD':>10} {'Win Rate':>10} {'Trades':>8} {'Status':<10}")
    print("-" * 90)
    
    for ticker, bt in results['backtest'].items():
        if bt['success']:
            return_emoji = "🟢" if bt['return'] > 0 else "🔴"
            print(f"{ticker:<8} {return_emoji} {bt['return']*100:>9.1f}% {bt['sharpe']:>10.2f} {bt['max_dd']*100:>9.1f}% {bt['win_rate']*100:>9.1f}% {bt['trades']:>8d} ✅")
        else:
            print(f"{ticker:<8} {'FAILED':>10} {'-':>10} {'-':>10} {'-':>10} {'-':>8} ❌")
    
    # Top Picks
    print("\n" + "=" * 90)
    print("🏆 TOP PICKS BY CATEGORY")
    print("=" * 90)
    
    # Best Fundamental
    print("\n📈 BEST FUNDAMENTAL:")
    fundamental_sorted = sorted(
        [(t, r) for t, r in results['fundamental'].items() if r['success']],
        key=lambda x: -x[1]['score']
    )[:3]
    for i, (ticker, fund) in enumerate(fundamental_sorted, 1):
        print(f"  {i}. {ticker} - Score: {fund['score']:.1f}, Grade: {fund['grade']}")
    
    # Best Technical
    print("\n📊 BEST TECHNICAL:")
    technical_sorted = sorted(
        [(t, r) for t, r in results['technical'].items() if r['success']],
        key=lambda x: -x[1]['score']
    )[:3]
    for i, (ticker, tech) in enumerate(technical_sorted, 1):
        print(f"  {i}. {ticker} - Score: {tech['score']:.1f}, Signal: {tech['signal']}")
    
    # Best Combined
    print("\n🎯 BEST COMBINED:")
    combined_sorted = sorted(
        [(t, r) for t, r in results['combined'].items() if r['success']],
        key=lambda x: -x[1]['combined_score']
    )[:3]
    for i, (ticker, comb) in enumerate(combined_sorted, 1):
        print(f"  {i}. {ticker} - Score: {comb['combined_score']:.1f}, Signal: {comb['combined_signal']}")
    
    # Best Backtest
    print("\n🧪 BEST BACKTEST PERFORMANCE:")
    backtest_sorted = sorted(
        [(t, r) for t, r in results['backtest'].items() if r['success']],
        key=lambda x: -x[1]['return']
    )[:3]
    for i, (ticker, bt) in enumerate(backtest_sorted, 1):
        print(f"  {i}. {ticker} - Return: {bt['return']*100:.1f}%, Sharpe: {bt['sharpe']:.2f}")
    
    print("\n" + "=" * 90)


def main():
    """Main test function."""
    print("\n" + "╔" + "=" * 88 + "╗")
    print("║" + " " * 20 + "IDX AI STOCK ASSISTANT - FULL SYSTEM TEST" + " " * 26 + "║")
    print("╚" + "=" * 88 + "╝")
    print(f"\n📅 Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test stocks - major IDX stocks with good liquidity
    test_tickers = ["BBCA", "BBRI", "TLKM", "UNVR", "GOTO"]
    
    results = {
        'technical': {},
        'fundamental': {},
        'combined': {},
        'backtest': {},
    }
    
    total_start = time.time()
    
    for ticker in test_tickers:
        print(f"\n\n{'#' * 90}")
        print(f"# TESTING: {ticker}")
        print(f"{'#' * 90}")
        
        # Fetch price data
        print(f"\n📥 Fetching price data for {ticker}...")
        price_data = fetch_price_data(ticker, period="2y")
        
        if price_data is None or price_data.empty:
            print(f"❌ Failed to fetch price data for {ticker}")
            results['technical'][ticker] = {'success': False}
            results['combined'][ticker] = {'success': False}
            results['backtest'][ticker] = {'success': False}
        else:
            print(f"✓ Fetched {len(price_data)} bars")
            
            # Test Technical Analysis
            results['technical'][ticker] = test_technical_analysis(ticker, price_data)
            
            # Test Combined Analysis (needs both price and fundamental)
            results['combined'][ticker] = test_combined_analysis(ticker, price_data)
            
            # Test Backtest
            results['backtest'][ticker] = test_backtest(ticker, price_data)
        
        # Test Fundamental Analysis (independent)
        results['fundamental'][ticker] = test_fundamental_analysis(ticker)
        
        # Small delay to avoid rate limiting
        time.sleep(1)
    
    # Generate summary report
    generate_summary_report(results)
    
    total_elapsed = time.time() - total_start
    
    print(f"\n⏱️  Total test time: {total_elapsed:.1f}s")
    print(f"\n✅ Full system test completed!")
    
    # Save results to file
    output_file = Path(__file__).parent / "test_results.txt"
    with open(output_file, 'w') as f:
        f.write(f"IDX AI Stock Assistant - Test Results\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(str(results))
    
    print(f"\n📄 Results saved to: {output_file}")
    print()


if __name__ == "__main__":
    main()
