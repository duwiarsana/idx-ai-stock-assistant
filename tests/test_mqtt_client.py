"""Tests for the MQTT publisher (ESP32 sound alerts)."""

import asyncio

import pytest

from app.services.mqtt_client import MqttPublisher


def make_pos():
    class P:
        symbol = "WLD_USDT"
        display = "WLD/USDT"
        base = "WLD"
        quote = "USDT"
        entry_price = 0.3524
        quantity = 255391.6
        invested = 90000.0
        exit_reason = "TP1"
        status = "CLOSED"
    return P()


def make_account():
    class A:
        cash_balance = 708333.69
        realized_pnl = -1694.21
        total_trades = 7
        winning_trades = 3
    return A()


def make_publisher(monkeypatch, enabled=True):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "mqtt_enabled", enabled)
    monkeypatch.setattr(get_settings(), "mqtt_host", "localhost")
    monkeypatch.setattr(get_settings(), "mqtt_topic_prefix", "crypto/trade")
    return MqttPublisher()


@pytest.mark.asyncio
async def test_publish_disabled_returns_false(monkeypatch):
    p = make_publisher(monkeypatch, enabled=False)
    assert await p.publish("buy", {}) is False


@pytest.mark.asyncio
async def test_publish_builds_topic_and_payload(monkeypatch):
    p = make_publisher(monkeypatch)
    captured = {}

    class FakeClient:
        def __init__(self, **kw): captured["kw"] = kw
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def publish(self, topic, message, qos=0):
            captured["topic"] = topic
            captured["message"] = message

    import aiomqtt
    monkeypatch.setattr(aiomqtt, "Client", FakeClient)

    ok = await p.publish_buy(make_pos())
    assert ok is True
    assert captured["topic"] == "crypto/trade/buy"
    import json
    data = json.loads(captured["message"])
    assert data["event"] == "BUY"
    assert data["symbol"] == "WLD_USDT"
    assert data["display"] == "WLD/USDT"
    assert "ts" in data
    assert captured["kw"]["username"] is None  # no auth configured in test
    assert captured["kw"]["hostname"] == "localhost"


@pytest.mark.asyncio
async def test_profit_and_loss_topics(monkeypatch):
    p = make_publisher(monkeypatch)
    topics = []

    class FakeClient:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def publish(self, topic, message, qos=0):
            topics.append(topic)

    import aiomqtt
    monkeypatch.setattr(aiomqtt, "Client", FakeClient)

    pos = make_pos()
    assert await p.publish_profit(pos, 0.3565, 1045.0) is True
    assert await p.publish_loss(pos, 0.34, -3200.0) is True
    assert "crypto/trade/profit" in topics
    assert "crypto/trade/loss" in topics


@pytest.mark.asyncio
async def test_publish_failure_is_not_fatal(monkeypatch):
    p = make_publisher(monkeypatch)

    class BrokenClient:
        def __init__(self, **kw): pass
        async def __aenter__(self):
            raise ConnectionError("broker unreachable")
        async def __aexit__(self, *a): return False
        async def publish(self, *a, **k): pass

    import aiomqtt
    monkeypatch.setattr(aiomqtt, "Client", BrokenClient)

    ok = await p.publish_buy(make_pos())
    assert ok is False
    assert p.state["connected"] is False
    assert p.state["last_error"]


@pytest.mark.asyncio
async def test_payload_contains_pnl_percent(monkeypatch):
    p = make_publisher(monkeypatch)
    captured = {}

    class FakeClient:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def publish(self, topic, message, qos=0):
            captured["message"] = message

    import aiomqtt
    monkeypatch.setattr(aiomqtt, "Client", FakeClient)

    await p.publish_profit(make_pos(), 0.3565, 1045.0)
    import json
    data = json.loads(captured["message"])
    # 1045 / 90000 = 1.16%
    assert data["pnl_percent"] == pytest.approx(1.16, abs=0.01)
    assert data["exit_reason"] == "TP1"


@pytest.mark.asyncio
async def test_payload_contains_account_summary(monkeypatch):
    p = make_publisher(monkeypatch)
    captured = []

    class FakeClient:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def publish(self, topic, message, qos=0):
            captured.append((topic, message))

    import aiomqtt
    monkeypatch.setattr(aiomqtt, "Client", FakeClient)

    acc = make_account()
    await p.publish_buy(make_pos(), acc)
    await p.publish_loss(make_pos(), 0.34, -3200.0, acc)

    import json
    for topic, msg in captured:
        data = json.loads(msg)
        assert data["balance"] == pytest.approx(708333.69)
        assert data["realized_pnl"] == pytest.approx(-1694.21)
        assert data["total_trades"] == 7
        assert data["winning_trades"] == 3


@pytest.mark.asyncio
async def test_no_account_summary_when_account_none(monkeypatch):
    p = make_publisher(monkeypatch)
    captured = {}

    class FakeClient:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def publish(self, topic, message, qos=0):
            captured["message"] = message

    import aiomqtt
    monkeypatch.setattr(aiomqtt, "Client", FakeClient)

    await p.publish_buy(make_pos(), None)
    import json
    data = json.loads(captured["message"])
    assert "balance" not in data
    assert "realized_pnl" not in data