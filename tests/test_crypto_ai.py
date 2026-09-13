"""Tests for the AI verdict parsing + formatting helpers."""

import pytest

from app.services.crypto_ai import (
    AIVerdict,
    build_candidate_payload,
    parse_verdict,
    deterministic_fallback,
    _parse_batch,
    _trim_payloads,
)


def sample_candidate(score=85.0):
    closes_1h = [round(1.0 + i * 0.01, 6) for i in range(200)]
    closes_15m = [round(1.2 + i * 0.003, 6) for i in range(96)]
    return {
        "symbol": "SUI_USDT",
        "score": score,
        "price_change": {"1h": 3.2, "4h": 7.8, "24h": 9.0},
        "tf_summaries": {
            "5m": {"rsi": 63.0, "trend": "bullish"},
            "15m": {"rsi": 68.0, "trend": "bullish"},
            "1h": {
                "rsi": 55.0,
                "trend": "bullish",
                "macd_state": "bullish",
                "relative_volume": 2.7,
                "at_high": True,
                "price": 1.234,
                "atr_pct": 2.1,
            },
        },
        "score_breakdown": {"trend": 100.0, "momentum": 70.0, "volume": 80.0,
                            "breakout": 90.0, "risk_penalty": -10.0},
        "ticker": {"quoteVolume": 1_500_000.0},
        "series": {"1h": closes_1h, "15m": closes_15m},
        "price_levels": {
            "entry": 1.20, "take_profit_1": 1.33, "take_profit_2": 1.45,
            "stop_loss": 1.10, "risk_reward": 2.0,
        },
    }


def test_parse_verdict_single_json():
    raw = '{"symbol": "SUI_USDT", "verdict": "WATCH", "confidence": 78, "risk": "LOW", "reason": ["a"], "warning": ""}'
    v = parse_verdict(raw, "SUI_USDT")
    assert v.verdict == "WATCH"
    assert v.confidence == 78
    assert v.risk == "LOW"
    assert v.symbol == "SUI_USDT"


def test_parse_verdict_markdown_fences():
    raw = '```json\n{"symbol": "SUI_USDT", "verdict": "STRONG_WATCH", "confidence": 90, "risk": "LOW", "reason": ["x"], "warning": ""}\n```'
    v = parse_verdict(raw)
    assert v.verdict == "STRONG_WATCH"


def test_parse_verdict_with_leading_text():
    raw = 'Here you go:\n{"symbol": "SUI_USDT", "verdict": "AVOID", "confidence": 30, "risk": "HIGH", "reason": ["a", "b"], "warning": "danger"}'
    v = parse_verdict(raw)
    assert v.verdict == "AVOID"
    assert v.risk == "HIGH"
    assert v.warning == "danger"


def test_parse_verdict_unparseable():
    v = parse_verdict("total garbage", "SUI_USDT")
    assert v.verdict == "NEUTRAL"
    assert v.reason == ["AI response unparseable"]


def test_parse_verdict_invalid_verdict_falls_back_neutral():
    raw = '{"symbol": "X", "verdict": "BUY", "confidence": 99, "risk": "LOW", "reason": [], "warning": ""}'
    v = parse_verdict(raw)
    assert v.verdict == "NEUTRAL"  # BUY not allowed


def test_parse_verdict_clamps_confidence():
    raw = '{"symbol": "X", "verdict": "WATCH", "confidence": 500, "risk": "LOW", "reason": [], "warning": ""}'
    v = parse_verdict(raw)
    assert v.confidence == 100


def test_parse_batch_array():
    raw = """```json
    [
      {"symbol": "SUI_USDT", "verdict": "WATCH", "confidence": 70, "risk": "MEDIUM", "reason": ["a"], "warning": ""},
      {"symbol": "SOL_USDT", "verdict": "AVOID", "confidence": 25, "risk": "HIGH", "reason": ["b"], "warning": "x"}
    ]
    ```"""
    out = _parse_batch(raw, [])
    assert set(out) == {"SUI_USDT", "SOL_USDT"}
    assert out["SOL_USDT"].verdict == "AVOID"


def test_deterministic_fallback_high_score():
    v = deterministic_fallback(sample_candidate(score=88))
    assert v.verdict == "STRONG_WATCH"
    assert v.confidence > 80


def test_deterministic_fallback_low_score():
    v = deterministic_fallback(sample_candidate(score=40))
    assert v.verdict == "AVOID"


def test_build_candidate_payload_no_crash():
    payload = build_candidate_payload(sample_candidate())
    d = payload.to_dict()
    assert d["symbol"] == "SUI_USDT"
    assert d["score"] == 85.0
    assert d["breakout"] is True
    assert d["volatility"] == "medium"  # atr_pct 2.1 → medium


def test_build_candidate_payload_carries_candle_series():
    d = build_candidate_payload(sample_candidate()).to_dict()
    assert len(d["candles_1h"]) == 200
    assert len(d["candles_15m"]) == 96
    # newest close last (canary on ordering upstream)
    assert d["candles_1h"][-1] > d["candles_1h"][0]
    # all closes are plain floats
    assert all(isinstance(x, float) and x == round(x, 6) for x in d["candles_1h"])


def test_build_candidate_payload_backcompat_without_series():
    c = sample_candidate()
    c.pop("series")
    d = build_candidate_payload(c).to_dict()
    assert d["candles_1h"] == []
    assert d["candles_15m"] == []
    assert d["scoreBreakdown"]["trend"] == 100.0
    assert d["volume24h"] == 1_500_000.0
    assert d["entry"] == 1.20


def test_trim_payloads_under_budget_unchanged():
    d = build_candidate_payload(sample_candidate()).to_dict()
    payloads = [d.copy()]
    out = _trim_payloads(payloads)
    assert len(out[0]["candles_1h"]) == 200
    assert len(out[0]["candles_15m"]) == 96


def test_trim_payloads_shrinks_when_over_budget(monkeypatch):
    monkeypatch.setattr("app.services.crypto_ai._MAX_BATCH_CHARS", 500)
    d = build_candidate_payload(sample_candidate()).to_dict()
    payloads = [d.copy() for _ in range(3)]
    out = _trim_payloads(payloads)
    # over budget → 15m dropped first
    assert "candles_15m" not in out[0]
    # still over budget → 1h trimmed to last 100
    assert len(out[0]["candles_1h"]) == 100
    assert out[0]["scoreBreakdown"]["trend"] == 100.0  # indicators never dropped


def test_ai_verdict_never_raises_on_weird_types():
    raw = '{"symbol": "X", "verdict": 123, "confidence": "abc", "risk": null, "reason": "just a string", "warning": null}'
    v = parse_verdict(raw)
    assert v.verdict == "NEUTRAL"
    assert v.confidence == 50
    assert v.risk == "MEDIUM"
    assert v.reason == ["just a string"]
