#!/usr/bin/env python3
"""Demo script to test Fundamental Analysis Engine.

Usage:
    python scripts/demo_fundamental.py
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.fundamental_analyzer import (
    FundamentalAnalyzer,
    format_fundamental_summary,
)


def main():
    """Main demo function."""
    print("\n" + "╔" + "=" * 58 + "╗")
    print("║" + " " * 12 + "IDX AI Stock Assistant - Fundamental Analysis Demo" + " " * 5 + "║")
    print("╚" + "=" * 58 + "╝")
    
    # Test stocks - major IDX stocks
    test_tickers = ["BBCA", "BBRI", "TLKM", "UNVR", "ADRO"]
    
    analyzer = FundamentalAnalyzer()
    all_results = []
    
    for ticker in test_tickers:
        try:
            print(f"\n{'=' * 60}")
            print(f"🔍 ANALYZING: {ticker}")
            print("=" * 60)
            
            # Run fundamental analysis
            result = analyzer.analyze(ticker)
            
            if result:
                # Print formatted summary
                print("\n" + format_fundamental_summary(result))
                
                # Print detailed ratios
                print("\n📊 KEY FINANCIAL RATIOS:")
                print("-" * 60)
                
                ratios = result.ratios
                if ratios.roe:
                    print(f"  ROE:              {ratios.roe * 100:>8.1f}%")
                if ratios.roa:
                    print(f"  ROA:              {ratios.roa * 100:>8.1f}%")
                if ratios.roic:
                    print(f"  ROIC:             {ratios.roic * 100:>8.1f}%")
                if ratios.pe_ratio:
                    print(f"  P/E Ratio:        {ratios.pe_ratio:>8.1f}x")
                if ratios.pb_ratio:
                    print(f"  P/B Ratio:        {ratios.pb_ratio:>8.1f}x")
                if ratios.debt_to_equity:
                    print(f"  Debt/Equity:      {ratios.debt_to_equity:>8.2f}")
                if ratios.current_ratio:
                    print(f"  Current Ratio:    {ratios.current_ratio:>8.2f}")
                if ratios.net_margin:
                    print(f"  Net Margin:       {ratios.net_margin * 100:>8.1f}%")
                
                # Print growth metrics
                print("\n📈 GROWTH METRICS:")
                print("-" * 60)
                
                growth = result.growth
                if growth.revenue_growth_yoy:
                    print(f"  Revenue Growth (YoY):   {growth.revenue_growth_yoy * 100:>8.1f}%")
                if growth.earnings_growth_yoy:
                    print(f"  Earnings Growth (YoY):  {growth.earnings_growth_yoy * 100:>8.1f}%")
                if growth.eps_growth_yoy:
                    print(f"  EPS Growth (YoY):       {growth.eps_growth_yoy * 100:>8.1f}%")
                
                # Store for summary
                all_results.append({
                    'ticker': ticker,
                    'name': result.company_name,
                    'overall_score': result.overall_score,
                    'grade': result.investment_grade,
                    'health': result.financial_health,
                    'pe': result.ratios.pe_ratio,
                    'roe': result.ratios.roe,
                    'debt_equity': result.ratios.debt_to_equity,
                })
            
            print()
        
        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted by user")
            break
        except Exception as e:
            print(f"\n❌ Error analyzing {ticker}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Summary table
    if all_results:
        print("\n" + "=" * 90)
        print("📊 FUNDAMENTAL ANALYSIS SUMMARY")
        print("=" * 90)
        print(f"{'Ticker':<8} {'Company':<25} {'Score':>8} {'Grade':<12} {'Health':<12} {'P/E':>8} {'ROE':>8}")
        print("-" * 90)
        
        for r in sorted(all_results, key=lambda x: -x['overall_score']):
            pe_str = f"{r['pe']:.1f}" if r['pe'] else "N/A"
            roe_str = f"{r['roe']*100:.1f}%" if r['roe'] else "N/A"
            
            grade_emoji = "🟢" if r['grade'] in ['STRONG_BUY', 'BUY'] else "🟡" if r['grade'] == 'HOLD' else "🔴"
            
            print(f"{r['ticker']:<8} {r['name'][:25]:<25} {r['overall_score']:>8.1f} {grade_emoji} {r['grade']:<10} {r['health']:<12} {pe_str:>8} {roe_str:>8}")
        
        print("=" * 90)
        
        # Top picks
        print("\n🏆 TOP FUNDAMENTAL PICKS:")
        top_picks = sorted(all_results, key=lambda x: -x['overall_score'])[:3]
        for i, r in enumerate(top_picks, 1):
            print(f"  {i}. {r['ticker']} - {r['name']} (Score: {r['overall_score']:.1f}, Grade: {r['grade']})")
    
    print("\n✅ Demo completed!")
    print("\n📝 Next Steps:")
    print("   1. Review fundamental scores above")
    print("   2. Combine with technical analysis for better stock selection")
    print("   3. Backtest fundamental-based strategies")
    print("   4. Add more IDX stocks to the sector mapping")
    print()


if __name__ == "__main__":
    main()
