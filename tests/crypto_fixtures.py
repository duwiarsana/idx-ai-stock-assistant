"""Fixtures shared across the crypto scanner test modules."""

import numpy as np
import pytest


def make_candles(n: int = 120, base: float = 100.0, drift: float = 0.0, vol: float = 0.02, vol_mult: float = 1.0, seed: int = 42):
    """Generate synthetic OHLCV candles with an optional linear drift."""
    rng = np.random.default_rng(seed)
    closes = [base]
    for i in range(1, n):
        ret = drift + rng.normal(0, vol)
        closes.append(max(closes[-1] * (1 + ret), 0.01))

    candles = []
    for i, close in enumerate(closes):
        rng2 = np.random.default_rng(seed + i)
        spread = close * rng2.uniform(0.001, 0.01)
        high = close + spread
        low = max(close - spread, 0.001)
        open_ = low + (high - low) * rng2.uniform(0.2, 0.8)
        candles.append({
            "openTime": i * 3600_000,
            "open": float(open_),
            "high": float(high),
            "low": float(low),
            "close": float(close),
            "volume": float(1000.0 * vol_mult + (i % 5) * 10),
        })
    return candles


def make_candles_uptrend(n: int = 120, vol_mult: float = 1.5):
    """Clear uptrend with volume — good candidate setup."""
    rng = np.random.default_rng(7)
    closes = [100.0]
    for i in range(1, n):
        closes.append(closes[-1] * (1 + 0.004 + rng.normal(0, 0.01)))
    candles = []
    for i, close in enumerate(closes):
        rng2 = np.random.default_rng(100 + i)
        spread = close * rng2.uniform(0.002, 0.012)
        candles.append({
            "openTime": i * 3600_000,
            "open": float(close * (1 - 0.002)),
            "high": float(close + spread),
            "low": float(close - spread),
            "close": float(close),
            "volume": float(1200.0 * vol_mult + (i % 5) * 10),
        })
    return candles


def make_candles_downtrend(n: int = 120):
    """Clear downtrend."""
    rng = np.random.default_rng(9)
    closes = [100.0]
    for i in range(1, n):
        closes.append(max(closes[-1] * (1 - 0.004 + rng.normal(0, 0.01)), 0.01))
    candles = []
    for i, close in enumerate(closes):
        rng2 = np.random.default_rng(200 + i)
        spread = close * rng2.uniform(0.002, 0.012)
        candles.append({
            "openTime": i * 3600_000,
            "open": float(close * (1 + 0.002)),
            "high": float(close + spread),
            "low": float(close - spread),
            "close": float(close),
            "volume": float(800.0 + (i % 5) * 10),
        })
    return candles


@pytest.fixture
def uptrend_candles():
    return make_candles_uptrend()


@pytest.fixture
def downtrend_candles():
    return make_candles_downtrend()


@pytest.fixture
def mixed_candles():
    return make_candles()


# Shared sample data objects for API/adapter tests.

def sample_symbol_entry(symbol="BTC_USDT", base="BTC", quote="USDT", type_=1, spot=True):
    return {
        "symbol": symbol,
        "baseAsset": base,
        "quoteAsset": quote,
        "type": type_,
        "spotTradingEnable": 1 if spot else 0,
        "filters": [
            {"filterType": "PRICE_FILTER", "minPrice": "0.01"},
            {"filterType": "NOTIONAL", "minNotional": "5.0"},
        ],
    }


def sample_symbols_response():
    """Envelope-wrapped symbols response (like /open/v1/common/symbols)."""
    return {
        "code": 0,
        "msg": "Success",
        "data": {
            "list": [
                sample_symbol_entry("BTC_USDT", "BTC", "USDT", 1),
                sample_symbol_entry("ETH_USDT", "ETH", "USDT", 1),
                sample_symbol_entry("SUI_USDT", "SUI", "USDT", 1),
                sample_symbol_entry("USDT_IDR", "USDT", "IDR", 1),     # stablecoin base -> filtered out
                sample_symbol_entry("BTC_IDR", "BTC", "IDR", 1),
                sample_symbol_entry("TKO_IDR", "TKO", "IDR", 3),
                sample_symbol_entry("HALTED_USDT", "HALTED", "USDT", 1, spot=False),
            ],
            "timestamp": 1700000000000,
        },
    }


def sample_ticker_list():
    """Bare-array ticker response (like /api/v3/ticker/24hr without symbol)."""
    return [
        {"symbol": "BTCUSDT", "lastPrice": "63000", "priceChangePercent": "1.23",
         "priceChange": "700", "highPrice": "64000", "lowPrice": "61000",
         "volume": "1000", "quoteVolume": "63000000", "count": 12345},
        {"symbol": "ETHUSDT", "lastPrice": "3200", "priceChangePercent": "-0.5",
         "priceChange": "-16", "highPrice": "3300", "lowPrice": "3100",
         "volume": "5000", "quoteVolume": "16000000", "count": 5000},
        {"symbol": "SUIUSDT", "lastPrice": "1.23", "priceChangePercent": "3.2",
         "priceChange": "0.04", "highPrice": "1.25", "lowPrice": "1.18",
         "volume": "2000000", "quoteVolume": "2460000", "count": 8000},
        {"symbol": "BTCIDR", "lastPrice": "960000000", "priceChangePercent": "0.8",
         "priceChange": "7000000", "highPrice": "970000000", "lowPrice": "940000000",
         "volume": "50", "quoteVolume": "48000000000", "count": 300},
        {"symbol": "HALTEDUSDT", "lastPrice": "1.0", "priceChangePercent": "0",
         "priceChange": "0", "highPrice": "1.0", "lowPrice": "1.0",
         "volume": "0", "quoteVolume": "0", "count": 0},
    ]


def sample_kline_rows(symbol="BTCUSDT"):
    """Bare-array klines response in Binance-style row format."""
    rows = []
    for i in range(60):
        base = 100 + i * 0.5
        rows.append([
            1700000000000 + i * 3600_000,
            str(base),          # open
            str(base + 1),      # high
            str(base - 1),      # low
            str(base + 0.5),    # close
            "1500",             # volume
            1700000000000 + (i + 1) * 3600_000,
            "1500000",          # quoteVolume
            "300",              # trades
            "1000",
            "1000000",
            "0",
        ])
    return rows
