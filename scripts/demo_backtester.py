#!/usr/bin/env python3
"""Demo script to test the Backtesting Engine.

This script demonstrates how to backtest trading strategies on historical data.

Usage:
    python scripts/demo_backtester.py
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import yfinance as yf

from app.services.backtester import (
    Backtester,
    TechnicalSignalStrategy,
    Portfolio,
    Signal,
    format_backtest_results,
)
from app.services.enhanced_technicals import EnhancedTechnicalEngine


def fetch_stock_data(ticker: str, period: str = "2y") -> pd.DataFrame:
    """Fetch stock data from Yahoo Finance."""
    jk_ticker = f"{ticker}.JK"
    print(f"📥 Fetching data for {jk_ticker}...")
    
    stock = yf.Ticker(jk_ticker)
    df = stock.history(period=period)
    
    if df.empty:
        raise ValueError(f"No data found for {jk_ticker}")
    
    # Reset index and normalize columns
    df = df.reset_index()
    df.columns = df.columns.str.lower()
    
    print(f"✓ Fetched {len(df)} bars from {df['date'].min().date()} to {df['date'].max().date()}")
    
    return df


class EnhancedTechnicalStrategy(TechnicalSignalStrategy):
    """Strategy based on enhanced technical analysis signals."""
    
    def __init__(self, min_score: float = 60.0):
        super().__init__()
        self.min_score = min_score
        self.engine = EnhancedTechnicalEngine()
    
    @property
    def name(self) -> str:
        return "Enhanced Technical Strategy"
    
    def generate_signal(
        self,
        row: pd.Series,
        portfolio: Portfolio,
        history: pd.DataFrame
    ) -> Signal:
        ticker = row.get('ticker', 'UNKNOWN')
        
        # Check if we already have a position
        if ticker in portfolio.positions:
            # Exit if signal turns to SELL or score drops below threshold
            signal_value = row.get('signal', 'HOLD')
            score = row.get('composite_score', 50)
            
            if signal_value == 'SELL' or score < 40:
                return Signal.SELL
            return Signal.HOLD
        else:
            # Enter if signal is BUY and score is high enough
            signal_value = row.get('signal', 'HOLD')
            score = row.get('composite_score', 50)
            
            if signal_value == 'BUY' and score >= self.min_score:
                return Signal.BUY
            return Signal.HOLD


def run_simple_backtest(ticker: str, data: pd.DataFrame):
    """Run simple backtest using signal column directly."""
    print("\n" + "=" * 60)
    print(f"📊 SIMPLE BACKTEST: {ticker}")
    print("=" * 60)
    
    # Check if signal column exists
    if 'signal' not in data.columns:
        print("❌ No 'signal' column in data. Run enhanced analysis first.")
        return None
    
    # Initialize backtester
    backtester = Backtester(
        initial_capital=100_000_000,  # 100 million IDR
        commission=0.0003,  # 0.03%
        slippage=0.001,  # 0.1%
        position_sizing="fixed_fractional",
        risk_per_trade=0.02,
    )
    
    # Run backtest
    strategy = TechnicalSignalStrategy(signal_column='signal')
    result = backtester.run(strategy, data)
    
    # Print results
    print("\n" + format_backtest_results(result))
    
    return result


def run_enhanced_backtest(ticker: str):
    """Run backtest with on-the-fly technical analysis."""
    print("\n" + "=" * 60)
    print(f"🚀 ENHANCED BACKTEST: {ticker}")
    print("=" * 60)
    
    # Fetch data
    data = fetch_stock_data(ticker, period="2y")
    
    # Run enhanced technical analysis on each bar
    print("\n⚙️  Running technical analysis on historical data...")
    engine = EnhancedTechnicalEngine()
    
    # Store signals and scores
    signals = []
    scores = []
    
    # Rolling window analysis
    window_size = 50
    for i in range(window_size, len(data)):
        history = data.iloc[:i+1].to_dict('records')
        result = engine.analyze(pd.DataFrame(history), ticker)
        
        signals.append(result.signal)
        scores.append(result.composite_score)
    
    # Add to dataframe
    data = data.iloc[window_size:].copy()
    data['signal'] = signals
    data['composite_score'] = scores
    
    print(f"✓ Generated {len(signals)} signals")
    print(f"  BUY signals: {signals.count('BUY')}")
    print(f"  SELL signals: {signals.count('SELL')}")
    print(f"  HOLD signals: {signals.count('HOLD')}")
    
    # Initialize backtester
    backtester = Backtester(
        initial_capital=100_000_000,
        commission=0.0003,
        slippage=0.001,
        position_sizing="fixed_fractional",
    )
    
    # Run backtest
    strategy = EnhancedTechnicalStrategy(min_score=60.0)
    result = backtester.run(strategy, data)
    
    # Print results
    print("\n" + format_backtest_results(result))
    
    # Additional analysis
    print("\n📈 EQUITY CURVE ANALYSIS:")
    if result.equity_curve:
        # Find best and worst periods
        equity_values = [e['equity'] for e in result.equity_curve]
        max_equity = max(equity_values)
        min_equity = min(equity_values)
        
        print(f"  Peak Equity: Rp {max_equity:,.0f}")
        print(f"  Lowest Equity: Rp {min_equity:,.0f}")
        print(f"  Current Equity: Rp {equity_values[-1]:,.0f}")
    
    print("\n📊 MONTHLY RETURNS:")
    if result.monthly_returns:
        for month, ret in list(result.monthly_returns.items())[:12]:  # Show first 12 months
            emoji = "🟢" if ret > 0 else "🔴" if ret < 0 else "⚪"
            print(f"  {emoji} {month}: {ret:>7.2%}")
    
    return result


def compare_strategies(ticker: str):
    """Compare different parameter settings."""
    print("\n" + "=" * 60)
    print(f"📋 STRATEGY COMPARISON: {ticker}")
    print("=" * 60)
    
    # Fetch data
    data = fetch_stock_data(ticker, period="2y")
    
    # Run enhanced analysis
    print("\n⚙️  Running technical analysis...")
    engine = EnhancedTechnicalEngine()
    
    signals_list = []
    scores_list = []
    
    window_size = 50
    for i in range(window_size, len(data)):
        history = data.iloc[:i+1].to_dict('records')
        result = engine.analyze(pd.DataFrame(history), ticker)
        
        signals_list.append(result.signal)
        scores_list.append(result.composite_score)
    
    data = data.iloc[window_size:].copy()
    data['signal'] = signals_list
    data['composite_score'] = scores_list
    
    # Test different minimum score thresholds
    thresholds = [50, 60, 70]
    results = []
    
    for threshold in thresholds:
        print(f"\nTesting threshold: {threshold}...")
        
        backtester = Backtester(
            initial_capital=100_000_000,
            commission=0.0003,
            slippage=0.001,
        )
        
        strategy = EnhancedTechnicalStrategy(min_score=threshold)
        result = backtester.run(strategy, data)
        
        results.append({
            'threshold': threshold,
            'total_return': result.total_return_pct,
            'sharpe': result.sharpe_ratio,
            'max_dd': result.max_drawdown_pct,
            'win_rate': result.win_rate,
            'trades': result.total_trades,
        })
        
        print(f"  Return: {result.total_return_pct:7.2%} | Sharpe: {result.sharpe_ratio:5.2f} | MaxDD: {result.max_drawdown_pct:7.2%} | Trades: {result.total_trades:3d}")
    
    # Summary table
    print("\n" + "=" * 80)
    print(f"{'Threshold':<12} {'Return':<12} {'Sharpe':<10} {'MaxDD':<12} {'Win Rate':<12} {'Trades':<8}")
    print("-" * 80)
    for r in results:
        print(f"{r['threshold']:<12} {r['total_return']:<12.2%} {r['sharpe']:<10.2f} {r['max_dd']:<12.2%} {r['win_rate']:<12.2%} {r['trades']:<8d}")
    print("=" * 80)
    
    return results


def main():
    """Main demo function."""
    print("\n" + "╔" + "=" * 58 + "╗")
    print("║" + " " * 15 + "IDX AI Stock Assistant - Backtester Demo" + " " * 10 + "║")
    print("╚" + "=" * 58 + "╝")
    
    # Test stocks
    test_tickers = ["BBCA", "BBRI", "TLKM"]
    
    all_results = []
    
    for ticker in test_tickers:
        try:
            # Run enhanced backtest
            result = run_enhanced_backtest(ticker)
            if result:
                all_results.append({
                    'ticker': ticker,
                    'return': result.total_return_pct,
                    'sharpe': result.sharpe_ratio,
                    'max_dd': result.max_drawdown_pct,
                })
            
            # Compare strategies (optional, takes longer)
            # compare_strategies(ticker)
            
            print("\n" + "─" * 60 + "\n")
        
        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted by user")
            break
        except Exception as e:
            print(f"\n❌ Error testing {ticker}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Summary
    if all_results:
        print("\n" + "=" * 60)
        print("📊 BACKTEST SUMMARY")
        print("=" * 60)
        print(f"{'Ticker':<10} {'Return':<12} {'Sharpe':<10} {'MaxDD':<12}")
        print("-" * 60)
        for r in all_results:
            print(f"{r['ticker']:<10} {r['return']:<12.2%} {r['sharpe']:<10.2f} {r['max_dd']:<12.2%}")
        print("=" * 60)
    
    print("\n✅ Demo completed!")
    print("\n📝 Next Steps:")
    print("   1. Review backtest results above")
    print("   2. Adjust strategy parameters in EnhancedTechnicalStrategy")
    print("   3. Test on more stocks and time periods")
    print("   4. Add walk-forward validation for robust testing")
    print()


if __name__ == "__main__":
    main()
