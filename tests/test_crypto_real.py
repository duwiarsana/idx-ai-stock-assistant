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
async def test_limit_sell_matches_documented_params(monkeypatch):
    """LIMIT sell must send exactly the documented params — extra fields like
    timeInForce trigger 'Request Parameter Error' on Tokocrypto."""
    captured = {}

    class FakeResp:
        def json(self):
            return {"code": 0, "data": {"orderId": 5, "executedQty": "1",
                                        "executedPrice": "3.494", "symbol": "EGLD_USDT"}}

    class FakeClient:
        is_closed = False

        async def post(self, url, data=None, headers=None):
            captured["data"] = data
            return FakeResp()

    c = make_client(monkeypatch)
    c._client = FakeClient()
    await c.limit_sell("EGLD_USDT", 1.452, 3.494)
    d = captured["data"]
    assert d["type"] == 1            # ORDER_LIMIT
    assert d["side"] == 1            # SELL
    assert d["quantity"] == "1.452"
    assert d["price"] == "3.494"
    assert "timeInForce" not in d


@pytest.mark.asyncio
async def test_get_symbol_rules_parses_tick_size(monkeypatch):
    class FakeResp:
        def json(self):
            return {"code": 0, "data": {"list": [{
                "symbol": "EGLD_USDT",
                "filters": [
                    {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                    {"filterType": "NOTIONAL", "minNotional": "5"},
                    {"filterType": "PRICE_FILTER", "tickSize": "0.001"},
                ],
            }]}}

    class FakeClient:
        is_closed = False

        async def get(self, url, params=None, headers=None):
            return FakeResp()

    c = make_client(monkeypatch)
    c._client = FakeClient()
    rules = await c.get_symbol_rules("EGLD_USDT")
    assert rules["tick_size"] == 0.001
    assert rules["step_size"] == 0.001
    assert rules["min_notional"] == 5.0


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
        async def get_balance(self, asset):
            return 0.1  # wallet holds the full position (no fee shortfall)

        async def get_symbol_rules(self, symbol):
            return {"step_size": 0.001, "min_qty": 0.001, "min_notional": 5.0}

        async def market_sell(self, symbol, quantity):
            sold["symbol"] = symbol
            sold["quantity"] = quantity
            return {"code": 0, "data": {"orderId": 88, "executedQty": str(quantity),
                                        "executedPrice": "190", "executedQuoteQty": str(quantity * 190),
                                        "symbol": symbol}}

        async def limit_sell(self, symbol, quantity, price):
            # TP exits place a LIMIT sell (slippage protection) — emulate a fill.
            sold["symbol"] = symbol
            sold["quantity"] = quantity
            sold["limit_price"] = price
            return {"code": 0, "data": {"orderId": 88, "executedQty": str(quantity),
                                        "executedPrice": str(price), "executedQuoteQty": str(quantity * price),
                                        "symbol": symbol}}

    t.client = FakeClient()

    class P:
        id = "pos-real-1"
        symbol = "SOL_USDT"
        base = "SOL"
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
        base = "SOL"
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


@pytest.mark.asyncio
async def test_tp_exit_falls_back_to_market_when_limit_rejected(monkeypatch):
    """A LIMIT sell rejected by the exchange must retry as MARKET so the TP
    exit never leaves the position stuck open (the Aug-2026 bug)."""
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "crypto_real_notify", False)
    from app.services.crypto_real import RealTrader, STATUS_OPEN
    t = RealTrader()

    calls = []

    class FakeClient:
        async def get_balance(self, asset):
            return 5.0

        async def get_symbol_rules(self, symbol):
            return {"step_size": 0.001, "min_qty": 0.001,
                    "min_notional": 5.0, "tick_size": 0.001}

        async def limit_sell(self, symbol, quantity, price):
            calls.append("limit")
            raise Exception("API error 400 on /open/v1/orders: Request Parameter Error")

        async def market_sell(self, symbol, quantity):
            calls.append("market")
            return {"code": 0, "data": {"orderId": 99, "executedQty": str(quantity),
                                        "executedPrice": "3.494",
                                        "executedQuoteQty": str(quantity * 3.494),
                                        "symbol": symbol}}

    t.client = FakeClient()

    class P:
        id = "pos-fallback-1"
        symbol = "EGLD_USDT"
        base = "EGLD"
        quote = "USDT"
        display = "EGLD/USDT"
        status = STATUS_OPEN
        mode = "REAL"
        entry_price = 3.425
        quantity = 2.0
        invested = 6.85
        take_profit_1 = 3.49350
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
        def add(self, obj): pass
    session = FakeSession()

    ok = await t._close_position(session, pos, account, "TP1", 3.494)
    assert ok is True
    assert calls == ["limit", "market"]   # tried limit first, then market
    assert pos.status == "CLOSED"
    assert pos.exit_reason == "TP1"


# ── Dust-trap fixes ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dust_close_books_market_value_not_full_loss(monkeypatch):
    """A dust force-close must book the REAL market value of holdings as PnL,
    never -invested (-100%). The coins stay in the wallet."""
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "crypto_real_notify", False)
    from app.services.crypto_real import RealTrader, STATUS_OPEN
    t = RealTrader()

    class FakeClient:
        async def get_balance(self, asset):
            return 5.5  # full position is available

        async def get_symbol_rules(self, symbol):
            return {"step_size": 0.001, "min_qty": 0.001, "min_notional": 5.0}

    t.client = FakeClient()

    class P:
        id = "pos-dust-1"
        symbol = "KAVA_USDT"
        base = "KAVA"
        quote = "USDT"
        display = "KAVA/USDT"
        status = STATUS_OPEN
        mode = "REAL"
        entry_price = 1.0
        quantity = 5.5
        invested = 5.5   # entered right AT the exchange minimum (the trap)
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
        def add(self, obj): pass
    session = FakeSession()

    # Price dipped just -10% → notional 4.95 < min 5 → unsellable → dust close.
    ok = await t._close_position(session, pos, account, "SL", 0.9)
    assert ok is True
    assert pos.status == "CLOSED"
    assert pos.exit_reason == "SL_DUST"
    # OLD BUG: pnl was -abs(invested) = -5.5 (-100%). TRUE result: -0.55 (-10%).
    assert pos.realized_pnl == pytest.approx(-0.55, abs=1e-6)
    assert account.realized_pnl == pytest.approx(-0.55, abs=1e-6)


def test_entry_gate_blocks_pegged_assets(monkeypatch):
    """Stablecoins / gold tokens / wrapped assets must never pass the gate."""
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "crypto_real_trading_enabled", True)
    from app.services.crypto_real import RealTrader
    t = RealTrader()

    def strong_candidate(symbol):
        return {
            "symbol": symbol, "display": symbol.replace("_", "/"),
            "base": symbol.split("_")[0], "quote": "USDT",
            "price": 1.0, "score": 95.0,
            "tf_summaries": {"1h": {
                "trend": "bullish", "macd_state": "bullish", "price": 1.0,
                "ema20": 0.98, "at_high": False, "relative_volume": 3.0,
                "atr": 0.001,
            }},
            "ticker": {"quoteVolume": "50_000_000", "priceChangePercent": "1.0"},
            "price_levels": {"risk_reward": 2.0},
        }

    for pegged in ("USD1_USDT", "XUSD_USDT", "BFUSD_USDT", "PAXG_USDT",
                   "XAUT_USDT", "WBETH_USDT", "USDC_USDT"):
        assert t._passes_entry_gate(strong_candidate(pegged)) is False, pegged

    # A real volatile asset with identical (strong) signals still passes.
    assert t._passes_entry_gate(strong_candidate("SOL_USDT")) is True


@pytest.mark.asyncio
async def test_open_position_skips_when_balance_below_floor(monkeypatch, make_candidate):
    """When the balance can't support the position-size floor, skip the BUY."""
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "crypto_real_trading_enabled", True)
    monkeypatch.setattr(get_settings(), "crypto_real_notify", False)
    monkeypatch.setattr(get_settings(), "crypto_real_allocation_percent", 100.0)

    from app.services.crypto_real import RealTrader
    t = RealTrader()

    buys = []

    class FakeClient:
        async def get_symbol_rules(self, symbol):
            return {"step_size": 0.001, "min_qty": 0.001, "min_notional": 5.0}

        async def market_buy(self, symbol, quantity):
            buys.append(quantity)
            return {"code": 0, "data": {"executedQty": str(quantity),
                                        "executedPrice": "180", "symbol": symbol}}

    t.client = FakeClient()

    async def fake_balance(q):
        return 6.0  # below the 7 USDT floor (and its headroom)
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
    assert buys == []          # no order placed
    assert session.added == [] # nothing persisted


@pytest.mark.asyncio
async def test_open_position_sizes_up_to_floor(monkeypatch, make_candidate):
    """Allocation below the floor is bumped UP to the floor (not to the bare
    exchange minimum) so a small dip can't make the position unsellable."""
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "crypto_real_trading_enabled", True)
    monkeypatch.setattr(get_settings(), "crypto_real_notify", False)
    monkeypatch.setattr(get_settings(), "crypto_real_allocation_percent", 25.0)

    from app.services.crypto_real import RealTrader
    t = RealTrader()

    buys = []

    class FakeClient:
        async def get_symbol_rules(self, symbol):
            return {"step_size": 0.001, "min_qty": 0.001, "min_notional": 5.0}

        async def market_buy(self, symbol, quantity):
            buys.append(quantity)
            return {"code": 0, "data": {"orderId": 90, "executedQty": str(quantity),
                                        "executedPrice": "180",
                                        "executedQuoteQty": str(quantity * 180),
                                        "symbol": symbol}}

    t.client = FakeClient()

    async def fake_balance(q):
        return 20.0  # 25% = 5 USDT < 7 floor, but balance supports the floor
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
    invested = buys[0] * 180.0
    assert invested >= 6.9  # sized at/above the 7 USDT floor (step rounding)
    positions = [o for o in session.added if type(o).__name__ == "CryptoPaperPosition"]
    assert len(positions) == 1

# ── Portfolio summary regression: stats must survive empty book ────────

@pytest.mark.asyncio
async def test_portfolio_summary_includes_stats_with_no_open_positions(monkeypatch):
    """After the last sell (no OPEN positions) the Telegram summary must still
    include Total Realized PnL and Total Trade. Regression for the missing
    ``func`` import that silently zeroed the stats via except/pass."""
    from types import SimpleNamespace
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "crypto_real_notify", False)
    from app.services import crypto_real as cr

    t = cr.RealTrader()

    async def fake_balance(q):
        return 123.45
    t._real_balance = fake_balance

    # First query (OPEN positions) → none left. Second query (stats) → 7 trades.
    class FakeResult:
        def __init__(self, value):
            self._value = value
        def scalars(self):
            return self
        def all(self):
            return self._value
        def one(self):
            return self._value

    calls = {"n": 0}

    class FakeSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def execute(self, stmt, *a, **k):
            calls["n"] += 1
            if calls["n"] == 1:
                return FakeResult([])                       # no open positions
            return FakeResult((-1694.21, 7, 2))             # sum, count, wins

    import app.db.session as db_session
    orig_factory = db_session.async_session_factory
    monkeypatch.setattr(db_session, "async_session_factory", lambda: FakeSession())

    text = await t._portfolio_summary("USDT")

    assert "Tidak ada" in text                      # open positions section present
    assert "-1,694.21 USDT" in text                 # realized PnL NOT zeroed/missing
    assert "Total Trade: 7" in text and "2 menang" in text


# ── Pegged-asset guard: never buy a stablecoin with TP/SL ─────────────

@pytest.mark.asyncio
async def test_pegged_guard_blocks_newly_listed_stablecoin(monkeypatch):
    """A stablecoin not in the static blacklist (e.g. RLUSD) must be refused
    via the defensive exchange-rules pegged check before any money is spent."""
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "crypto_real_notify", False)
    from app.services.crypto_real import RealTrader
    t = RealTrader()

    class FakeClient:
        async def get_symbol_rules(self, symbol):
            # RLUSD-style 1:1 stablecoin: step ~1.0 → flagged as pegged
            if symbol == "RLUSD_USDT":
                return {"step_size": 1.0, "min_qty": 1.0, "min_notional": 5.0, "tick_size": 0.0001}
            return {"step_size": 0.001, "min_qty": 0.001, "min_notional": 5.0, "tick_size": 0.00001}
    t.client = FakeClient()

    # RLUSD looks like a genuine 1:1 stablecoin → guard must refuse BEFORE market_buy
    assert await t._is_pegged("RLUSD_USDT") is True

    # A normal alt is allowed (returns False for pegged)
    assert await t._is_pegged("BTC_USDT") is False


@pytest.mark.asyncio
async def test_pegged_guard_covers_blacklist_without_rules(monkeypatch):
    """A blacklisted stablecoin is refused even if rules lookup fails."""
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "crypto_real_notify", False)
    from app.services.crypto_real import RealTrader
    t = RealTrader()

    class FakeClient:
        async def get_symbol_rules(self, symbol):
            raise RuntimeError("no rules")
    t.client = FakeClient()

    # U is now in the static blacklist → refused even without rules
    assert await t._is_pegged("U_USDT") is True
