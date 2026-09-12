#!/usr/bin/env python3
"""Per-trade performance snapshot for the crypto engines.

Computes expectancy / win-rate / reason breakdown per mode (REAL or PAPER)
from CLOSED positions, plus a before/after comparison around a baseline date
(used to judge strategy changes like the SL_ATR_MULT 2.0→3.0 deploy).

Usage:
    python scripts/crypto_stats.py                       # print current snapshot
    python scripts/crypto_stats.py --baseline 2026-09-12 # compare 7d-before vs since
    python scripts/crypto_stats.py --history             # append today's row to data/crypto_stats_history.csv

Requires DB access via app config (run on the VPS / inside the bot container).
"""

import argparse
import asyncio
import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from app.db.session import async_session_factory
from app.models.crypto import CryptoPaperPosition

STATUS_CLOSED = "CLOSED"


def _summarize(rows: list) -> dict:
    """rows: list of (mode, exit_reason, realized_pnl, closed_at)."""
    total = len(rows)
    wins = [r[2] for r in rows if r[2] is not None and r[2] > 0]
    losses = [r[2] for r in rows if r[2] is not None and r[2] <= 0]
    n_w = len(wins)
    n_l = len(losses)
    avg_win = sum(wins) / n_w if n_w else 0.0
    avg_loss = sum(losses) / n_l if n_l else 0.0
    total_pnl = sum(r[2] for r in rows if r[2] is not None)
    expectancy = (avg_win * n_w + avg_loss * n_l) / total if total else 0.0
    reasons = {}
    for _, reason, _, _ in rows:
        reasons[reason] = reasons.get(reason, 0) + 1
    return {
        "trades": total,
        "win_rate": (n_w / total * 100.0) if total else 0.0,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "expectancy": expectancy,
        "total_pnl": total_pnl,
        "reasons": reasons,
    }


def _fmt(s: dict) -> str:
    r = s["reasons"]
    return (
        f"n={s['trades']:3d} WR={s['win_rate']:5.1f}% avgW={s['avg_win']:+.3f} "
        f"avgL={s['avg_loss']:+.3f} exp={s['expectancy']:+.4f} pnl={s['total_pnl']:+.3f} "
        f"USDT  (TP1={r.get('TP1', 0)} TP2={r.get('TP2', 0)} SL={r.get('SL', 0)} "
        f"END={r.get('END', 0)})"
    )


async def _load_since(session, since: datetime) -> list:
    rows = []
    res = await session.execute(
        select(CryptoPaperPosition.mode, CryptoPaperPosition.exit_reason,
               CryptoPaperPosition.realized_pnl, CryptoPaperPosition.closed_at)
        .where(CryptoPaperPosition.status == STATUS_CLOSED,
               CryptoPaperPosition.closed_at >= since)
        .order_by(CryptoPaperPosition.closed_at)
    )
    for mode, reason, pnl, closed_at in res.all():
        rows.append((mode, reason, pnl, closed_at))
    return rows


async def main() -> None:
    parser = argparse.ArgumentParser(description="Crypto per-trade performance snapshot")
    parser.add_argument("--baseline", type=str, default=None,
                        help="ISO date (UTC) marking a strategy change. Compares the "
                             "7 days before vs everything since. Default: 2026-09-12 "
                             "(the SL 2.0→3.0 deploy).")
    parser.add_argument("--history", action="store_true",
                        help="Append today's REAL/PAPER snapshot to data/crypto_stats_history.csv")
    args = parser.parse_args()

    baseline = datetime(2026, 9, 12, tzinfo=timezone.utc) if not args.baseline else \
        datetime.fromisoformat(args.baseline.replace("Z", "+00:00"))

    async with async_session_factory() as session:
        all_rows = await _load_since(session, baseline - timedelta(days=30))
        today = datetime.now(timezone.utc)

        print("=" * 78)
        print("CRYPTO PERFORMANCE SNAPSHOT")
        print(f"Generated: {today:%Y-%m-%d %H:%M} UTC")
        print("=" * 78)

        since = baseline - timedelta(days=7)
        for mode in ("REAL", "PAPER"):
            before = [r for r in all_rows if r[0] == mode and since <= r[3] < baseline]
            after = [r for r in all_rows if r[0] == mode and r[3] >= baseline]
            print(f"\n[{mode}]  before {since:%d-%b}→{baseline:%d-%b}:")
            print(f"    {_fmt(_summarize(before))}")
            print(f"[{mode}]  after  {baseline:%d-%b}→now:")
            print(f"    {_fmt(_summarize(after))}")

        if args.history:
            out_path = Path(__file__).parent.parent / "data" / "crypto_stats_history.csv"
            out_path.parent.mkdir(exist_ok=True)
            is_new = not out_path.exists()
            with out_path.open("a", newline="") as f:
                w = csv.writer(f)
                if is_new:
                    w.writerow(["date_utc", "mode", "trades", "win_rate", "avg_win",
                                "avg_loss", "expectancy", "total_pnl"])
                for mode in ("REAL", "PAPER"):
                    today_rows = [r for r in all_rows
                                  if r[0] == mode and baseline <= r[3] and r[3].date() == today.date()]
                    s = _summarize(today_rows)
                    w.writerow([today.strftime("%Y-%m-%d"), mode, s["trades"],
                                round(s["win_rate"], 1), round(s["avg_win"], 4),
                                round(s["avg_loss"], 4), round(s["expectancy"], 4),
                                round(s["total_pnl"], 4)])
            print(f"\n→ history appended: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())