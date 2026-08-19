#!/usr/bin/env python3
"""Manual trigger for the Tokocrypto crypto scanner.

Usage:
    python scripts/crypto_scan.py            # run one scan
    python scripts/crypto_scan.py --dry-run  # run scan, log alerts only (no Telegram)
    python scripts/crypto_scan.py --top 5    # show top 5 candidates after scan
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def main():
    parser = argparse.ArgumentParser(description="Run one Tokocrypto momentum scan")
    parser.add_argument("--dry-run", action="store_true", help="Simulate alerts (no Telegram send)")
    parser.add_argument("--top", type=int, default=5, help="Number of top candidates to print")
    parser.add_argument("--json", action="store_true", help="Print results as JSON")
    args = parser.parse_args()

    from app.services.crypto_scanner import crypto_scanner

    print("=" * 72)
    print("CRYPTO SCANNER (Tokocrypto) — manual run")
    print("=" * 72)
    if args.dry_run:
        print("Mode: DRY-RUN (alerts logged, not sent to Telegram)")
    print()

    summary = await crypto_scanner.run_scan(dry_run=args.dry_run)

    print()
    print("=" * 72)
    print(f"Status: {summary.get('status')}")
    print(f"Pairs found:        {summary.get('pairs_found')}")
    print(f"Pairs liquid:       {summary.get('pairs_liquid')}")
    print(f"Pairs analysed:     {summary.get('pairs_analysed')}")
    print(f"Candidates:         {summary.get('candidates')}")
    print(f"AI analysed:        {summary.get('ai_analysed')}")
    print(f"Alerts sent:        {summary.get('alerts_sent')}")
    print(f"Errors:             {summary.get('errors')}")
    print(f"Duration:           {summary.get('duration_ms')} ms")
    print(f"Top candidate:      {summary.get('top_candidate')}")
    print("=" * 72)

    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    else:
        results = summary.get("results", [])[: args.top]
        if results:
            print()
            print(f"TOP {len(results)} CANDIDATES:")
            for r in results:
                verdict = r.get("ai_verdict", {}) or {}
                print(f"  {r.get('display', r.get('symbol')):<14} "
                      f"score={r.get('score'):<5} "
                      f"verdict={verdict.get('verdict', '?'):<12} "
                      f"risk={verdict.get('risk', '?')} "
                      f"relvol={r.get('relative_volume')}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
