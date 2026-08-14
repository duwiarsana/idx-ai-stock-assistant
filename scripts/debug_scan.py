#!/usr/bin/env python3
"""Debug scan - show all scores."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.realtime_scanner import RealtimeScanner, ScanCriteria


async def main():
    scanner = RealtimeScanner()
    
    tickers = ['BBCA', 'BBRI', 'TLKM', 'GOTO', 'ASII']
    
    print('DEBUG SCAN - Showing ALL scores')
    print('='*80)
    
    # Very loose criteria
    criteria = ScanCriteria(
        min_combined_score=30,
        min_conviction=0.2,
        min_volume_ratio=0.5,
        require_buy_signal=False,
    )
    
    for ticker in tickers:
        print(f'\n{ticker}:')
        try:
            alert = await scanner.scan_stock(ticker)
            
            if alert:
                print(f'  Combined:     {alert.combined_score:.1f}')
                print(f'  Technical:    {alert.technical_score:.1f}')
                print(f'  Fundamental:  {alert.fundamental_score:.1f}')
                print(f'  Signal:       {alert.signal}')
                print(f'  Conviction:   {alert.conviction:.2f}')
            else:
                print('  No alert generated')
                
        except Exception as e:
            print(f'  ERROR: {e}')

if __name__ == '__main__':
    asyncio.run(main())
