"""Crypto momentum scoring engine (0-100) with reproducible breakdown.

The score is computed purely in code — no LLM involvement. Weights live in
``Settings`` (``crypto_weight_*``) so they can be tuned without code changes.

Score = trend + momentum + volume + breakout - risk_penalty, clamped to [0,100].
Each positive component is a 0-1 fraction multiplied by its weight (weights sum
to 1), then scaled to a 100-point scale. The risk penalty subtracts directly.
"""

import logging
from dataclasses import dataclass, field, asdict
from typing import Optional

from app.config import get_settings
from app.services.crypto_indicators import compute_indicator_summary, price_change_percent

logger = logging.getLogger(__name__)
settings = get_settings()


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _rsi_bullish(rsi: Optional[float]) -> float:
    """RSI contribution: bullish zone (50-65) is ideal; overbought (>75) penalised."""
    if rsi is None:
        return 0.5
    if rsi <= 45:
        return _clamp((rsi - 30) / 15.0)  # 30→0, 45→1
    if rsi <= 65:
        return 1.0
    if rsi <= 80:
        return 1.0 - (rsi - 65) / 15.0 * 0.8
    return 0.0


@dataclass
class ScoreBreakdown:
    trend: float = 0.0
    momentum: float = 0.0
    volume: float = 0.0
    breakout: float = 0.0
    risk_penalty: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def compute_momentum_score(
    tf_summaries: dict[str, dict],
    price_change: dict[str, Optional[float]],
    weights: Optional[dict] = None,
) -> tuple[float, ScoreBreakdown]:
    """Compute the momentum score for a pair from per-timeframe summaries.

    Args:
        tf_summaries: ``{"5m": summary, "15m": summary, "1h": summary}`` where
            each summary comes from ``compute_indicator_summary``.
        price_change: ``{"1h": ..., "4h": ..., "24h": ...}`` percent changes.
        weights: optional override dict for trend/momentum/volume/breakout.

    Returns:
        ``(score, breakdown)`` with score in [0, 100].
    """
    weights = weights or {
        "trend": settings.crypto_weight_trend,
        "momentum": settings.crypto_weight_momentum,
        "volume": settings.crypto_weight_volume,
        "breakout": settings.crypto_weight_breakout,
    }
    wsum = sum(max(w, 0) for w in weights.values()) or 1.0

    tf_1h = tf_summaries.get("1h") or {}
    tf_15m = tf_summaries.get("15m") or {}
    tf_5m = tf_summaries.get("5m") or {}

    # ── Trend (1h primary) ─────────────────────────────────────────────
    trend_score = 0.0
    if tf_1h.get("trend") == "bullish":
        trend_score += 0.55
    elif tf_1h.get("trend") == "bearish":
        trend_score += 0.0
    else:
        trend_score += 0.25
    # Price above EMAs on 1h
    price = tf_1h.get("price")
    if price is not None:
        above = 0
        for key in ("ema9", "ema20", "ema50"):
            val = tf_1h.get(key)
            if val is not None and price > val:
                above += 1
        trend_score += above / 3.0 * 0.45  # up to +0.45

    # ── Momentum (5m + 15m + 1h blend) ────────────────────────────────
    mom_5m = _rsi_bullish(tf_5m.get("rsi")) if tf_5m else 0.5
    mom_15m = _rsi_bullish(tf_15m.get("rsi")) if tf_15m else 0.5
    mom_1h = _rsi_bullish(tf_1h.get("rsi")) if tf_1h else 0.5

    macd_5m = 1.0 if tf_5m.get("macd_state") == "bullish" else (0.3 if tf_5m else 0.5)
    macd_15m = 1.0 if tf_15m.get("macd_state") == "bullish" else (0.3 if tf_15m else 0.5)
    macd_1h = 1.0 if tf_1h.get("macd_state") == "bullish" else (0.3 if tf_1h else 0.5)

    # Confirmation weighting: 5m=momentum, 15m=confirmation, 1h=trend.
    momentum_score = (
        mom_5m * 0.20 + macd_5m * 0.10
        + mom_15m * 0.20 + macd_15m * 0.10
        + mom_1h * 0.25 + macd_1h * 0.15
    )

    # Positive price momentum on 1h (up to +0.1)
    pc1h = (price_change or {}).get("1h")
    if pc1h is not None:
        momentum_score += _clamp(pc1h / 10.0, 0, 0.1)

    # ── Volume (5m/15m relative volume) ───────────────────────────────
    rv_5m = tf_5m.get("relative_volume")
    rv_15m = tf_15m.get("relative_volume")
    rv_1h = tf_1h.get("relative_volume")
    rv_base = 0.35
    if rv_1h:
        rv_base += _clamp((rv_1h - 1.0) / 2.0) * 0.3
    if rv_15m:
        rv_base += _clamp((rv_15m - 1.0) / 2.0) * 0.2
    if rv_5m:
        rv_base += _clamp((rv_5m - 1.0) / 2.0) * 0.15
    volume_score = _clamp(rv_base, 0, 1)

    # ── Breakout (24h resistance proximity + volume confirmation) ─────
    breakout_score = 0.0
    dist_1h = tf_1h.get("distance_from_high")
    if dist_1h is not None:
        if tf_1h.get("at_high"):
            breakout_score += 0.6
        else:
            # distance_from_high is negative below the high; score only when
            # the price is within ~2% of the recent high (approaching resistance).
            proximity = _clamp(1.0 + dist_1h / 2.0, 0, 1)
            breakout_score += proximity * 0.5
    if rv_1h and rv_1h >= 1.5:
        breakout_score += 0.4  # breakout confirmed by volume
    elif rv_1h and rv_1h >= 1.0:
        breakout_score += 0.2

    # ── Risk penalty ──────────────────────────────────────────────────
    penalty = 0.0
    rsi_5m = tf_5m.get("rsi")
    rsi_15m = tf_15m.get("rsi")
    rsi_1h = tf_1h.get("rsi")

    # Overbought RSI
    for r in (rsi_5m, rsi_15m, rsi_1h):
        if r is not None and r >= 80:
            penalty += 0.10
        elif r is not None and r >= 72:
            penalty += 0.05

    # Extreme pump (1h price change too high → possible pump & dump)
    if pc1h is not None:
        if pc1h > 25:
            penalty += 0.10
        elif pc1h > 15:
            penalty += 0.05

    # Price too far from EMA50 (extended)
    if tf_1h.get("ema50") and tf_1h.get("price"):
        ext = (tf_1h["price"] - tf_1h["ema50"]) / tf_1h["ema50"]
        if ext > 0.20:
            penalty += 0.10
        elif ext > 0.10:
            penalty += 0.05

    # Abnormal volatility (ATR %)
    atr_pct = tf_1h.get("atr_pct")
    if atr_pct and atr_pct > 8:
        penalty += 0.08
    elif atr_pct and atr_pct > 5:
        penalty += 0.04

    # Thin volume
    if rv_1h is not None and rv_1h < 0.5:
        penalty += 0.10

    penalty = _clamp(penalty, 0, 0.6)

    # ── Combine (weights normalized to sum 1) ─────────────────────────
    raw = (
        trend_score * weights["trend"]
        + momentum_score * weights["momentum"]
        + volume_score * weights["volume"]
        + breakout_score * weights["breakout"]
    ) / wsum
    raw -= penalty * 0.25  # penalty scaled so it bites but doesn't dominate

    breakdown = ScoreBreakdown(
        trend=round(trend_score * 100, 2),
        momentum=round(momentum_score * 100, 2),
        volume=round(volume_score * 100, 2),
        breakout=round(breakout_score * 100, 2),
        risk_penalty=round(-penalty * 100, 2),
    )

    score = round(max(0.0, min(100.0, raw * 100)), 2)
    return score, breakdown
