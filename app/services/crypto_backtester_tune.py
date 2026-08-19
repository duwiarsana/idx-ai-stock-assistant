"""Grid-search tuning for the crypto paper strategy using cached history.

Fetches klines once per symbol, then runs the backtester across a grid of
(entry_score, pullback_pct, sl_mult, tp1_mult) to find the best parameter set
without re-hitting the rate-limited API for every combo.

Usage:
    python -m app.services.crypto_backtester_tune --days 60 --top 15
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from app.data.tokocrypto_client import TokocryptoClient
from app.services.crypto_backtester import (
    CryptoBacktester,
    BacktestParams,
    BacktestResult,
    pick_liquid_symbols,
    WARMUP_BARS,
)

logger = logging.getLogger(__name__)


async def main(args) -> None:
    client = TokocryptoClient()
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = await pick_liquid_symbols(client, "USDT", args.top)

    # Fetch once per symbol.
    histories = {}
    for sym in symbols:
        try:
            klines = await client_safe_fetch(client, sym, args.days)
            if len(klines["1h"]) >= WARMUP_BARS + 20:
                histories[sym] = klines
                logger.info(f"  fetched {sym}: {len(klines['1h'])} 1h bars")
            else:
                logger.warning(f"  {sym}: insufficient history, skipped")
        except Exception as e:
            logger.warning(f"  {sym}: fetch failed ({e})")
        await asyncio.sleep(0.2)
    await client.close()

    if not histories:
        print("No usable history.")
        return

    grid = []
    for score in args.scores:
        for pull in args.pullbacks:
            for sl in args.sl_mults:
                for tp1 in args.tp1_mults:
                    grid.append((score, pull, sl, tp1))

    print(f"\nGrid: {len(grid)} combos across {len(histories)} symbols\n")

    rows = []
    for score, pull, sl, tp1 in grid:
        params = BacktestParams(
            entry_score=score,
            pullback_max_pct=pull,
            sl_mult=sl,
            tp1_mult=tp1,
        )
        bt = CryptoBacktester(client=TokocryptoClient(), params=params)
        total_trades = 0
        total_ret = 0.0
        total_wr = 0.0
        n = 0
        for sym, klines in histories.items():
            res = bt.run_symbol(klines, sym)
            m = res.metrics()
            total_trades += m["trades"]
            total_ret += m["total_return_pct"]
            total_wr += m["win_rate"]
            n += 1
        if n:
            avg_ret = total_ret / n
            avg_wr = total_wr / n
            rows.append({
                "score": score, "pull": pull, "sl": sl, "tp1": tp1,
                "trades": total_trades, "avg_wr": avg_wr, "avg_ret": avg_ret,
            })

    rows.sort(key=lambda r: r["avg_ret"], reverse=True)
    print(f"{'score':>5} {'pull%':>5} {'sl_x':>5} {'tp1_x':>5} {'trades':>6} {'win%':>6} {'avg_ret%':>9}")
    print("-" * 52)
    for r in rows:
        print(f"{r['score']:>5} {r['pull']:>5} {r['sl']:>5.2f} {r['tp1']:>5.2f} "
              f"{r['trades']:>6} {r['avg_wr']:>6.1f} {r['avg_ret']:>9.2f}")

    print("\nBEST:", rows[0] if rows else None)


async def client_safe_fetch(client: TokocryptoClient, sym: str, days: int):
    bt = CryptoBacktester(client=client)
    return await bt.fetch_history(sym, days=days)


def main_cli() -> None:
    parser = argparse.ArgumentParser(description="Tune crypto paper strategy params")
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--symbols", type=str, default="")
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--scores", type=str, default="75,80,85")
    parser.add_argument("--pullbacks", type=str, default="2.0,3.0,5.0")
    parser.add_argument("--sl-mults", type=str, default="0.75,1.0")
    parser.add_argument("--tp1-mults", type=str, default="1.5,2.0")
    args = parser.parse_args()
    args.scores = [float(x) for x in args.scores.split(",")]
    args.pullbacks = [float(x) for x in args.pullbacks.split(",")]
    args.sl_mults = [float(x) for x in args.sl_mults.split(",")]
    args.tp1_mults = [float(x) for x in args.tp1_mults.split(",")]

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    asyncio.run(main(args))


if __name__ == "__main__":
    main_cli()