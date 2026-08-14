#!/usr/bin/env python3
"""Demo script for Real-time Stock Scanner.

Tests the scanner on a small subset of stocks to verify functionality.

Usage:
    python scripts/demo_scanner.py
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.realtime_scanner import (
    RealtimeScanner,
    ScanCriteria,
    ScanFrequency,
    IDXStockUniverse,
    StockAlert,
)


async def demo_single_scan():
    """Demo: Single scan of selected stocks."""
    print("\n" + "╔" + "=" * 70 + "╗")
    print("║" + " " * 15 + "IDX AI Stock Scanner - Single Scan Demo" + " " * 15 + "║")
    print("╚" + "=" * 70 + "╝")
    
    # Configure criteria
    criteria = ScanCriteria(
        min_technical_score=55.0,
        min_combined_score=60.0,
        min_conviction=0.5,
        min_volume_ratio=1.0,
        require_buy_signal=False,  # Show all signals for demo
        min_fundamental_score=45.0,
    )
    
    print("\n📋 SCAN CRITERIA:")
    print(f"  Min Technical Score: {criteria.min_technical_score}")
    print(f"  Min Combined Score: {criteria.min_combined_score}")
    print(f"  Min Conviction: {criteria.min_conviction*100:.0f}%")
    print(f"  Min Volume Ratio: {criteria.min_volume_ratio}x")
    print(f"  Require Buy Signal: {criteria.require_buy_signal}")
    
    # Create scanner
    scanner = RealtimeScanner(criteria=criteria, frequency=ScanFrequency.NORMAL)
    
    # Test stocks
    test_stocks = ["BBCA", "BBRI", "TLKM", "UNVR", "GOTO", "ADRO"]
    
    print(f"\n🔍 SCANNING {len(test_stocks)} STOCKS...")
    print("=" * 80)
    
    alerts = []
    
    for ticker in test_stocks:
        print(f"\n📊 Scanning {ticker}...")
        alert = await scanner.scan_stock(ticker)
        
        if alert:
            alerts.append(alert)
            print(f"\n{'=' * 80}")
            print(f"🚨 ALERT: {alert.ticker}")
            print(f"{'=' * 80}")
            print(alert.to_telegram_message())
        else:
            print(f"  ❌ No alert for {ticker}")
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 SCAN SUMMARY")
    print("=" * 80)
    print(f"Stocks Scanned: {len(test_stocks)}")
    print(f"Alerts Triggered: {len(alerts)}")
    print(f"Alert Rate: {len(alerts)/len(test_stocks)*100:.0f}%")
    
    if alerts:
        print("\n🏆 TOP ALERTS:")
        for i, alert in enumerate(sorted(alerts, key=lambda x: -x.combined_score)[:3], 1):
            print(f"  {i}. {alert.ticker} - {alert.alert_type} (Score: {alert.combined_score:.1f})")
    
    return alerts


async def demo_continuous_scan():
    """Demo: Continuous scanning (3 iterations)."""
    print("\n" + "╔" + "=" * 70 + "╗")
    print("║" + " " * 12 + "IDX AI Stock Scanner - Continuous Scan Demo" + " " * 12 + "║")
    print("╚" + "=" * 70 + "╝")
    
    criteria = ScanCriteria(
        min_technical_score=60.0,
        min_combined_score=65.0,
        min_conviction=0.6,
    )
    
    scanner = RealtimeScanner(
        criteria=criteria,
        frequency=ScanFrequency.HIGH,  # 5 minutes
    )
    
    print("\n⚙️  Starting continuous scan (3 iterations)...")
    print(f"   Scan interval: {scanner.get_scan_interval()}s")
    print(f"   Stocks to scan: {len(IDXStockUniverse.get_priority_list())}")
    
    # Run 3 iterations
    for i in range(3):
        print(f"\n\n{'=' * 80}")
        print(f"📅 ITERATION {i+1}/3 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'=' * 80}")
        
        alerts = await scanner.scan_all_stocks()
        
        print(f"\n📊 Iteration {i+1} Summary:")
        print(f"   Alerts: {len(alerts)}")
        print(f"   Total alerts so far: {scanner.alert_count}")
        
        if i < 2:
            print(f"\n⏳ Waiting {scanner.get_scan_interval()}s for next scan...")
            await asyncio.sleep(10)  # Shorter wait for demo
    
    # Final status
    print("\n" + "=" * 80)
    print("📊 FINAL STATUS")
    print("=" * 80)
    status = scanner.get_status()
    for key, value in status.items():
        print(f"  {key}: {value}")


def demo_criteria_presets():
    """Demo: Show different criteria presets."""
    print("\n" + "╔" + "=" * 70 + "╗")
    print("║" + " " * 15 + "IDX AI Stock Scanner - Criteria Presets" + " " * 15 + "║")
    print("╚" + "=" * 70 + "╝")
    
    presets = {
        'Conservative': {
            'min_combined_score': 75,
            'min_conviction': 0.8,
            'min_volume_ratio': 2.0,
            'require_buy_signal': True,
        },
        'Moderate': {
            'min_combined_score': 65,
            'min_conviction': 0.6,
            'min_volume_ratio': 1.5,
            'require_buy_signal': True,
        },
        'Aggressive': {
            'min_combined_score': 55,
            'min_conviction': 0.4,
            'min_volume_ratio': 1.0,
            'require_buy_signal': False,
        },
        'Breakout Hunter': {
            'min_combined_score': 60,
            'min_conviction': 0.5,
            'min_volume_ratio': 3.0,
            'require_buy_signal': True,
        },
    }
    
    print("\n📋 AVAILABLE CRITERIA PRESETS:")
    print("=" * 80)
    
    for name, config in presets.items():
        print(f"\n🔹 {name}:")
        for key, value in config.items():
            print(f"   • {key}: {value}")
    
    print("\n💡 Use these presets by modifying ScanCriteria parameters:")
    print("""
    criteria = ScanCriteria(
        min_combined_score=75,
        min_conviction=0.8,
        min_volume_ratio=2.0,
        require_buy_signal=True,
    )
    """)


async def main():
    """Main demo function."""
    print("\n" + "🚀 " * 20 + "\n")
    
    # Demo 1: Criteria presets
    demo_criteria_presets()
    
    # Demo 2: Single scan
    input("\nPress Enter to run single scan demo...")
    await demo_single_scan()
    
    # Demo 3: Continuous scan (optional)
    response = input("\nRun continuous scan demo? (y/n): ")
    if response.lower() == 'y':
        await demo_continuous_scan()
    
    print("\n" + "✅ " * 20 + "\n")
    print("Demo completed!")
    print("\n📝 To run the full scanner:")
    print("   python -m app.services.realtime_scanner")
    print("\n📝 Or as background service:")
    print("   nohup python -m app.services.realtime_scanner > scanner.log 2>&1 &")
    print()


if __name__ == "__main__":
    asyncio.run(main())
