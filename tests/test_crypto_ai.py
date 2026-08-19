"""Tests for the AI verdict parsing + formatting helpers."""

import pytest

from app.services.crypto_ai import (
    AIVerdict,
    build_candidate_payload,
    parse_verdict,
    deterministic_fallback,
    _parse_batch,
)


def sample_candidate(score=85.0):
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


def test_ai_verdict_never_raises_on_weird_types():
    raw = '{"symbol": "X", "verdict": 123, "confidence": "abc", "risk": null, "reason": "just a string", "warning": null}'
    v = parse_verdict(raw)
    assert v.verdict == "NEUTRAL"
    assert v.confidence == 50
    assert v.risk == "MEDIUM"
    assert v.reason == ["just a string"]
