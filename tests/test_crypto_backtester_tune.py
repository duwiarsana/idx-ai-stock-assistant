"""Tests for the Hyperopt-style tuner (app/services/crypto_backtester_tune.py)."""

from datetime import datetime, timezone

import pytest

from app.services.crypto_backtester import BacktestParams, BacktestResult, Trade
from app.services.crypto_backtester_tune import (
    aggregate_metrics,
    build_grid,
    random_combos,
)


def _trade(pnl: float, ts: int) -> Trade:
    t = datetime.fromtimestamp(ts, tz=timezone.utc)
    return Trade(
        symbol="X", entry_time=t, entry_price=100.0,
        exit_time=t, exit_price=100.0 * (1 + pnl / 100.0),
        exit_reason="TP1", pnl_pct=pnl, bars_held=1,
    )


def _result(pnls: list[float], ts0: int = 1_700_000_000) -> BacktestResult:
    r = BacktestResult(symbol="X", start=datetime.fromtimestamp(ts0, tz=timezone.utc),
                       end=datetime.fromtimestamp(ts0 + 1000, tz=timezone.utc))
    r.trades = [_trade(p, ts0 + i) for i, p in enumerate(pnls)]
    return r


class TestAggregateMetrics:
    def test_single_symbol_curve(self):
        # +10%, -5%, +20% → equity 1.1 → 1.045 → 1.254
        res = _result([10.0, -5.0, 20.0])
        m = aggregate_metrics([res])
        assert m["total_return_pct"] == 25.4
        assert m["win_rate"] == 66.7          # 2 wins / 3 trades
        assert m["profit_factor"] == 6.0       # 30 / 5
        assert m["max_drawdown_pct"] == 5.0    # 1.1 → 1.045
        assert m["trades"] == 3

    def test_merges_multiple_symbols(self):
        # Symbol A loses late (-5% at t1), symbol B wins at t1 → the merged
        # path compounds both; drawdown is computed on the combined equity.
        a = _result([10.0, -5.0], ts0=100)
        b = _result([20.0], ts0=101)           # exits after A's first trade
        m = aggregate_metrics([a, b])
        assert m["trades"] == 3
        # order by exit: +10, +20, -5 → 1.1*1.2*0.95 = 1.254 → 25.4%
        assert m["total_return_pct"] == pytest.approx(25.4)
        assert round(m["max_drawdown_pct"], 2) == round(
            (1.1 * 1.2 - 1.1 * 1.2 * 0.95) / (1.1 * 1.2) * 100, 2)

    def test_empty_results(self):
        m = aggregate_metrics([])
        assert m["trades"] == 0
        assert m["win_rate"] == 0.0
        assert m["profit_factor"] is None
        assert m["total_return_pct"] == 0.0

    def test_all_wins_no_losses_pf_is_inf(self):
        m = aggregate_metrics([_result([5.0, 7.0])])
        assert m["profit_factor"] is None      # ∞ marker
        assert m["win_rate"] == 100.0


class TestSearchSpace:
    def test_build_grid_cartesian(self):
        combos = build_grid([75, 80], [2.0, 3.0], [1.25], [1.5, 2.0], [3.0], [0, 2.0])
        assert len(combos) == 2 * 2 * 1 * 2 * 1 * 2 == 16
        c0, c1 = combos[0], combos[1]
        assert c0.params == BacktestParams(entry_score=75, pullback_max_pct=2.0,
                                           sl_mult=1.25, tp1_mult=1.5, tp2_mult=3.0,
                                           trailing_stop_pct=0)
        assert c1.trail == 2.0 and c1.params.trailing_stop_pct == 2.0

    def test_grid_maps_all_dimensions(self):
        combos = build_grid([70], [4.0], [1.0], [2.0], [3.0], [1.5])
        assert len(combos) == 1
        p = combos[0].params
        assert p.entry_score == 70 and p.pullback_max_pct == 4.0
        assert p.sl_mult == 1.0 and p.tp1_mult == 2.0 and p.tp2_mult == 3.0
        assert p.trailing_stop_pct == 1.5

    def test_random_combos_seed_deterministic(self):
        args = ([70, 80, 90], [2.0, 5.0], [1.0, 2.0], [1.5, 2.5], [3.0, 4.0], [0, 2.0])
        a = random_combos(*args, iters=25, seed=7)
        b = random_combos(*args, iters=25, seed=7)
        c = random_combos(*args, iters=25, seed=8)
        assert [(x.score, x.trail) for x in a] == [(x.score, x.trail) for x in b]
        assert [(x.score, x.trail) for x in a] != [(x.score, x.trail) for x in c]
        assert len(a) == 25

    def test_random_combos_bounds(self):
        combos = random_combos([75, 85], [2.0], [1.0], [2.0], [3.0], [0, 1.0], iters=10, seed=1)
        for cb in combos:
            assert cb.score in (75, 85)
            assert cb.trail in (0, 1.0)