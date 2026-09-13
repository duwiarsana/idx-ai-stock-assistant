"""Hyperopt-style parameter tuning for the crypto momentum strategy.

Adopts the Freqtrade Hyperopt idea: fetch klines ONCE per symbol, then run the
backtester across many parameter combinations (grid or random search) and rank
them by aggregate risk/return metrics — without re-hitting the rate-limited
Tokocrypto API for every combo.

Search space (each dimension is a CSV list on the CLI):
  - momentum entry score threshold   (--scores)
  - TP1 / TP2 / SL ATR multiples     (--tp1, --tp2, --sl)
  - pullback max %                   (--pullbacks)
  - trailing stop % of peak          (--trailing; 0 = static SL only)

Each combination is evaluated on the SAME history, then trades from all
symbols are merged into one equity curve to compute the reported metrics:
Win Rate, Profit Factor, Max Drawdown, Total Return.

Usage:
    python -m app.services.crypto_backtester_tune --days 60 --top 15
    python -m app.services.crypto_backtester_tune --search random --iters 50
    python -m app.services.crypto_backtester_tune --scores 80,85 \
        --tp1 2,2.5 --tp2 3,4 --sl 1.0,1.5 --trailing 0,1.5,2.5 --sort-by pf
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import logging
import math
import random
from dataclasses import dataclass
from typing import Optional

from app.data.tokocrypto_client import TokocryptoClient
from app.services.crypto_backtester import (
    CryptoBacktester,
    BacktestParams,
    BacktestResult,
    pick_liquid_symbols,
    WARMUP_BARS,
)

logger = logging.getLogger(__name__)


@dataclass
class Combo:
    """One parameter combination + its aggregate backtest outcome."""

    params: BacktestParams
    score: float
    pull: float
    sl: float
    tp1: float
    tp2: float
    trail: float
    trades: int = 0
    win_rate: float = 0.0
    profit_factor: Optional[float] = None
    max_drawdown_pct: float = 0.0
    total_return_pct: float = 0.0
    rank: int = 0


def build_grid(scores, pullbacks, sl_mults, tp1_mults, tp2_mults, trailing_pcts) -> list[Combo]:
    """Cartesian product of the search dimensions (grid search)."""
    combos = []
    for vals in itertools.product(scores, pullbacks, sl_mults, tp1_mults, tp2_mults, trailing_pcts):
        score, pull, sl, tp1, tp2, trail = vals
        combos.append(Combo(
            params=BacktestParams(
                entry_score=score,
                pullback_max_pct=pull,
                sl_mult=sl,
                tp1_mult=tp1,
                tp2_mult=tp2,
                trailing_stop_pct=trail,
            ),
            score=score, pull=pull, sl=sl, tp1=tp1, tp2=tp2, trail=trail,
        ))
    return combos


def random_combos(scores, pullbacks, sl_mults, tp1_mults, tp2_mults, trailing_pcts,
                  iters: int, seed: int | None = None) -> list[Combo]:
    """Random search: sample the same dimensions uniformly, allowing repeats."""
    rng = random.Random(seed)
    combos = []
    for _ in range(iters):
        score = rng.choice(scores)
        pull = rng.choice(pullbacks)
        sl = rng.choice(sl_mults)
        tp1 = rng.choice(tp1_mults)
        tp2 = rng.choice(tp2_mults)
        trail = rng.choice(trailing_pcts)
        combos.append(Combo(
            params=BacktestParams(
                entry_score=score,
                pullback_max_pct=pull,
                sl_mult=sl,
                tp1_mult=tp1,
                tp2_mult=tp2,
                trailing_stop_pct=trail,
            ),
            score=score, pull=pull, sl=sl, tp1=tp1, tp2=tp2, trail=trail,
        ))
    return combos


def aggregate_metrics(results: list[BacktestResult]) -> dict:
    """Merge all trades (across symbols) into one equity curve.

    Returns the Freqtrade-style headline metrics used for ranking:
    ``trades``, ``win_rate``, ``profit_factor``, ``max_drawdown_pct``,
    ``total_return_pct``. Trades are ordered by exit time so drawdown follows
    the chronological PnL path of the strategy as a whole.
    """
    trades = [t for r in results for t in r.trades]
    if not trades:
        return {"trades": 0, "win_rate": 0.0, "profit_factor": None,
                "max_drawdown_pct": 0.0, "total_return_pct": 0.0}

    ordered = sorted(trades, key=lambda t: (t.exit_time, t.symbol))

    wins = [t.pnl_pct for t in ordered if t.pnl_pct > 0]
    losses = [t.pnl_pct for t in ordered if t.pnl_pct <= 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    profit_factor = gross_win / gross_loss if gross_loss > 0 else None

    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for t in ordered:
        equity *= (1 + t.pnl_pct / 100.0)
        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100.0 if peak > 0 else 0.0
        max_dd = max(max_dd, dd)

    return {
        "trades": len(ordered),
        "win_rate": round(len(wins) / len(ordered) * 100.0, 1),
        "profit_factor": round(profit_factor, 2) if profit_factor and math.isfinite(profit_factor) else None,
        "max_drawdown_pct": round(max_dd, 2),
        "total_return_pct": round((equity - 1) * 100.0, 2),
    }


def run_combo(bt: CryptoBacktester, combo: Combo, histories: dict) -> None:
    """Evaluate one combo on every symbol's cached history."""
    bt.params = combo.params
    results = [bt.run_symbol(klines, sym) for sym, klines in histories.items()]
    m = aggregate_metrics(results)
    combo.trades = m["trades"]
    combo.win_rate = m["win_rate"]
    combo.profit_factor = m["profit_factor"]
    combo.max_drawdown_pct = m["max_drawdown_pct"]
    combo.total_return_pct = m["total_return_pct"]


def _fmt_pf(value: Optional[float]) -> str:
    if value is None:
        return "  ∞ "  # no losses (or no trades)
    return f"{value:>4.2f}"


def render_table(combos: list[Combo], sort_by: str = "total") -> list[Combo]:
    """Rank combos by the chosen objective and print the summary table."""
    keys = {
        "total": lambda c: c.total_return_pct,
        "pf": lambda c: c.profit_factor if c.profit_factor is not None else float("inf"),
        "wr": lambda c: c.win_rate,
        "dd": lambda c: -c.max_drawdown_pct,
    }
    ranked = sorted(combos, key=keys[sort_by], reverse=True)
    for i, c in enumerate(ranked):
        c.rank = i + 1

    print("\n" + "=" * 78)
    print(f"Ranking by: {sort_by}   |   combos={len(ranked)}")
    print("=" * 78)
    print(f"{'#':>3} {'score':>5} {'pull%':>5} {'sl_x':>5} {'tp1_x':>5} {'tp2_x':>5} "
          f"{'trail%':>6} {'trades':>6} {'win%':>6} {'PF':>6} {'maxDD%':>7} {'totRet%':>9}")
    print("-" * 78)
    for c in ranked:
        print(f"{c.rank:>3} {c.score:>5.0f} {c.pull:>5.1f} {c.sl:>5.2f} {c.tp1:>5.2f} "
              f"{c.tp2:>5.2f} {c.trail:>6.1f} {c.trades:>6} {c.win_rate:>6.1f} "
              f"{_fmt_pf(c.profit_factor):>6} {c.max_drawdown_pct:>7.2f} {c.total_return_pct:>9.2f}")
    print("-" * 78)
    return ranked


async def main(args) -> None:
    client = TokocryptoClient()
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = await pick_liquid_symbols(client, "USDT", args.top)

    # Fetch once per symbol — the whole point of keeping the API off the grid.
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

    if args.search == "random":
        combos = random_combos(args.scores, args.pullbacks, args.sl_mults,
                               args.tp1_mults, args.tp2_mults, args.trailing,
                               args.iters, seed=args.seed)
        print(f"\nRandom search: {len(combos)} sampled combos across {len(histories)} symbols\n")
    else:
        combos = build_grid(args.scores, args.pullbacks, args.sl_mults,
                            args.tp1_mults, args.tp2_mults, args.trailing)
        print(f"\nGrid search: {len(combos)} combos across {len(histories)} symbols\n")

    # One backtester, reused across combos (run_symbol never touches the client).
    bt = CryptoBacktester(client=TokocryptoClient())
    try:
        for n, combo in enumerate(combos, 1):
            run_combo(bt, combo, histories)
            if n % max(1, len(combos) // 10) == 0 or n == len(combos):
                logger.info(f"  evaluated {n}/{len(combos)} combos")
    finally:
        await bt.close()

    ranked = render_table(combos, sort_by=args.sort_by)

    html = getattr(args, "out", None)
    if html:
        _write_html_report(ranked, html)


def _write_html_report(ranked: list[Combo], path: str) -> None:
    """Dump the ranked table as a tiny self-contained HTML report."""
    rows = "".join(
        f"<tr><td>{c.rank}</td><td>{c.score:.0f}</td><td>{c.pull:.1f}</td>"
        f"<td>{c.sl:.2f}</td><td>{c.tp1:.2f}</td><td>{c.tp2:.2f}</td>"
        f"<td>{c.trail:.1f}</td><td>{c.trades}</td><td>{c.win_rate:.1f}</td>"
        f"<td>{_fmt_pf(c.profit_factor)}</td><td>{c.max_drawdown_pct:.2f}</td>"
        f"<td>{c.total_return_pct:.2f}</td></tr>"
        for c in ranked
    )
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Crypto backtest hyperopt results</title>
<style>
body{{font:13px/1.4 -apple-system,sans-serif;margin:24px}}
table{{border-collapse:collapse}}
td,th{{border:1px solid #ddd;padding:4px 10px;text-align:right}}
tr:first-child{{background:#eaffea}}
th{{background:#f5f5f5}}
</style></head><body>
<h2>Hyperopt grid/random search — ranked</h2>
<table><tr><th>#</th><th>score</th><th>pull%</th><th>sl_x</th><th>tp1_x</th><th>tp2_x</th>
<th>trail%</th><th>trades</th><th>win%</th><th>PF</th><th>maxDD%</th><th>totRet%</th></tr>
{rows}</table></body></html>"""
    with open(path, "w") as fh:
        fh.write(doc)
    print(f"\nHTML report: {path}")


async def client_safe_fetch(client: TokocryptoClient, sym: str, days: int):
    bt = CryptoBacktester(client=client)
    return await bt.fetch_history(sym, days=days)


def _parse_csv(value: str) -> list[float]:
    return [float(x.strip()) for x in value.split(",") if x.strip()]


def main_cli() -> None:
    parser = argparse.ArgumentParser(description="Tune crypto strategy params (Hyperopt-style)")
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--symbols", type=str, default="")
    parser.add_argument("--top", type=int, default=15)

    parser.add_argument("--search", choices=("grid", "random"), default="grid")
    parser.add_argument("--iters", type=int, default=50, help="random-search sample count")
    parser.add_argument("--seed", type=int, default=None, help="random-search seed")

    # The search dimensions.
    parser.add_argument("--scores", type=str, default="75,80,85", help="momentum entry score thresholds")
    parser.add_argument("--pullbacks", type=str, default="2.0,3.0,5.0", help="pullback max %")
    parser.add_argument("--sl-mults", type=str, default="0.75,1.25,2.0", help="SL ATR multiples")
    parser.add_argument("--tp1-mults", type=str, default="1.5,2.0,2.5", help="TP1 ATR multiples")
    parser.add_argument("--tp2-mults", type=str, default="2.5,3.0,4.0", help="TP2 ATR multiples")
    parser.add_argument("--trailing", type=str, default="0,1.0,2.0,3.0",
                        help="trailing stop % of peak (0 = static SL only, -1 = keep ATR-style)")
    parser.add_argument("--sort-by", choices=("total", "pf", "wr", "dd"), default="total")
    parser.add_argument("--out", type=str, default="", help="optional HTML report path")

    args = parser.parse_args()
    args.scores = _parse_csv(args.scores)
    args.pullbacks = _parse_csv(args.pullbacks)
    args.sl_mults = _parse_csv(args.sl_mults)
    args.tp1_mults = _parse_csv(args.tp1_mults)
    args.tp2_mults = _parse_csv(args.tp2_mults)
    args.trailing = _parse_csv(args.trailing)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    asyncio.run(main(args))


if __name__ == "__main__":
    main_cli()