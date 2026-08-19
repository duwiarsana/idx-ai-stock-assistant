"""Tests for the momentum scoring engine."""

import pytest

from app.services.crypto_indicators import compute_indicator_summary
from app.services.crypto_scoring import (
    ScoreBreakdown,
    compute_momentum_score,
    _clamp,
)
from tests.crypto_fixtures import make_candles_uptrend, make_candles_downtrend


def build_summaries(uptrend=True, rv=1.5, closes_5m=None):
    """Build per-timeframe summaries from synthetic candles."""
    if uptrend:
        base = make_candles_uptrend()
    else:
        base = make_candles_downtrend()
    s1h = compute_indicator_summary(base)
    s15 = compute_indicator_summary(base)
    s5 = compute_indicator_summary(closes_5m or base)
    # Force a healthy relative volume so the volume component isn't null.
    for s in (s1h, s15, s5):
        s["relative_volume"] = rv
    return {"5m": s5, "15m": s15, "1h": s1h}


def test_score_range():
    summaries = build_summaries(uptrend=True)
    score, breakdown = compute_momentum_score(summaries, {"1h": 2.0})
    assert 0 <= score <= 100
    assert isinstance(breakdown, ScoreBreakdown)


def test_score_breakdown_keys():
    summaries = build_summaries(uptrend=True)
    score, breakdown = compute_momentum_score(summaries, {"1h": 2.0})
    d = breakdown.to_dict()
    for key in ("trend", "momentum", "volume", "breakout", "risk_penalty"):
        assert key in d


def test_uptrend_scores_higher_than_downtrend():
    up = build_summaries(uptrend=True, rv=2.0)
    down = build_summaries(uptrend=False, rv=0.6)
    score_up, _ = compute_momentum_score(up, {"1h": 3.0})
    score_down, _ = compute_momentum_score(down, {"1h": -3.0})
    assert score_up > score_down


def test_score_is_deterministic():
    summaries = build_summaries(uptrend=True)
    s1, b1 = compute_momentum_score(summaries, {"1h": 2.0})
    s2, b2 = compute_momentum_score(summaries, {"1h": 2.0})
    assert s1 == s2
    assert b1.to_dict() == b2.to_dict()


def test_risk_penalty_for_pump():
    summaries = build_summaries(uptrend=True, rv=3.0)
    # A big 1h pump triggers the pump & dump risk penalty.
    score, breakdown = compute_momentum_score(
        summaries, {"1h": 28.0, "4h": 40.0, "24h": 60.0}
    )
    assert breakdown.risk_penalty < 0


def test_weights_override():
    summaries = build_summaries(uptrend=True)
    default_score, _ = compute_momentum_score(summaries, {"1h": 2.0})
    custom_score, _ = compute_momentum_score(
        summaries, {"1h": 2.0}, weights={"trend": 1.0, "momentum": 0.0, "volume": 0.0, "breakout": 0.0}
    )
    # With trend dominating, the score is very high for an uptrend.
    assert custom_score > default_score


def test_clamp():
    assert _clamp(150, 0, 100) == 100
    assert _clamp(-5, 0, 100) == 0
    assert _clamp(50, 0, 100) == 50


def test_empty_summaries():
    score, breakdown = compute_momentum_score({}, {})
    assert 0 <= score <= 100
    assert breakdown.risk_penalty <= 0
