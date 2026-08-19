"""Tests for the /crypto Telegram handler (dispatcher, status, scan, alerts)."""

import asyncio

import pytest

from app.bot.handlers.crypto import (
    crypto_handler,
    CRYPTO_HELP_MESSAGE,
    _status_emoji,
)


class FakeChat:
    def __init__(self):
        self.actions = []

    async def send_action(self, action):
        self.actions.append(action)


class FakeMessage:
    def __init__(self):
        self.chat = FakeChat()
        self.sent = []
        self.deleted = False

    async def reply_text(self, text, parse_mode=None):
        self.sent.append({"text": text, "parse_mode": parse_mode})
        return self

    async def delete(self):
        self.deleted = True


class FakeUser:
    id = 5994671522


class FakeUpdate:
    def __init__(self, message, user=None):
        self.message = message
        self.effective_user = user or FakeUser()
        self.update_id = 1


class FakeContext:
    def __init__(self, args=None):
        self.args = args or []


def make_update_and_context(args=None):
    msg = FakeMessage()
    return FakeUpdate(msg), FakeContext(args), msg


@pytest.mark.asyncio
async def test_status_no_scan_yet(monkeypatch):
    update, context, msg = make_update_and_context()
    monkeypatch.setattr("app.bot.handlers.crypto.crypto_scanner", FakeScanner(state={}))
    await crypto_handler(update, context)
    assert len(msg.sent) == 1
    assert "belum pernah" in msg.sent[0]["text"]
    assert "CRYPTO SCANNER" in msg.sent[0]["text"]
    assert msg.chat.actions == ["typing"]


@pytest.mark.asyncio
async def test_status_with_results(monkeypatch):
    state = {
        "last_scan_at": "2026-08-16T02:00:00+00:00",
        "last_scan_status": "ok",
        "last_error": None,
        "pairs_found": 459,
        "pairs_analysed": 4,
        "last_results": [
            {
                "symbol": "SOL_USDT",
                "display": "SOL/USDT",
                "score": 82.5,
                "trend": "bullish",
                "ai_verdict": {"verdict": "WATCH", "risk": "MEDIUM"},
            },
            {
                "symbol": "BTC_USDT",
                "display": "BTC/USDT",
                "score": 60.0,
                "trend": "bearish",
                "ai_verdict": {"verdict": "NEUTRAL", "risk": "HIGH"},
            },
        ],
    }
    update, context, msg = make_update_and_context()
    monkeypatch.setattr("app.bot.handlers.crypto.crypto_scanner", FakeScanner(state=state))
    await crypto_handler(update, context)
    text = msg.sent[0]["text"]
    assert "SOL/USDT" in text
    assert "82" in text
    assert "BTC/USDT" in text
    assert "WATCH" in text
    assert "🟢" in text  # bullish emoji
    assert "🔴" in text  # bearish emoji


@pytest.mark.asyncio
async def test_scan_subcommand(monkeypatch):
    update, context, msg = make_update_and_context(["scan"])
    fake_scanner = FakeScanner(state={}, scan_result={
        "status": "ok",
        "pairs_found": 459,
        "pairs_liquid": 40,
        "pairs_analysed": 40,
        "candidates": 5,
        "ai_analysed": 5,
        "alerts_sent": 2,
        "errors": 0,
        "duration_ms": 1200,
        "results": [
            {"symbol": "SUI_USDT", "display": "SUI/USDT", "score": 88.0,
             "price_change": {"1h": 4.5}, "ai_verdict": {"verdict": "STRONG_WATCH"}},
        ],
    })
    monkeypatch.setattr("app.bot.handlers.crypto.crypto_scanner", fake_scanner)
    await crypto_handler(update, context)
    assert fake_scanner.scan_called is True
    assert fake_scanner.dry_arg is False
    # First a "running..." status message, then results.
    assert any("Menjalankan crypto scan" in s["text"] for s in msg.sent)
    results_msg = [s for s in msg.sent if "Hasil Crypto Scan" in s["text"]]
    assert results_msg, "expected results message"
    assert "SUI/USDT" in results_msg[0]["text"]
    assert "88" in results_msg[0]["text"]
    assert "+4.5%" in results_msg[0]["text"]


@pytest.mark.asyncio
async def test_scan_dry_flag(monkeypatch):
    update, context, msg = make_update_and_context(["scan", "--dry"])
    fake_scanner = FakeScanner(state={}, scan_result={"status": "ok", "candidates": 0})
    monkeypatch.setattr("app.bot.handlers.crypto.crypto_scanner", fake_scanner)
    await crypto_handler(update, context)
    assert fake_scanner.dry_arg is True


@pytest.mark.asyncio
async def test_scan_skipped(monkeypatch):
    update, context, msg = make_update_and_context(["scan"])
    fake_scanner = FakeScanner(state={}, scan_result={"status": "skipped", "reason": "lock"})
    monkeypatch.setattr("app.bot.handlers.crypto.crypto_scanner", fake_scanner)
    await crypto_handler(update, context)
    assert any("masih aktif" in s["text"] for s in msg.sent)


@pytest.mark.asyncio
async def test_help_subcommand(monkeypatch):
    update, context, msg = make_update_and_context(["help"])
    monkeypatch.setattr("app.bot.handlers.crypto.crypto_scanner", FakeScanner(state={}))
    await crypto_handler(update, context)
    assert msg.sent[0]["text"] == CRYPTO_HELP_MESSAGE


@pytest.mark.asyncio
async def test_alerts_subcommand(monkeypatch):
    update, context, msg = make_update_and_context(["alerts"])
    monkeypatch.setattr("app.bot.handlers.crypto.crypto_scanner", FakeScanner(state={}))

    class FakeAlert:
        symbol = "SOL_IDR"
        display = "SOL/IDR"
        score = 82.0
        risk = "MEDIUM"
        delivery_status = "sent"
        created_at = None

    class FakeSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def execute(self, stmt):
            return FakeResult([FakeAlert()])

    class FakeResult:
        def __init__(self, rows):
            self._rows = rows
        def scalars(self):
            return self
        def all(self):
            return self._rows

    def fake_session_factory():
        return FakeSession()

    monkeypatch.setattr("app.db.session.async_session_factory", fake_session_factory)
    await crypto_handler(update, context)
    text = msg.sent[0]["text"]
    assert "Alert Crypto Terakhir" in text
    assert "SOL/IDR" in text


@pytest.mark.asyncio
async def test_alerts_empty(monkeypatch):
    update, context, msg = make_update_and_context(["alerts"])
    monkeypatch.setattr("app.bot.handlers.crypto.crypto_scanner", FakeScanner(state={}))

    class FakeSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def execute(self, stmt):
            return FakeResult([])

    class FakeResult:
        def __init__(self, rows):
            self._rows = rows
        def scalars(self):
            return self
        def all(self):
            return self._rows

    def fake_session_factory():
        return FakeSession()

    monkeypatch.setattr("app.db.session.async_session_factory", fake_session_factory)
    await crypto_handler(update, context)
    assert "Belum ada alert" in msg.sent[0]["text"]


@pytest.mark.asyncio
async def test_alerts_db_error(monkeypatch):
    update, context, msg = make_update_and_context(["alerts"])
    monkeypatch.setattr("app.bot.handlers.crypto.crypto_scanner", FakeScanner(state={}))

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr("app.db.session.async_session_factory", boom)
    await crypto_handler(update, context)
    assert "database tidak tersedia" in msg.sent[0]["text"]


def test_status_emoji():
    assert _status_emoji("ok") == "✅"
    assert _status_emoji("error") == "❌"
    assert _status_emoji("running") == "🔄"
    assert _status_emoji("skipped") == "⏳"
    assert _status_emoji("unknown") == "⚪"


class FakeScanner:
    """Minimal stand-in for the crypto_scanner singleton."""

    def __init__(self, state, scan_result=None):
        self.state = state
        self.scan_result = scan_result or {"status": "ok"}
        self.scan_called = False
        self.dry_arg = None

    async def run_scan(self, dry_run=None):
        self.scan_called = True
        self.dry_arg = dry_run
        return self.scan_result
