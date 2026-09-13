"""Tests for the Freqtrade-style liquidity filters (app/services/crypto_filters.py)."""

import pytest

from app.config import get_settings
from app.services.crypto_filters import (
    check_spread,
    check_volume_consistency,
    spread_pct,
)


def make_ticker(bid=100.0, ask=100.4):
    return {"bidPrice": bid, "askPrice": ask, "lastPrice": 100.0}


def make_candles(volumes):
    return [{"volume": float(v)} for v in volumes]


# ── spread_pct ───────────────────────────────────────────────────────


class TestSpreadPct:
    def test_normal(self):
        assert spread_pct(make_ticker(100.0, 100.4)) == pytest.approx(0.4)

    def test_zero_spread(self):
        assert spread_pct(make_ticker(100.0, 100.0)) == 0.0

    def test_missing_bid(self):
        assert spread_pct({"askPrice": 100.4}) is None

    def test_missing_ask(self):
        assert spread_pct({"bidPrice": 100.0}) is None

    def test_zero_bid(self):
        assert spread_pct({"bidPrice": 0, "askPrice": 10.0}) is None


# ── check_spread ─────────────────────────────────────────────────────


class TestCheckSpread:
    def test_disabled_allows_all(self, monkeypatch):
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "crypto_spread_filter_enabled", False)
        res = check_spread(make_ticker(100.0, 100.4))
        assert res.ok and res.key == "spread"

    def test_within_tolerance(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "crypto_spread_max_pct", 0.5)
        res = check_spread(make_ticker(100.0, 100.4))
        assert res.ok
        assert res.detail["spread_pct"] == pytest.approx(0.4)

    def test_over_tolerance(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "crypto_spread_max_pct", 0.5)
        res = check_spread(make_ticker(100.0, 101.0))  # 1% spread
        assert not res.ok
        assert res.key == "spread"
        assert "spread" in res.reason

    def test_missing_data_allows_through(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "crypto_spread_max_pct", 0.5)
        res = check_spread({"lastPrice": 100.0})
        assert res.ok and res.key == "spread_missing"


# ── check_volume_consistency ─────────────────────────────────────────


class TestVolumeConsistency:
    def test_disabled_allows_all(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "crypto_volume_consistency_enabled", False)
        res = check_volume_consistency({"1h": make_candles([1.0, 100.0, 1.0])})
        assert res.ok

    def test_flat_volume_passes(self, monkeypatch):
        gs = get_settings()
        monkeypatch.setattr(gs, "crypto_volume_consistency_max_spike_ratio", 3.0)
        monkeypatch.setattr(gs, "crypto_volume_consistency_max_single_share", 0.35)
        res = check_volume_consistency({"1h": make_candles([100.0] * 24)})
        assert res.ok

    def test_single_dominant_spike_fails(self, monkeypatch):
        gs = get_settings()
        monkeypatch.setattr(gs, "crypto_volume_consistency_max_spike_ratio", 3.0)
        monkeypatch.setattr(gs, "crypto_volume_consistency_max_single_share", 0.35)
        vols = [10.0] * 23 + [1000.0]  # spike is 100×median & 81% of window
        res = check_volume_consistency({"1h": make_candles(vols)})
        assert not res.ok
        assert res.key == "volume"
        assert "1h" in res.reason

    def test_both_criteria_required(self, monkeypatch):
        """A big candle that is still a minor part of the window passes."""
        gs = get_settings()
        monkeypatch.setattr(gs, "crypto_volume_consistency_max_spike_ratio", 1.1)
        monkeypatch.setattr(gs, "crypto_volume_consistency_max_single_share", 0.60)
        vols = [100.0] * 23 + [120.0]  # ratio 1.2 (>1.1) but share ~5% (<60%)
        res = check_volume_consistency({"1h": make_candles(vols)})
        assert res.ok

    def test_checks_15m_window_too(self, monkeypatch):
        gs = get_settings()
        monkeypatch.setattr(gs, "crypto_volume_consistency_max_spike_ratio", 3.0)
        monkeypatch.setattr(gs, "crypto_volume_consistency_max_single_share", 0.35)
        # 1h window is flat, but the 15m window has one dominant candle.
        res = check_volume_consistency({
            "1h": make_candles([100.0] * 24),
            "15m": make_candles([10.0] * 95 + [1000.0]),
        })
        assert not res.ok
        assert "15m" in res.reason

    def test_short_history_cannot_judge(self, monkeypatch):
        gs = get_settings()
        monkeypatch.setattr(gs, "crypto_volume_consistency_min_bars", 12)
        res = check_volume_consistency({"1h": make_candles([1.0, 500.0])})
        assert res.ok