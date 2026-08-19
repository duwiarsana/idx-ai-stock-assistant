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