"""Tests for the CryptoScanner orchestrator pipeline (mocked Tokocrypto client)."""

import asyncio

import pytest

from app.services.crypto_scanner import CryptoScanner
from app.data.tokocrypto_client import TokocryptoSymbol
from tests.crypto_fixtures import make_candles_uptrend, make_candles_downtrend


class MockTokocryptoClient:
    """Pre-built fake client returning deterministic data."""

    def __init__(self):
        self.symbols = [
            TokocryptoSymbol("BTC_USDT", "BTC", "USDT", 1, True),
            TokocryptoSymbol("SUI_USDT", "SUI", "USDT", 1, True),
            TokocryptoSymbol("TKO_IDR", "TKO", "IDR", 3, True),
            TokocryptoSymbol("USDT_USDC", "USDT", "USDC", 1, True),  # stablecoin base
            TokocryptoSymbol("HALTED_USDT", "HALTED", "USDT", 1, False),
        ]
        self.tickers = {
            "BTCUSDT": {"symbol": "BTCUSDT", "lastPrice": 63000.0, "quoteVolume": 6.3e9},
            "SUIUSDT": {"symbol": "SUIUSDT", "lastPrice": 1.23, "quoteVolume": 2.4e6},
            "TKOIDR": {"symbol": "TKOIDR", "lastPrice": 2500.0, "quoteVolume": 5.0e7},
        }
        self.kline_calls = []

    async def fetch_symbols(self, cache_ttl=300, force=False):
        return self.symbols

    async def fetch_tickers(self):
        return self.tickers

    async def fetch_klines(self, symbol, interval, limit=200):
        self.kline_calls.append((symbol.raw_symbol, interval))
        if interval == "1h":
            return make_candles_uptrend(n=80)
        return make_candles_uptrend(n=60)


@pytest.fixture
def scanner(monkeypatch):
    client = MockTokocryptoClient()
    s = CryptoScanner(client=client)
    # Lower the alert threshold so synthetic uptrends qualify as candidates.
    from app.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "crypto_min_score_alert", 30)
    monkeypatch.setattr(settings, "crypto_min_quote_volume", "1000000")
    # Bypass DB persistence (no database in unit tests).
    async def noop_persist(*args, **kwargs):
        pass
    monkeypatch.setattr(s, "_persist_scan", noop_persist)
    monkeypatch.setattr(s, "persist_alert", noop_persist)
    # Bypass Telegram + AI.
    async def fake_send(candidate, verdict, dry_run=None):
        return {"sent": True, "dry_run": True, "reason": "test"}
    monkeypatch.setattr("app.services.crypto_scanner.send_crypto_alert", fake_send)
    async def fake_should(candidate, cooldown_minutes=None):
        return True, "test"
    monkeypatch.setattr("app.services.crypto_scanner.should_alert", fake_should)
    from app.services.crypto_ai import deterministic_fallback
    async def fake_analyze(candidates):
        return {c["symbol"]: deterministic_fallback(c) for c in candidates}
    monkeypatch.setattr("app.services.crypto_scanner.analyze_candidates", fake_analyze)
    return s


@pytest.mark.asyncio
async def test_pipeline_filters_stablecoins_and_inactive(scanner):
    summary = await scanner.run_scan()
    assert summary["status"] == "ok"
    # USDT_USDC (stablecoin base) and HALTED_USDT (spot disabled) must be excluded.
    assert summary["pairs_found"] == 3  # BTC_USDT, SUI_USDT, TKO_IDR
    assert summary["pairs_liquid"] == 3
    assert summary["candidates"] > 0


@pytest.mark.asyncio
async def test_pipeline_scores_and_ranks(scanner):
    summary = await scanner.run_scan()
    results = summary["results"]
    assert results
    # results must be sorted by score descending.
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)
    for r in results:
        assert r["score"] >= 0
        assert "ai_verdict" in r
        assert r["symbol"] in ("BTC_USDT", "SUI_USDT", "TKO_IDR")


@pytest.mark.asyncio
async def test_pipeline_skips_overlapping_runs(scanner):
    # Hold the lock, then attempt a second run.
    async with scanner.lock:
        summary = await scanner.run_scan()
    assert summary["status"] == "skipped"


@pytest.mark.asyncio
async def test_pipeline_no_kline_for_missing_ticker(monkeypatch):
    """Pairs without a 24h ticker should be skipped early."""
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "crypto_min_score_alert", 30)
    monkeypatch.setattr(get_settings(), "crypto_scanner_dry_run", True)

    client = MockTokocryptoClient()
    del client.tickers["SUIUSDT"]
    s = CryptoScanner(client=client)
    async def noop(*a, **k): pass
    s._persist_scan = noop
    s.persist_alert = noop
    async def fake_send(candidate, verdict, dry_run=None):
        return {"sent": True, "dry_run": True, "reason": "test"}
    monkeypatch.setattr("app.services.crypto_scanner.send_crypto_alert", fake_send)
    async def fake_should(candidate, cooldown_minutes=None):
        return True, "test"
    monkeypatch.setattr("app.services.crypto_scanner.should_alert", fake_should)
    from app.services.crypto_ai import deterministic_fallback
    async def fake_analyze(candidates):
        return {c["symbol"]: deterministic_fallback(c) for c in candidates}
    monkeypatch.setattr("app.services.crypto_scanner.analyze_candidates", fake_analyze)

    summary = await s.run_scan()
    # SUI is not in tickers → excluded from liquid set.
    symbols_in_results = {r["symbol"] for r in summary["results"]}
    assert "SUI_USDT" not in symbols_in_results


@pytest.mark.asyncio
async def test_min_quote_volume_filter(monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "crypto_min_score_alert", 30)
    monkeypatch.setattr(get_settings(), "crypto_scanner_dry_run", True)

    client = MockTokocryptoClient()
    # Make SUI's quote volume tiny so it falls below the default 1M threshold.
    client.tickers["SUIUSDT"] = {"symbol": "SUIUSDT", "lastPrice": 1.23, "quoteVolume": 100.0}
    s = CryptoScanner(client=client)
    async def noop(*a, **k): pass
    s._persist_scan = noop
    s.persist_alert = noop
    async def fake_send(candidate, verdict, dry_run=None):
        return {"sent": True, "dry_run": True, "reason": "test"}
    monkeypatch.setattr("app.services.crypto_scanner.send_crypto_alert", fake_send)
    async def fake_should(candidate, cooldown_minutes=None):
        return True, "test"
    monkeypatch.setattr("app.services.crypto_scanner.should_alert", fake_should)
    from app.services.crypto_ai import deterministic_fallback
    async def fake_analyze(candidates):
        return {c["symbol"]: deterministic_fallback(c) for c in candidates}
    monkeypatch.setattr("app.services.crypto_scanner.analyze_candidates", fake_analyze)

    summary = await s.run_scan()
    symbols_in_results = {r["symbol"] for r in summary["results"]}
    assert "SUI_USDT" not in symbols_in_results
    assert "BTC_USDT" in symbols_in_results


@pytest.mark.asyncio
async def test_kline_timeframes_requested(scanner):
    await scanner.run_scan()
    intervals = {i for _, i in scanner.client.kline_calls}
    assert intervals == {"5m", "15m", "1h"}
    # Each liquid pair should have requested all three timeframes.
    per_symbol = {}
    for sym, interval in scanner.client.kline_calls:
        per_symbol.setdefault(sym, []).append(interval)
    for sym in ("BTC_USDT", "SUI_USDT", "TKO_IDR"):
        assert sorted(per_symbol[sym]) == ["15m", "1h", "5m"]
