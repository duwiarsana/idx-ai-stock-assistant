"""Tests for deterministic price levels (entry / TP / SL)."""

import pytest

from app.services.crypto_indicators import compute_indicator_summary, candles_to_closes
from app.services.crypto_levels import compute_price_levels, PriceLevels
from tests.crypto_fixtures import make_candles_uptrend, make_candles


def test_uptrend_breakout_levels():
    candles = make_candles_uptrend()
    s = compute_indicator_summary(candles)
    levels = compute_price_levels({"1h": s}, candles)
    assert levels.is_complete()
    assert levels.take_profit_1 > levels.entry
    assert levels.take_profit_2 > levels.take_profit_1
    assert levels.stop_loss < levels.entry
    assert levels.risk_reward and levels.risk_reward > 0


def test_range_levels_target_recent_high():
    """Below the recent high → TP1 is the resistance high."""
    # Deterministic series: rises to ~110, then pulls back to ~100.
    closes = [100 + i * 0.4 for i in range(25)] + [110, 109, 108, 107, 106, 105, 104, 103, 102, 101, 100]
    candles = [
        {"openTime": i, "open": c - 0.5, "high": c + 1, "low": c - 1, "close": c, "volume": 1000.0}
        for i, c in enumerate(closes)
    ]
    s = compute_indicator_summary(candles)
    assert s["at_high"] is False
    recent_high = max(closes[:-1])
    levels = compute_price_levels({"1h": s}, candles)
    assert levels.is_complete()
    assert levels.take_profit_1 == pytest.approx(recent_high)
    assert levels.stop_loss < levels.entry
    assert levels.entry_note  # either support or EMA20 pullback note


def test_levels_no_crash_without_candles():
    s = {"price": 100.0, "atr": 2.0, "at_high": False}
    levels = compute_price_levels({"1h": s}, [])
    assert levels.entry == 100.0
    assert levels.is_complete()


def test_levels_no_price_returns_empty():
    levels = compute_price_levels({}, [])
    assert levels.entry is None
    assert not levels.is_complete()


def test_price_levels_dataclass_roundtrip():
    p = PriceLevels(entry=1.0, take_profit_1=1.1, take_profit_2=1.2, stop_loss=0.95, risk_reward=2.0)
    d = p.to_dict()
    assert d["entry"] == 1.0
    assert d["risk_reward"] == 2.0
    assert p.is_complete()