#!/usr/bin/env python3
"""Quick scan - non-interactive version."""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.realtime_scanner import RealtimeScanner, ScanCriteria


async def main():
    scanner = RealtimeScanner()
    
    # Bluechip + liquid stocks
    tickers = [
        'BBCA', 'BBRI', 'BMRI', 'BBNI', 'BRIS',
        'TLKM', 'EXCL', 'ISAT',
        'UNVR', 'ICBP', 'INDF', 'MYOR', 'KLBF', 'AMRT',
        'ASII', 'UNTR', 'AUTO',
        'ADRO', 'ITMG', 'PTBA',
        'GOTO', 'EMTK',
        'JSMR', 'BSDE', 'SMRA',
        'ANTM', 'MDKA',
        'TPIA', 'INTP', 'SMGR',
        'PGAS', 'AKRA',
    ]
    
    print('='*80)
    print('IDX AI STOCK SCANNER - LIVE SCAN')
    print('='*80)
    print('Time:', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print('Stocks:', len(tickers))
    print('Criteria: Score >= 60, Conviction >= 0.5')
    print('='*80)
    print()
    
    criteria = ScanCriteria(
        min_combined_score=60,
        min_conviction=0.5,
        min_volume_ratio=1.0,
        require_buy_signal=False,
    )
    
    results = []
    
    for i, ticker in enumerate(tickers, 1):
        print(f'[{i}/{len(tickers)}] Scanning {ticker}...', end=' ', flush=True)
        
        try:
            alert = await scanner.scan_stock(ticker)
            
            if alert:
                results.append(alert)
                print(f'Score={alert.combined_score:.1f}')
            else:
                print('Skip')
                
        except Exception as e:
            print(f'Error: {str(e)[:40]}')
    
    print()
    print('='*80)
    print(f'RESULTS: {len(results)} stocks met criteria')
    print('='*80)
    
    if results:
        results.sort(key=lambda x: x.combined_score, reverse=True)
        
        print()
        print('TOP 10:')
        print(f'{"Rank":<5} {"Ticker":<8} {"Score":>7} {"Signal":<14} {"Conviction":>10}')
        print('-'*80)
        
        for i, r in enumerate(results[:10], 1):
            mark = '[+]' if r.combined_score >= 70 else '[!]'
            print(f'{mark} {i:<4} {r.ticker:<6} {r.combined_score:>6.1f} {r.signal:<14} {r.conviction:>9.2f}')
        
        print()
        print('='*80)
        top = results[0]
        print(f'BEST: {top.ticker} (Score: {top.combined_score:.1f}, Signal: {top.signal})')
    
    print('='*80)


if __name__ == '__main__':
    asyncio.run(main())
