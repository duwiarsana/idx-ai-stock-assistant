#!/usr/bin/env python3
"""Test scan - minimal criteria."""

import asyncio
import sys
from pathlib import Path
from dataclasses import dataclass, field

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.realtime_scanner import RealtimeScanner, ScanCriteria, AlertType


async def main():
    # Ultra loose criteria
    criteria = ScanCriteria(
        min_combined_score=30.0,
        min_conviction=0.2,
        min_volume_ratio=0.5,
        require_buy_signal=False,
        require_uptrend=False,
        exclude_penny_stocks=False,
        min_technical_score=20.0,
        min_fundamental_score=20.0,
        min_roe=-10.0,  # Allow negative
        max_debt_equity=10.0,  # Very high
        min_price=0.0,
    )
    
    scanner = RealtimeScanner(criteria=criteria)
    
    tickers = ['BBCA', 'BBRI', 'TLKM']
    
    print('ULTRA LOOSE CRITERIA TEST')
    print('='*80)
    
    for ticker in tickers:
        print(f'\nScanning {ticker}...')
        try:
            alert = await scanner.scan_stock(ticker)
            
            if alert:
                print(f'  ALERT GENERATED!')
                print(f'    Combined Score:  {alert.combined_score:.1f}')
                print(f'    Technical Score: {alert.technical_score:.1f}')
                print(f'    Fundamental:     {alert.fundamental_score:.1f}')
                print(f'    Signal:          {alert.signal}')
                print(f'    Conviction:      {alert.conviction:.2f}')
                print(f'    Alert Type:      {alert.alert_type}')
            else:
                print(f'  Still no alert - checking why...')
                
                # Manual check
                from app.services.enhanced_technicals import TechnicalAnalyzer
                from app.services.combined_analyzer import CombinedAnalyzer
                from app.services.fundamental_analyzer import FundamentalAnalyzer
                import yfinance as yf
                
                jk = f"{ticker}.JK"
                stock = yf.Ticker(jk)
                df = stock.history(period="1mo")
                
                if df.empty:
                    print(f'  -> No price data from Yahoo!')
                    continue
                
                df = df.reset_index()
                df.columns = df.columns.str.lower()
                
                tech = TechnicalAnalyzer().analyze(df, ticker)
                print(f'  -> Technical Score: {tech.composite_score if tech else "None"}')
                print(f'  -> Technical Signal: {tech.signal if tech else "None"}')
                
                fund = FundamentalAnalyzer().analyze(ticker)
                print(f'  -> Fundamental Score: {fund.overall_score if fund else "None"}')
                
                combined = CombinedAnalyzer().analyze(ticker, df)
                print(f'  -> Combined Score: {combined.combined_score if combined else "None"}')
                print(f'  -> Conviction: {combined.conviction if combined else "None"}')
                
        except Exception as e:
            print(f'  ERROR: {e}')
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(main())
