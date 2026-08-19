"""Deterministic technical indicators for crypto pairs.

All functions are pure and operate on plain OHLCV dict lists (see
``app.data.tokocrypto_client`` for the canonical shape). No LLM is involved
here — these calculations are fully reproducible.
"""

import logging
import math
from typing import Optional

logger = logging.getLogger(__name__)


def ema(values: list[float], period: int) -> Optional[float]:
    """Exponential moving average of the last value."""
    if not values or period <= 0:
        return None
    if len(values) < period:
        return None
    k = 2.0 / (period + 1)
    result = float(sum(values[:period]) / period)
    for val in values[period:]:
        result = val * k + result * (1 - k)
    return result


def sma(values: list[float], period: int) -> Optional[float]:
    """Simple moving average of the last value."""
    if len(values) < period or period <= 0:
        return None
    return float(sum(values[-period:]) / period)


def ema_series(values: list[float], period: int) -> list[Optional[float]]:
    """Return full EMA series (None until enough data)."""
    if not values or period <= 0:
        return [None] * len(values)
    out: list[Optional[float]] = [None] * len(values)
    if len(values) < period:
        return out
    k = 2.0 / (period + 1)
    result = float(sum(values[:period]) / period)
    out[period - 1] = result
    for i in range(period, len(values)):
        result = values[i] * k + result * (1 - k)
        out[i] = result
    return out


def rsi(closes: list[float], period: int = 14) -> Optional[float]:
    """Relative Strength Index (Wilder smoothing) of the last value."""
    if len(closes) <= period:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def macd(
    closes: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict[str, Optional[float]]:
    """MACD, signal line, and histogram of the last value."""
    fast_series = ema_series(closes, fast)
    slow_series = ema_series(closes, slow)

    macd_line: list[float] = []
    for f, s in zip(fast_series, slow_series):
        if f is not None and s is not None:
            macd_line.append(f - s)
        else:
            macd_line.append(math.nan)

    clean = [v for v in macd_line if not math.isnan(v)]
    if len(clean) < signal:
        return {"macd": None, "signal": None, "histogram": None}

    signal_series = ema_series(clean, signal)
    macd_val = macd_line[-1]
    signal_val = signal_series[-1]
    if macd_val is None or signal_val is None:
        return {"macd": None, "signal": None, "histogram": None}
    return {
        "macd": macd_val,
        "signal": signal_val,
        "histogram": macd_val - signal_val,
    }


def average_true_range(candles: list[dict], period: int = 14) -> Optional[float]:
    """Average True Range of the last value (uses open/high/low/close)."""
    if len(candles) <= period:
        return None
    trs: list[float] = []
    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        prev_close = candles[i - 1]["close"]
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    atr = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        atr = (atr * (period - 1) + trs[i]) / period
    return atr


def volume_ma(volumes: list[float], period: int = 20) -> Optional[float]:
    """Simple moving average of volumes."""
    return sma(volumes, period)


def relative_volume(volumes: list[float], period: int = 20) -> Optional[float]:
    """Last volume / average volume (spike factor)."""
    avg = volume_ma(volumes, period)
    if not avg or avg <= 0 or not volumes:
        return None
    return float(volumes[-1] / avg)


def price_change_percent(closes: list[float], lookback: int = 1) -> Optional[float]:
    """Percent change over ``lookback`` candles."""
    if len(closes) <= lookback:
        return None
    prev = closes[-1 - lookback]
    if prev == 0:
        return None
    return ((closes[-1] - prev) / prev) * 100.0


def recent_high(closes: list[float], lookback: int = 24) -> Optional[float]:
    """Highest close over the lookback window (excluding last bar optional)."""
    if not closes:
        return None
    window = closes[-lookback:-1] if lookback < len(closes) else closes[:-1]
    if not window:
        return None
    return max(window)


def recent_low(closes: list[float], lookback: int = 24) -> Optional[float]:
    """Lowest close over the lookback window (excluding last bar)."""
    if not closes:
        return None
    window = closes[-lookback:-1] if lookback < len(closes) else closes[:-1]
    if not window:
        return None
    return min(window)


def breakout_progress(closes: list[float], lookback: int = 24) -> dict[str, Optional[float]]:
    """How close the price is to the recent high, plus breakout flag.

    Returns:
        distance_from_high: percent below recent high (0.0 = at high, negative = above).
        at_high: True when price >= recent high.
    """
    high = recent_high(closes, lookback)
    if high is None or not closes:
        return {"distance_from_high": None, "at_high": False}
    last = closes[-1]
    distance = ((last - high) / high) * 100.0 if high else None
    return {"distance_from_high": distance, "at_high": bool(high and last >= high)}


def volatility(closes: list[float], period: int = 20) -> Optional[float]:
    """Annualised-ish volatility proxy: std of log returns over the window."""
    if len(closes) < period + 1:
        return None
    returns = []
    for i in range(len(closes) - period, len(closes)):
        prev = closes[i - 1]
        if prev > 0:
            returns.append(math.log(closes[i] / prev))
    if not returns:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(period)  # scaled to window


def candles_to_closes(candles: list[dict]) -> list[float]:
    return [float(c["close"]) for c in candles]


def candles_to_volumes(candles: list[dict]) -> list[float]:
    return [float(c["volume"]) for c in candles]


def compute_indicator_summary(candles: list[dict]) -> dict:
    """Compute the full indicator summary for a candle series."""
    closes = candles_to_closes(candles)
    volumes = candles_to_volumes(candles)

    ema9 = ema(closes, 9)
    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)
    rsi14 = rsi(closes, 14)
    macd_res = macd(closes)
    vol_ma20 = volume_ma(volumes, 20)
    rel_vol = relative_volume(volumes, 20)
    breakout = breakout_progress(closes, 24)
    atr = average_true_range(candles, 14)
    last_close = closes[-1] if closes else None

    # EMA alignment / trend
    trend = "neutral"
    if ema9 is not None and ema20 is not None and ema50 is not None:
        if ema9 > ema20 > ema50:
            trend = "bullish"
        elif ema9 < ema20 < ema50:
            trend = "bearish"

    macd_state = "neutral"
    if macd_res.get("histogram") is not None:
        if macd_res["histogram"] > 0 and macd_res["macd"] and macd_res["macd"] > 0:
            macd_state = "bullish"
        elif macd_res["histogram"] < 0 and macd_res["macd"] and macd_res["macd"] < 0:
            macd_state = "bearish"

    return {
        "price": last_close,
        "ema9": ema9,
        "ema20": ema20,
        "ema50": ema50,
        "rsi": rsi14,
        "macd": macd_res.get("macd"),
        "macd_signal": macd_res.get("signal"),
        "macd_histogram": macd_res.get("histogram"),
        "macd_state": macd_state,
        "volume_ma": vol_ma20,
        "relative_volume": rel_vol,
        "atr": atr,
        "atr_pct": (atr / last_close * 100.0) if atr and last_close else None,
        "trend": trend,
        "distance_from_high": breakout["distance_from_high"],
        "at_high": breakout["at_high"],
        "volatility": volatility(closes, 20),
        "candles": len(candles),
    }
