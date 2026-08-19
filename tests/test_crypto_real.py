"""Tests for the real-trading client & engine (all mocked — no real money)."""

import hashlib
import hmac

import pytest

from app.data.tokocrypto_trade_client import TokoCryptoTradeClient, TokoTradeError


def make_client(monkeypatch, key="k123", secret="s456"):
    c = TokoCryptoTradeClient(api_key=key, api_secret=secret)
    return c


@pytest.mark.asyncio
async def test_requires_config(monkeypatch):
    c = TokoCryptoTradeClient(api_key="", api_secret="")
    with pytest.raises(TokoTradeError):
        await c.get_balance("USDT")


def test_signature_is_hmac_sha256():
    c = make_client(None, key="cfDC92B191b9B3Ca3D842Ae0e01108CBKI6BqEW6xr4NrPus3hoZ9Ze9YrmWwPFV",
                    secret="f9AbA6a8AD6bC2a97294a212244dda04ETfl0kc4BSUGOtL7m7rNELpt3Jh25SiP")
    params = {"symbol": "BTC_USDT", "side": 0, "type": 1, "quantity": "0.16",
              "price": "7500", "timestamp": 1581720670624, "recvWindow": 5000}
    from urllib.parse import urlencode
    # Tokocrypto signs in INSERTION ORDER (same order the request is sent).
    query = urlencode(params)
    expected = hmac.new(b"f9AbA6a8AD6bC2a97294a212244dda04ETfl0kc4BSUGOtL7m7rNELpt3Jh25SiP",
                        query.encode(), hashlib.sha256).hexdigest()
    signed = c._sign(dict(params))
    assert signed["signature"] == expected
    # Must match the documented example signature.
    assert expected == "33824b5160daefc34257ab9cd3c3db7a0158a446674f896c9fc3b122ae656bfa"


def test_parse_fill_normalises_market_buy():
    c = make_client(None)
    resp = {"code": 0, "data": {
        "orderId": 305549804,
        "symbol": "BTC_USDT",
        "side": 0,
        "type": 2,
        "executedQty": "0.016",
        "executedPrice": "65500",
        "executedQuoteQty": "1048.0",
    }}
    fill = c.parse_fill(resp)
    assert fill["order_id"] == 305549804
    assert fill["quantity"] == 0.016
    assert fill["price"] == 65500
    assert fill["quote_amount"] == 1048.0


@pytest.mark.asyncio
async def test_market_buy_sends_signed_post(monkeypatch):
    captured = {}

    class FakeResp:
        def json(self):
            return {"code": 0, "data": {"orderId": 1, "executedQty": "1", "executedPrice": "10",
                                        "executedQuoteQty": "10", "symbol": "X"}}

    class FakeClient:
        is_closed = False

        async def post(self, url, data=None, headers=None):
            captured["url"] = url
            captured["data"] = data
            captured["headers"] = headers
            return FakeResp()

    c = make_client(monkeypatch)
    c._client = FakeClient()
    resp = await c.market_buy("BTC_USDT", 0.00008)
    assert captured["url"].endswith("/open/v1/orders")
    assert "signature" in captured["data"]
    assert captured["headers"]["X-MBX-APIKEY"] == "k123"
    assert captured["data"]["side"] == 0
    assert captured["data"]["type"] == 2
    assert captured["data"]["quantity"] == "0.00008"
    assert "quoteOrderQty" not in captured["data"]
    assert resp["code"] == 0


@pytest.mark.asyncio
async def test_api_error_raises(monkeypatch):
    class FakeResp:
        def json(self):
            return {"code": -1021, "msg": "Timestamp for this request is outside of the recvWindow."}

    class FakeClient:
        is_closed = False

        async def get(self, url, params=None, headers=None):
            return FakeResp()

    c = make_client(monkeypatch)
    c._client = FakeClient()
    with pytest.raises(TokoTradeError):
        await c.get_balance("USDT")


def test_no_withdraw_endpoint():
    """Safety: the trade client must never call a withdrawal endpoint."""
    import re
    src = open("app/data/tokocrypto_trade_client.py").read()
    # No signed request may target a withdraw endpoint.
    assert not re.search(r"_request\(\s*[\"'](?:GET|POST)[\"'],\s*[\"']/open/v1/withdraw", src)
    assert not re.search(r"/withdraw", src)
    assert "withdraw" not in [m for m in dir(TokoCryptoTradeClient)]


def test_real_trading_disabled_by_default():
    from app.config import get_settings
    assert get_settings().crypto_real_trading_enabled is False
    assert get_settings().crypto_real_allocation_percent <= 2.0


# ── RealTrader engine tests (all mocked) ──────────────────────────────

@pytest.fixture
def make_candidate():
    def _make(symbol="SOL_USDT", score=88.0):
        s1h = {
            "trend": "bullish", "rsi": 62.0, "price": 180.0, "at_high": False,
            "relative_volume": 2.0, "ema20": 175.0, "macd_state": "bullish",
        }
        return {
            "symbol": symbol, "display": symbol.replace("_", "/"), "base": symbol.split("_")[0],
            "quote": "USDT", "price": 180.0, "score": score,
            "tf_summaries": {"5m": {}, "15m": {}, "1h": s1h},
            "price_levels": {"entry": 180.0, "take_profit_1": 190.0,
                             "take_profit_2": 200.0, "stop_loss": 170.0},
        }
    return _make


class FakeAccountResult:
    def scalars(self): return self
    def all(self): return []
    def scalar(self): return 0
    def scalar_one_or_none(self): return None


class FakeAccountSession:
    def __init__(self):
        self.added = []
    async def flush(self): pass
    def add(self, obj): self.added.append(obj)
    async def execute(self, stmt, *a, **k): return FakeAccountResult()


@pytest.mark.asyncio
async def test_run_cycle_disabled_does_nothing(monkeypatch, make_candidate):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "crypto_real_trading_enabled", False)
    from app.services.crypto_real import RealTrader
    t = RealTrader()
    res = await t.run_cycle([make_candidate()], {})
    assert res["positions_opened"] == 0


@pytest.mark.asyncio
async def test_open_position_places_market_buy(monkeypatch, make_candidate):
    """_open_position sends a REAL market buy and persists a REAL position."""
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "crypto_real_trading_enabled", True)
    monkeypatch.setattr(get_settings(), "crypto_real_notify", False)
    monkeypatch.setattr(get_settings(), "crypto_real_allocation_percent", 45.0)

    from app.services.crypto_real import RealTrader
    t = RealTrader()

    class FakeClient:
        async def get_symbol_rules(self, symbol):
            return {"step_size": 0.001, "min_qty": 0.001, "min_notional": 5.0}

        async def market_buy(self, symbol, quantity):
            return {"code": 0, "data": {"orderId": 77, "executedQty": str(quantity),
                                        "executedPrice": "180", "executedQuoteQty": str(quantity * 180),
                                        "symbol": symbol}}

    t.client = FakeClient()
    async def fake_balance(q):
        return 1000.0
    t._real_balance = fake_balance

    class Account:
        quote_asset = "USDT"
        realized_pnl = 0.0
        total_trades = 0
        winning_trades = 0
    account = Account()

    class FakeSession:
        def __init__(self):
            self.added = []
        async def flush(self): pass
        def add(self, obj): self.added.append(obj)
        async def execute(self, stmt, *a, **k): return FakeAccountResult()
    session = FakeSession()

    cand = make_candidate()
    ok = await t._open_position(session, cand, 180.0, "USDT")
    assert ok is True
    positions = [o for o in session.added if type(o).__name__ == "CryptoPaperPosition"]
    assert len(positions) == 1
    assert positions[0].mode == "REAL"
    assert positions[0].entry_price == 180.0
    assert positions[0].quantity == 2.5  # 1000*45%/180 = 2.5 SOL, rounded up to step 0.001
    assert positions[0].stop_loss == 170.0


@pytest.mark.asyncio
async def test_open_position_skips_when_not_sellable(monkeypatch, make_candidate):
    """A BUY that cannot be sized to a sellable position must be skipped."""
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "crypto_real_trading_enabled", True)
    monkeypatch.setattr(get_settings(), "crypto_real_notify", False)
    monkeypatch.setattr(get_settings(), "crypto_real_allocation_percent", 100.0)

    from app.services.crypto_real import RealTrader
    t = RealTrader()

    class FakeClient:
        async def get_symbol_rules(self, symbol):
            return {"step_size": 0.001, "min_qty": 0.001, "min_notional": 5.0}

        async def market_buy(self, symbol, quantity):
            return {"code": 0, "data": {"orderId": 77, "executedQty": str(quantity),
                                        "executedPrice": "180", "executedQuoteQty": str(quantity * 180),
                                        "symbol": symbol}}

    t.client = FakeClient()

    async def fake_balance(q):
        return 4.0  # 100% = 4 USDT < 5 min, and too small to grow to sellable
    t._real_balance = fake_balance

    class FakeSession:
        def __init__(self):
            self.added = []
        async def flush(self): pass
        def add(self, obj): self.added.append(obj)
        async def execute(self, stmt, *a, **k): return FakeAccountResult()
    session = FakeSession()

    ok = await t._open_position(session, make_candidate(), 180.0, "USDT")
    assert ok is False
    assert session.added == []  # no position persisted


@pytest.mark.asyncio
async def test_open_position_grows_size_when_allocation_below_min(monkeypatch, make_candidate):
    """When allocation < NOTIONAL floor, the walk grows the position so it is
    sellable — the bot must not just skip."""
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "crypto_real_trading_enabled", True)
    monkeypatch.setattr(get_settings(), "crypto_real_notify", False)
    monkeypatch.setattr(get_settings(), "crypto_real_allocation_percent", 45.0)

    from app.services.crypto_real import RealTrader
    t = RealTrader()

    buys = []

    class FakeClient:
        async def get_symbol_rules(self, symbol):
            return {"step_size": 0.001, "min_qty": 0.001, "min_notional": 5.0}

        async def market_buy(self, symbol, quantity):
            buys.append(quantity)
            return {"code": 0, "data": {"orderId": 77, "executedQty": str(quantity),
                                        "executedPrice": "180", "executedQuoteQty": str(quantity * 180),
                                        "symbol": symbol}}

    t.client = FakeClient()

    async def fake_balance(q):
        return 10.55  # 45% = 4.75 < 5 -> walk must grow to ~0.029 (5.2 USDT)
    t._real_balance = fake_balance

    class FakeSession:
        def __init__(self):
            self.added = []
        async def flush(self): pass
        def add(self, obj): self.added.append(obj)
        async def execute(self, stmt, *a, **k): return FakeAccountResult()
    session = FakeSession()

    ok = await t._open_position(session, make_candidate(), 180.0, "USDT")
    assert ok is True
    assert buys, "a buy must have been placed"
    qty = buys[0]
    # sellable after fee + round-down: round_down(qty*0.998, 0.001)*180 >= 5
    sellable_qty = t._round_down_to_step(qty * 0.998, 0.001)
    assert sellable_qty * 180 >= 5.0
    positions = [o for o in session.added if type(o).__name__ == "CryptoPaperPosition"]
    assert len(positions) == 1
    assert positions[0].quantity > 0.0


@pytest.mark.asyncio
async def test_close_position_places_market_sell(monkeypatch, make_candidate):
    """Closing a REAL position sells the full quantity at market."""
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "crypto_real_notify", False)
    from app.services.crypto_real import RealTrader, STATUS_OPEN
    t = RealTrader()

    sold = {}

    class FakeClient:
        async def get_symbol_rules(self, symbol):
            return {"step_size": 0.001, "min_qty": 0.001, "min_notional": 5.0}

        async def market_sell(self, symbol, quantity):
            sold["symbol"] = symbol
            sold["quantity"] = quantity
            return {"code": 0, "data": {"orderId": 88, "executedQty": str(quantity),
                                        "executedPrice": "190", "executedQuoteQty": str(quantity * 190),
                                        "symbol": symbol}}

    t.client = FakeClient()

    class P:
        id = "pos-real-1"
        symbol = "SOL_USDT"
        quote = "USDT"
        display = "SOL/USDT"
        status = STATUS_OPEN
        mode = "REAL"
        entry_price = 180.0
        quantity = 0.1
        invested = 18.0
        take_profit_1 = 190.0
        take_profit_2 = 200.0
        stop_loss = 170.0
        exit_price = None
        exit_reason = None
        realized_pnl = None
        closed_at = None
    pos = P()

    class Account:
        quote_asset = "USDT"
        realized_pnl = 0.0
        total_trades = 0
        winning_trades = 0
    account = Account()

    class FakeSession:
        def __init__(self):
            self.added = []
        def add(self, obj): self.added.append(obj)
    session = FakeSession()

    ok = await t._close_position(session, pos, account, "TP1", 190.0)
    assert ok is True
    assert sold["symbol"] == "SOL_USDT"
    assert sold["quantity"] == 0.1
    assert pos.status == "CLOSED"
    assert pos.realized_pnl == pytest.approx(1.0, abs=0.01)
    assert pos.exit_reason == "TP1"


@pytest.mark.asyncio
async def test_close_position_keeps_open_on_sell_failure(monkeypatch, make_candidate):
    """A failed SELL must NOT mark the position closed (retry next cycle)."""
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "crypto_real_notify", False)
    from app.services.crypto_real import RealTrader, STATUS_OPEN
    t = RealTrader()

    class FakeClient:
        async def get_symbol_rules(self, symbol):
            return {"step_size": 0.001, "min_qty": 0.001, "min_notional": 5.0}

        async def market_sell(self, symbol, quantity):
            raise Exception("simulated API error")

    t.client = FakeClient()

    class P:
        id = "pos-real-2"
        symbol = "SOL_USDT"
        quote = "USDT"
        display = "SOL/USDT"
        status = STATUS_OPEN
        mode = "REAL"
        entry_price = 180.0
        quantity = 0.1
        invested = 18.0
    pos = P()

    class Account:
        realized_pnl = 0.0
        total_trades = 0
        winning_trades = 0
    account = Account()

    class FakeSession:
        def add(self, obj): pass
    session = FakeSession()

    ok = await t._close_position(session, pos, account, "SL", 170.0)
    assert ok is False
    assert pos.status == STATUS_OPEN  # still open — will retry


@pytest.mark.asyncio
async def test_drawdown_guard_stops_new_entries(monkeypatch, make_candidate):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "crypto_real_trading_enabled", True)
    monkeypatch.setattr(get_settings(), "crypto_real_max_drawdown", 50.0)

    from app.services.crypto_real import RealTrader
    t = RealTrader()

    class AccountNeg:
        quote_asset = "USDT"
        realized_pnl = -120.0
    class EmptyResult:
        def scalars(self): return self
        def all(self): return []
        def scalar(self): return 0
        def scalar_one_or_none(self): return AccountNeg()

    class FakeSession:
        def __init__(self):
            self.added = []
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def commit(self): pass
        async def flush(self): pass
        def add(self, obj): self.added.append(obj)
        async def execute(self, stmt, *a, **k): return EmptyResult()

    res = await t.run_cycle([make_candidate()], {})
    # Drawdown exceeded → no positions opened.
    assert res["positions_opened"] == 0