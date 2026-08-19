"""Tests for the crypto Telegram alert formatter + anti-spam gate."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.services.crypto_alert import (
    format_alert_message,
    should_alert,
    send_crypto_alert,
    _alert_payload,
    SCORE_IMPROVEMENT_THRESHOLD,
    ALERT_KEY_PREFIX,
)


def sample_candidate(score=85.0, at_high=True):
    return {
        "symbol": "SUI_USDT",
        "display": "SUI/USDT",
        "quote": "USDT",
        "score": score,
        "price_change": {"1h": 3.2, "4h": 7.8, "24h": 9.0},
        "tf_summaries": {
            "5m": {"trend": "bullish", "rsi": 63.0},
            "15m": {"trend": "bullish", "rsi": 68.0},
            "1h": {
                "trend": "bullish",
                "rsi": 55.0,
                "relative_volume": 2.7,
                "at_high": at_high,
                "price": 1.234,
            },
        },
        "price_levels": {
            "entry": 1.234,
            "take_profit_1": 1.30,
            "take_profit_2": 1.36,
            "stop_loss": 1.18,
            "risk_reward": 2.0,
            "entry_note": "Breakout — entry di harga pasar",
        },
    }


def sample_verdict():
    return {
        "verdict": "WATCH",
        "confidence": 81,
        "risk": "MEDIUM",
        "reason": ["Trend 1H bullish", "Volume 2.7x average"],
        "warning": "RSI high",
    }


def test_format_alert_message_contains_key_parts():
    msg = format_alert_message(sample_candidate(), sample_verdict())
    assert "SUI/USDT" in msg
    assert "85" in msg  # score
    assert "81%" in msg  # confidence
    assert "+3.2%" in msg
    assert "+7.8%" in msg
    assert "2.7x" in msg
    assert "Trend 1H bullish" in msg
    assert "not financial advice" in msg
    assert "🚨" in msg
    # Price levels block
    assert "Level Harga" in msg
    assert "Entry" in msg
    assert "TP1" in msg
    assert "TP2" in msg
    assert "SL" in msg
    assert "1.30" in msg
    assert "1.18" in msg
    assert "1:2" in msg  # risk/reward


def test_format_alert_message_missing_optional_fields():
    candidate = {"symbol": "SOL_USDT", "display": "SOL/USDT", "quote": "USDT", "score": 60.0, "tf_summaries": {}}
    msg = format_alert_message(candidate, {})
    assert "SOL/USDT" in msg
    assert "60" in msg


def test_format_alert_message_ai_unavailable_note():
    verdict = dict(sample_verdict(), warning="AI analysis unavailable; based on technical score only.")
    msg = format_alert_message(sample_candidate(), verdict)
    assert "AI analysis unavailable" in msg


def test_alert_payload_shape():
    p = _alert_payload(sample_candidate())
    assert p["symbol"] == "SUI_USDT"
    assert p["score"] == 85.0
    assert p["at_high"] is True
    assert "sent_at" in p


def test_cooldown_ttl_fits_int_range():
    """Cooldown in seconds must be a valid int (Redis TTL)."""
    from app.config import get_settings
    cooldown_min = get_settings().crypto_alert_cooldown_minutes
    assert isinstance(cooldown_min, int)
    assert 0 < cooldown_min <= 24 * 60  # sane range


class FakeRedis:
    """In-memory stand-in for cache_service.redis (setex/get/delete)."""

    def __init__(self):
        self.store = {}

    async def setex(self, key, ttl, value):
        self.store[key] = value

    async def get(self, key):
        return self.store.get(key)


@pytest.fixture
def fake_redis(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr("app.services.crypto_alert.cache_service.redis", redis)
    return redis


@pytest.mark.asyncio
async def test_should_alert_first_time(monkeypatch):
    class NoRedis:
        async def get(self, key):
            return None

    monkeypatch.setattr("app.services.crypto_alert.cache_service.redis", NoRedis())
    ok, reason = await should_alert(sample_candidate())
    assert ok is True
    assert reason == "first alert"


@pytest.mark.asyncio
async def test_should_alert_cooldown_active(fake_redis):
    # Store a recent alert for the same symbol.
    await fake_redis.setex(
        f"{ALERT_KEY_PREFIX}SUI_USDT",
        3600,
        json.dumps(_alert_payload(sample_candidate())),
    )
    ok, reason = await should_alert(sample_candidate())
    assert ok is False
    assert "cooldown" in reason


@pytest.mark.asyncio
async def test_should_alert_cooldown_expired(fake_redis):
    payload = _alert_payload(sample_candidate())
    payload["sent_at"] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    await fake_redis.setex(f"{ALERT_KEY_PREFIX}SUI_USDT", 3600, json.dumps(payload))
    ok, reason = await should_alert(sample_candidate())
    assert ok is True
    assert reason == "cooldown expired"


@pytest.mark.asyncio
async def test_should_alert_score_improved(fake_redis):
    old = _alert_payload(sample_candidate(score=60.0))
    old["sent_at"] = datetime.now(timezone.utc).isoformat()
    await fake_redis.setex(f"{ALERT_KEY_PREFIX}SUI_USDT", 3600, json.dumps(old))
    ok, reason = await should_alert(sample_candidate(score=60.0 + SCORE_IMPROVEMENT_THRESHOLD + 1))
    assert ok is True
    assert "improved" in reason


@pytest.mark.asyncio
async def test_should_alert_new_breakout(fake_redis):
    old = _alert_payload(sample_candidate(at_high=False))
    old["sent_at"] = datetime.now(timezone.utc).isoformat()
    await fake_redis.setex(f"{ALERT_KEY_PREFIX}SUI_USDT", 3600, json.dumps(old))
    ok, reason = await should_alert(sample_candidate(at_high=True))
    assert ok is True
    assert reason == "new breakout"


@pytest.mark.asyncio
async def test_send_crypto_alert_dry_run(monkeypatch, fake_redis, caplog):
    import logging
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "crypto_scanner_dry_run", True)
    monkeypatch.setattr(settings, "telegram_bot_token", "fake-token")
    monkeypatch.setattr(settings, "telegram_chat_id", "123")

    with caplog.at_level(logging.INFO):
        res = await send_crypto_alert(sample_candidate(), sample_verdict())

    assert res["sent"] is True
    assert res["dry_run"] is True
    assert "DRY-RUN" in caplog.text


@pytest.mark.asyncio
async def test_send_crypto_alert_no_credentials(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "crypto_scanner_dry_run", False)
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    monkeypatch.setattr(settings, "telegram_chat_id", "")

    res = await send_crypto_alert(sample_candidate(), sample_verdict())
    assert res["sent"] is False
    assert "not configured" in res["reason"]


@pytest.mark.asyncio
async def test_send_crypto_alert_disabled_via_setting(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "crypto_scanner_dry_run", False)
    monkeypatch.setattr(settings, "crypto_alert_telegram_enabled", False)
    monkeypatch.setattr(settings, "telegram_bot_token", "fake-token")
    monkeypatch.setattr(settings, "telegram_chat_id", "123")

    res = await send_crypto_alert(sample_candidate(), sample_verdict())
    assert res["sent"] is False
    assert "disabled" in res["reason"]
