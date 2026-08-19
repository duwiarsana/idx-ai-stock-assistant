"""Tests for deterministic technical indicators."""

import math

import pytest

from app.services.crypto_indicators import (
    ema,
    sma,
    ema_series,
    rsi,
    macd,
    average_true_range,
    volume_ma,
    relative_volume,
    price_change_percent,
    recent_high,
    breakout_progress,
    volatility,
    candles_to_closes,
    candles_to_volumes,
    compute_indicator_summary,
)
from tests.crypto_fixtures import make_candles, make_candles_uptrend, make_candles_downtrend


def test_sma():
    values = [1.0, 2.0, 3.0, 4.0]
    assert sma(values, 2) == pytest.approx(3.5)
    assert sma(values, 4) == pytest.approx(2.5)
    assert sma(values, 5) is None


def test_ema_basic():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    result = ema(values, 3)
    assert result > 0
    assert abs(result - ema(values, 3)) < 1e-9  # deterministic


def test_ema_shortage():
    assert ema([1.0, 2.0], 5) is None


def test_ema_series_length():
    values = list(range(1, 21))
    out = ema_series(values, 5)
    assert len(out) == 20
    assert out[-1] == ema(values, 5)


def test_rsi_range():
    values = [100 + math.sin(i / 3) * 10 for i in range(100)]
    result = rsi(values)
    assert 0 <= result <= 100


def test_rsi_overbought():
    """Persistent gains → RSI high."""
    values = [100 + i * 2 for i in range(50)]
    assert rsi(values) > 70


def test_rsi_oversold():
    values = [1000 - i * 2 for i in range(50)]
    assert rsi(values) < 30


def test_macd_bullish():
    # Exponential growth → fast EMA above slow EMA, MACD above signal.
    values = [100 * 1.01 ** i for i in range(60)]
    macd_state = macd(values)
    assert macd_state["macd"] > macd_state["signal"]
    assert macd_state["histogram"] > 0


def test_macd_bearish():
    # Accelerating decline → fast EMA below slow EMA, MACD below signal.
    values = [100 - i ** 1.5 for i in range(60)]
    macd_state = macd(values)
    assert macd_state["macd"] < macd_state["signal"]


def test_average_true_range_positive():
    candles = make_candles(n=50)
    atr = average_true_range(candles, 14)
    assert atr > 0
    assert isinstance(atr, float)


def test_volume_ma():
    volumes = [float(i + 1) for i in range(20)]
    assert volume_ma(volumes, 10) == pytest.approx(sum(volumes[10:]) / 10)


def test_relative_volume():
    # 20 values of 100, then a 300 spike (window includes the spike: avg = 110).
    volumes = [100.0] * 20 + [300.0]
    assert relative_volume(volumes, 20) == pytest.approx(300.0 / 110.0)


def test_price_change_percent():
    closes = [100.0, 101.0, 102.0, 103.0]
    assert price_change_percent(closes, 1) == pytest.approx((103 - 102) / 102 * 100)
    assert price_change_percent(closes, 3) == pytest.approx(3.0)
    assert price_change_percent(closes, 10) is None  # insufficient history


def test_recent_high():
    closes = [10, 12, 11, 9]
    assert recent_high(closes) == 12.0


def test_breakout_progress():
    # recent high = 12 (max of [10,11,12], excluding last), price 13 above it.
    closes = [10, 11, 12, 13]
    res = breakout_progress(closes)
    assert res["at_high"] is True
    assert res["distance_from_high"] is not None
    assert res["distance_from_high"] > 0  # above the recent high


def test_breakout_below_high():
    # price 9 below recent high 12 → negative distance, not at_high.
    closes = [10, 11, 12, 9]
    res = breakout_progress(closes)
    assert res["at_high"] is False
    assert res["distance_from_high"] < 0


def test_breakout_at_high():
    closes = [10, 11, 9, 12]
    res = breakout_progress(closes)
    assert res["at_high"] is True


def test_volatility_nonnegative():
    closes = candles_to_closes(make_candles(n=50))
    assert volatility(closes) >= 0


def test_candles_to_closes_volumes():
    candles = make_candles(n=10)
    closes = candles_to_closes(candles)
    volumes = candles_to_volumes(candles)
    assert len(closes) == 10
    assert len(volumes) == 10
    assert closes[0] == candles[0]["close"]
    assert volumes[0] == candles[0]["volume"]


def test_summary_uptrend():
    candles = make_candles_uptrend()
    s = compute_indicator_summary(candles)
    assert s["price"] == candles[-1]["close"]
    assert s["trend"] == "bullish"
    assert s["rsi"] is not None
    assert s["macd_state"] in ("bullish", "bearish", "neutral")
    assert s["atr_pct"] > 0
    assert s["relative_volume"] > 0
    assert s["volatility"] >= 0
    assert s["candles"] == len(candles)


def test_summary_downtrend():
    candles = make_candles_downtrend()
    s = compute_indicator_summary(candles)
    assert s["trend"] == "bearish"


def test_summary_short_input():
    s = compute_indicator_summary(make_candles(n=10))
    # Short input should still produce a dict without crashing; indicators may be None.
    assert isinstance(s, dict)
