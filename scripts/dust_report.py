#!/usr/bin/env python3
"""Manual dust report for the Tokocrypto spot wallet.

Lists leftover balances too small to be sold individually (below the
exchange minimum notional) and sends the report to Telegram when
configured. READ-ONLY: this script never places orders.

Usage:
    python scripts/dust_report.py            # scan + Telegram send
    python scripts/dust_report.py --no-send  # print report to stdout only
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def main():
    parser = argparse.ArgumentParser(description="Scan wallet dust (read-only)")
    parser.add_argument(
        "--no-send",
        action="store_true",
        help="print the report to stdout without sending to Telegram",
    )
    args = parser.parse_args()

    from app.services.crypto_dust import run_dust_report

    message = await run_dust_report(notify=not args.no_send)
    if message is None:
        print("Wallet balances unavailable (API keys not configured or empty wallet).")
        return
    print(message)
    if args.no_send:
        print("\n(dry-run: Telegram send skipped)")


if __name__ == "__main__":
    asyncio.run(main())
