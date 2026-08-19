"""Tests for Tokocrypto API client — response parsing robustness (mock HTTP)."""

import pytest

from app.data.tokocrypto_client import TokocryptoClient, TokocryptoSymbol, TokocryptoResponseError
from tests.crypto_fixtures import (
    sample_symbol_entry,
    sample_symbols_response,
    sample_ticker_list,
    sample_kline_rows,
)


@pytest.fixture
def client():
    c = TokocryptoClient(timeout=5, max_retries=1)
    yield c


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            from httpx import HTTPStatusError
            raise HTTPStatusError("boom", request=None, response=None)


class FakeClient:
    """Minimal async httpx stand-in recording calls."""

    def __init__(self, responses):
        self._responses = responses
        self.calls = []
        self.is_closed = False

    async def get(self, url, params=None):
        self.calls.append((url, params))
        if self._responses:
            return self._responses.pop(0)
        return FakeResponse({"code": 0, "msg": "success", "data": []})

    async def aclose(self):
        self.is_closed = True


async def fake_get_client(fake):
    return fake


def test_parse_symbol_underscore():
    s = TokocryptoClient.parse_symbol(sample_symbol_entry())
    assert s is not None
    assert s.raw_symbol == "BTC_USDT"
    assert s.normalized_symbol == "BTCUSDT"
    assert s.base == "BTC" and s.quote == "USDT"
    assert s.spot_trading is True
    assert s.display == "BTC/USDT"


def test_parse_symbol_no_underscore_is_rejected():
    assert TokocryptoClient.parse_symbol({"symbol": "BTCUSDT"}) is None


def test_parse_symbol_spot_disabled():
    s = TokocryptoClient.parse_symbol(sample_symbol_entry(spot=False))
    assert s.spot_trading is False


@pytest.mark.asyncio
async def test_fetch_symbols_unwraps_envelope(monkeypatch, client):
    fake = FakeClient([FakeResponse(sample_symbols_response())])
    monkeypatch.setattr(client, "_get_client", lambda: fake_get_client(fake))
    client._symbols_cache = (None, None)

    symbols = await client.fetch_symbols(force=True)
    assert len(symbols) == 7
    assert symbols[0].raw_symbol == "BTC_USDT"


@pytest.mark.asyncio
async def test_fetch_symbols_caches(monkeypatch, client):
    fake = FakeClient([FakeResponse(sample_symbols_response())])
    monkeypatch.setattr(client, "_get_client", lambda: fake_get_client(fake))

    await client.fetch_symbols(force=True)
    await client.fetch_symbols()  # should be served from cache
    assert len(fake.calls) == 1  # only one HTTP call


@pytest.mark.asyncio
async def test_fetch_symbols_errors(monkeypatch, client):
    fake = FakeClient([FakeResponse({"code": 30000, "msg": "bad"})])
    monkeypatch.setattr(client, "_get_client", lambda: fake_get_client(fake))
    client._symbols_cache = (None, None)

    with pytest.raises(TokocryptoResponseError):
        await client.fetch_symbols(force=True)


@pytest.mark.asyncio
async def test_fetch_tickers_bare_list(monkeypatch, client):
    fake = FakeClient([FakeResponse(sample_ticker_list())])
    monkeypatch.setattr(client, "_get_client", lambda: fake_get_client(fake))

    tickers = await client.fetch_tickers()
    assert "BTCUSDT" in tickers
    assert tickers["BTCUSDT"]["lastPrice"] == 63000.0
    assert tickers["BTCUSDT"]["priceChangePercent"] == 1.23
    assert tickers["BTCUSDT"]["quoteVolume"] == 63000000.0
    assert len(tickers) == 5


@pytest.mark.asyncio
async def test_fetch_tickers_envelope_wrapped(monkeypatch, client):
    payload = {"code": 0, "msg": "Success", "data": sample_ticker_list()}
    fake = FakeClient([FakeResponse(payload)])
    monkeypatch.setattr(client, "_get_client", lambda: fake_get_client(fake))

    tickers = await client.fetch_tickers()
    assert "SUIUSDT" in tickers
    assert tickers["SUIUSDT"]["priceChangePercent"] == 3.2


@pytest.mark.asyncio
async def test_fetch_klines_bare_array(monkeypatch, client):
    sym = TokocryptoSymbol("BTC_USDT", "BTC", "USDT", 1, True)
    fake = FakeClient([FakeResponse(sample_kline_rows())])
    monkeypatch.setattr(client, "_get_client", lambda: fake_get_client(fake))

    candles = await client.fetch_klines(sym, "1h", limit=60)
    assert len(candles) == 60
    first = candles[0]
    assert first["openTime"] == 1700000000000
    assert first["open"] == 100.0
    assert first["close"] == 100.5
    assert first["quoteVolume"] == 1500000.0
    assert first["numTrades"] == 300
    # kline request used normalized (no-underscore) symbol on v3
    url, params = fake.calls[0]
    assert "tokocrypto.site/api/v3/klines" in url
    assert params["symbol"] == "BTCUSDT"


@pytest.mark.asyncio
async def test_fetch_klines_type3_uses_v1_url(monkeypatch, client):
    sym = TokocryptoSymbol("TKO_IDR", "TKO", "IDR", 3, True)
    fake = FakeClient([FakeResponse([])])
    monkeypatch.setattr(client, "_get_client", lambda: fake_get_client(fake))

    candles = await client.fetch_klines(sym, "1h", limit=10)
    assert candles == []
    url, params = fake.calls[0]
    assert "2meta.app/api/v1/klines" in url
    assert params["symbol"] == "TKO_IDR"


@pytest.mark.asyncio
async def test_fetch_klines_bad_interval_raises(client):
    sym = TokocryptoSymbol("BTC_USDT", "BTC", "USDT", 1, True)
    with pytest.raises(ValueError):
        await client.fetch_klines(sym, "2h30m", limit=10)


@pytest.mark.asyncio
async def test_retry_on_timeout(monkeypatch, client):
    """Client should retry a few times and raise after exhausting attempts."""
    from httpx import TimeoutException

    class FailingClient:
        calls = 0
        is_closed = False

        async def get(self, url, params=None):
            self.calls += 1
            raise TimeoutException("timeout")

        async def aclose(self):
            pass

    fake = FailingClient()
    monkeypatch.setattr(client, "_get_client", lambda: fake_get_client(fake))
    client.max_retries = 3

    with pytest.raises(TokocryptoResponseError):
        await client.fetch_tickers()
    assert fake.calls == 3


@pytest.mark.asyncio
async def test_retry_on_rate_limit_backoff(monkeypatch, client):
    """429 responses should retry with a Retry-After delay."""
    fake = FakeClient([
        FakeResponse({}, status_code=429, headers={"Retry-After": "1"}),
        FakeResponse(sample_ticker_list()),
    ])
    monkeypatch.setattr(client, "_get_client", lambda: fake_get_client(fake))
    client.max_retries = 3

    tickers = await client.fetch_tickers()
    assert "BTCUSDT" in tickers
