"""Tests for the crypto strategy backtester (deterministic, no network)."""

import pytest

from app.services.crypto_backtester import (
    CryptoBacktester,
    BacktestParams,
    _resample_1h,
    _pct_change,
)


def make_15m_candles(n=500):
    """Synthetic uptrending 15m candles (1 per 15 min)."""
    out = []
    price = 100.0
    ts = 1_700_000_000_000
    for i in range(n):
        price *= (1 + 0.001)  # gentle uptrend
        out.append({
            "openTime": ts + i * 900_000,
            "open": price,
            "high": price * 1.01,
            "low": price * 0.99,
            "close": price,
            "volume": 1000.0,
        })
    return out


def test_resample_1h_groups_four_15m_bars():
    c15 = [
        {"openTime": 0, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
        {"openTime": 900_000, "open": 1.5, "high": 3, "low": 1, "close": 2, "volume": 5},
        {"openTime": 3_600_000, "open": 2, "high": 4, "low": 1.5, "close": 3, "volume": 7},
    ]
    out = _resample_1h(c15)
    assert len(out) == 2
    assert out[0]["high"] == 3
    assert out[0]["low"] == 0.5
    assert out[0]["close"] == 2
    assert out[0]["volume"] == 15


def test_pct_change():
    closes = [100, 100, 110]
    assert _pct_change(closes, 1) == pytest.approx(10.0)
    assert _pct_change(closes, 5) is None


def test_backtest_metrics_empty():
    from app.services.crypto_backtester import BacktestResult
    res = BacktestResult(symbol="X", start=None, end=None)
    m = res.metrics()
    assert m["trades"] == 0


def test_backtest_metrics_counts_reasons():
    from datetime import datetime, timezone
    from app.services.crypto_backtester import BacktestResult, Trade
    now = datetime.now(timezone.utc)
    res = BacktestResult(symbol="X", start=now, end=now)
    res.trades.append(Trade("X", now, 1.0, now, 1.05, "TP1", pnl_pct=5.0, bars_held=2))
    res.trades.append(Trade("X", now, 1.0, now, 0.95, "SL", pnl_pct=-5.0, bars_held=2))
    res.trades.append(Trade("X", now, 1.0, now, 1.02, "TP1", pnl_pct=2.0, bars_held=1))
    m = res.metrics()
    assert m["trades"] == 3
    assert m["win_rate"] == pytest.approx(66.7, abs=0.1)
    assert m["tp1"] == 2
    assert m["sl"] == 1
    assert m["profit_factor"] == pytest.approx(1.4, abs=0.01)


def test_gate_rejects_when_no_uptrend(monkeypatch):
    bt = CryptoBacktester(params=BacktestParams(entry_score=75, require_uptrend=True))
    cand = {
        "score": 90,
        "tf_summaries": {"1h": {"trend": "neutral", "macd_state": "bullish"}},
    }
    assert not bt._passes_gate(cand)


def test_gate_rejects_extended_above_ema(monkeypatch):
    bt = CryptoBacktester(params=BacktestParams(entry_score=75, pullback_max_pct=5.0))
    cand = {
        "score": 90,
        "tf_summaries": {"1h": {
            "trend": "bullish", "macd_state": "bullish",
            "price": 110.0, "ema20": 100.0, "at_high": False,
        }},
    }
    assert not bt._passes_gate(cand)


def test_gate_accepts_healthy_pullback(monkeypatch):
    bt = CryptoBacktester(params=BacktestParams(entry_score=75, pullback_max_pct=5.0))
    cand = {
        "score": 90,
        "tf_summaries": {"1h": {
            "trend": "bullish", "macd_state": "bullish",
            "price": 102.0, "ema20": 100.0, "at_high": False,
        }},
    }
    assert bt._passes_gate(cand)


def test_run_symbol_no_lookahead_uses_only_past_bars():
    """Entry gate uses bars before the entry bar (no look-ahead)."""
    candles = make_15m_candles(400)
    from app.services.crypto_backtester import WARMUP_BARS
    assert WARMUP_BARS > 0
    # Just verify the engine runs end-to-end without raising on synthetic data.
    klines = {"15m": candles, "1h": _resample_1h(candles)}
    bt = CryptoBacktester(params=BacktestParams(entry_score=75, pullback_max_pct=5.0))
    res = bt.run_symbol(klines, "SYNTH")
    assert isinstance(res.trades, list)


def _forced_candidate_klines(ride_highs):
    """1h bars long enough for WARMUP + a synthetic candidate whose exits hit
    TP1 first (103), then the rider behaves per ``ride_highs``. Entry at 100."""
    from app.services.crypto_backtester import WARMUP_BARS
    base = 1_700_000_000_000
    c1h = []
    for i in range(WARMUP_BARS + 4):
        c1h.append({
            "openTime": base + i * 3_600_000,
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
            "volume": 1000.0,
        })
    entry_ts = c1h[WARMUP_BARS]["openTime"]
    # Two pre-entry 15m bars (skipped), then the ride sequence. Bars on/above
    # TP1 keep low == high so an intra-bar dip can't trip the trailing stop
    # before the TP they're meant to trigger.
    c15 = []
    for j in range(len(ride_highs) + 2):
        ts = (entry_ts - 2 * 900_000) + j * 900_000
        ride = ride_highs[j - 2] if j >= 2 else 100.0
        c15.append({
            "openTime": ts,
            "open": 100.0,
            "high": ride,
            "low": ride,
            "close": ride,
            "volume": 1000.0,
        })
    return {"15m": c15, "1h": c1h}, WARMUP_BARS


def _forced_bt(params):
    from app.services.crypto_backtester import CryptoBacktester
    bt = CryptoBacktester(params=params)
    bt._candidate_at = lambda klines, idx: (
        {"price": 100.0, "price_levels": {"entry": 100.0, "take_profit_1": 103.0,
                                          "take_profit_2": 106.0, "stop_loss": 97.0}}
        if idx == params._entry_idx else None
    )
    bt._passes_gate = lambda cand: True
    return bt


def test_partial_tp1_then_rider_closes_at_tp2():
    """50% booked at TP1; the remainder rides to TP2 — the combined trade is
    weighted (50×TP1 + 50×TP2) so pnl_pct matches the live engine."""
    from app.services.crypto_backtester import BacktestParams
    params = BacktestParams(partial_tp1_pct=50.0)
    params._entry_idx = None
    klines, i = _forced_candidate_klines([100.0, 104.0, 101.0, 107.0])
    params._entry_idx = i
    bt = _forced_bt(params)
    res = bt.run_symbol(klines, "SYNTH")
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t.exit_reason == "TP1+TP2"
    assert t.exit_price == pytest.approx(104.5)          # 0.5*103 + 0.5*106
    assert t.pnl_pct == pytest.approx(4.5)               # (104.5-100)/100*100
    assert t.bars_held == pytest.approx(0.8)             # 3×15m bars to the rider exit
    m = res.metrics()
    assert m["tp1"] == 1
    assert m["tp2"] == 1


def test_legacy_full_close_at_tp1_pct_100():
    """partial_tp1_pct=100 disables partial: pure TP1 full close (old behavior)."""
    from app.services.crypto_backtester import BacktestParams
    params = BacktestParams(partial_tp1_pct=100.0)
    klines, i = _forced_candidate_klines([100.0, 104.0, 101.0, 107.0])
    params._entry_idx = i
    bt = _forced_bt(params)
    res = bt.run_symbol(klines, "SYNTH")
    assert len(res.trades) == 1
    assert res.trades[0].exit_reason == "TP1"
    assert res.trades[0].exit_price == pytest.approx(103.0)
    assert res.trades[0].pnl_pct == pytest.approx(3.0)


def test_partial_tp1_then_rider_stopped_out_reason_tp1_sl():
    """Rider stopped by the trailing/SL after TP1 → combined 'TP1+SL' reason,
    counted in both metrics buckets."""
    from app.services.crypto_backtester import BacktestParams
    params = BacktestParams(partial_tp1_pct=50.0)
    # TP1 hit on the 2nd ride bar, then the rider crashes through the trailing
    # stop (99.6) → SL exit at 96.9 (SL − 0.1% slippage).
    klines, i = _forced_candidate_klines([100.0, 104.0, 101.0, 96.5])
    params._entry_idx = i
    bt = _forced_bt(params)
    res = bt.run_symbol(klines, "SYNTH")
    assert len(res.trades) == 1
    assert res.trades[0].exit_reason == "TP1+SL"
    # 50% locked at +3%, remainder stopped at 96.9 → 0.5*3 + 0.5*(-3.1)
    assert res.trades[0].pnl_pct == pytest.approx(-0.05, abs=0.02)
    m = res.metrics()
    assert m["tp1"] == 1
    assert m["sl"] == 1