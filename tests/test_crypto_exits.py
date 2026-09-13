"""Tests for the shared Freqtrade-style exit helpers (app/services/crypto_exits.py)."""

import pytest
from datetime import datetime, timezone, timedelta

from app.config import get_settings
from app.services.crypto_exits import (
    EXIT_ROI,
    dynamic_roi_exit,
    parse_minimal_roi_tiers,
    trailing_stop_effective,
)


def make_pos(entry=100.0, sl=95.0, atr=2.0, highest=None, created_dt=None):
    class P:
        pass
    p = P()
    p.entry_price = entry
    p.stop_loss = sl
    p.atr_value = atr
    p.highest_price = highest or entry
    p.created_at = created_dt
    return p


# ── parse_minimal_roi_tiers ──────────────────────────────────────────


class TestParseTiers:
    def test_basic(self):
        assert parse_minimal_roi_tiers("120:1.0, 240:0.8") == [(120, 1.0), (240, 0.8)]

    def test_sorts_by_minutes(self):
        assert parse_minimal_roi_tiers("240:0.8,60:2.0") == [(60, 2.0), (240, 0.8)]

    def test_skips_bad_entries(self):
        assert parse_minimal_roi_tiers("120:1.0,abc,x:-1,240:0.8") == [(120, 1.0), (240, 0.8)]

    def test_empty(self):
        assert parse_minimal_roi_tiers("") == []
        assert parse_minimal_roi_tiers("   ") == []


# ── trailing_stop_effective ──────────────────────────────────────────


class TestTrailingStop:
    def test_disabled_returns_static_sl(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "crypto_real_trailing_enabled", False)
        monkeypatch.setattr(get_settings(), "crypto_real_trailing_only_after_pct", 0.0)
        pos = make_pos(entry=100.0, sl=95.0, atr=2.0, highest=105.0)
        sl, highest = trailing_stop_effective(pos, 104.0)
        assert sl == 95.0
        assert highest == 105.0

    def test_trigger_not_reached_uses_static_sl(self, monkeypatch):
        gs = get_settings()
        monkeypatch.setattr(gs, "crypto_real_trailing_enabled", True)
        monkeypatch.setattr(gs, "crypto_real_trailing_only_after_pct", 2.0)
        monkeypatch.setattr(gs, "crypto_real_trailing_pct", 1.5)
        pos = make_pos(entry=100.0, sl=95.0, atr=2.0, highest=101.0)
        sl, _ = trailing_stop_effective(pos, 101.0)  # only +1% → not armed
        assert sl == 95.0

    def test_trigger_reached_trails_pct_below_peak(self, monkeypatch):
        gs = get_settings()
        monkeypatch.setattr(gs, "crypto_real_trailing_enabled", True)
        monkeypatch.setattr(gs, "crypto_real_trailing_only_after_pct", 2.0)
        monkeypatch.setattr(gs, "crypto_real_trailing_pct", 1.5)
        pos = make_pos(entry=100.0, sl=95.0, atr=2.0, highest=105.0)
        # price still +4% (≥ +2%) so trail is armed and rides 1.5% under 105.
        sl, highest = trailing_stop_effective(pos, 104.0)
        assert highest == 105.0
        assert sl == pytest.approx(105.0 * 0.985)

    def test_trailing_never_below_original_sl(self, monkeypatch):
        gs = get_settings()
        monkeypatch.setattr(gs, "crypto_real_trailing_enabled", True)
        monkeypatch.setattr(gs, "crypto_real_trailing_only_after_pct", 0.0)
        monkeypatch.setattr(gs, "crypto_real_trailing_pct", 5.0)  # absurdly wide
        pos = make_pos(entry=100.0, sl=95.0, atr=2.0, highest=100.0)
        sl, _ = trailing_stop_effective(pos, 100.0)
        assert sl >= 95.0

    def test_legacy_atr_distance_when_pct_off(self, monkeypatch):
        gs = get_settings()
        monkeypatch.setattr(gs, "crypto_real_trailing_enabled", True)
        monkeypatch.setattr(gs, "crypto_real_trailing_only_after_pct", 0.0)
        monkeypatch.setattr(gs, "crypto_real_trailing_pct", 0.0)
        monkeypatch.setattr(gs, "crypto_real_trailing_mult", 2.2)
        monkeypatch.setattr(gs, "crypto_real_trailing_min_pct", 2.0)
        pos = make_pos(entry=100.0, sl=95.0, atr=3.0, highest=110.0)
        sl, _ = trailing_stop_effective(pos, 110.0)
        expected = 110.0 - max(3.0 * 2.2, 100.0 * 0.02)  # 2.2×3=6.6 > 2% of entry
        assert sl == pytest.approx(expected)

    def test_min_pct_floor_wins_for_low_atr(self, monkeypatch):
        gs = get_settings()
        monkeypatch.setattr(gs, "crypto_real_trailing_enabled", True)
        monkeypatch.setattr(gs, "crypto_real_trailing_only_after_pct", 0.0)
        monkeypatch.setattr(gs, "crypto_real_trailing_pct", 0.0)
        monkeypatch.setattr(gs, "crypto_real_trailing_mult", 2.2)
        monkeypatch.setattr(gs, "crypto_real_trailing_min_pct", 2.0)
        pos = make_pos(entry=100.0, sl=95.0, atr=0.2, highest=110.0)
        sl, _ = trailing_stop_effective(pos, 110.0)
        expected = 110.0 - max(0.2 * 2.2, 100.0 * 0.02)  # 2.0 > 0.44
        assert sl == pytest.approx(expected)

    def test_tracks_new_high(self, monkeypatch):
        gs = get_settings()
        monkeypatch.setattr(gs, "crypto_real_trailing_enabled", True)
        monkeypatch.setattr(gs, "crypto_real_trailing_only_after_pct", 0.0)
        monkeypatch.setattr(gs, "crypto_real_trailing_pct", 1.5)
        pos = make_pos(entry=100.0, sl=95.0, atr=2.0, highest=100.0)
        _, highest = trailing_stop_effective(pos, 112.0)
        assert highest == 112.0


# ── dynamic_roi_exit ─────────────────────────────────────────────────


def _old_pos(minutes_ago, profit_pct):
    entry = 100.0
    now = datetime.now(timezone.utc)
    return make_pos(
        entry=entry,
        sl=95.0,
        atr=2.0,
        highest=entry * (1 + profit_pct / 100.0),
        created_dt=now - timedelta(minutes=minutes_ago),
    )


class TestDynamicRoi:
    def test_disabled_never_exits(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "crypto_real_dynamic_roi_enabled", False)
        pos = _old_pos(300, 5.0)
        assert dynamic_roi_exit(pos, 105.0) is None

    def test_too_young(self, monkeypatch):
        gs = get_settings()
        monkeypatch.setattr(gs, "crypto_real_dynamic_roi_enabled", True)
        monkeypatch.setattr(gs, "crypto_real_dynamic_roi_tiers", "120:1.0,240:0.8")
        pos = _old_pos(60, 3.0)  # old enough for NEITHER tier profit? no—too young
        assert dynamic_roi_exit(pos, 103.0) is None

    def test_profit_below_threshold(self, monkeypatch):
        gs = get_settings()
        monkeypatch.setattr(gs, "crypto_real_dynamic_roi_enabled", True)
        monkeypatch.setattr(gs, "crypto_real_dynamic_roi_tiers", "120:1.0,240:0.8")
        pos = _old_pos(300, 0.5)  # old, but profit < 0.8
        assert dynamic_roi_exit(pos, 100.5) is None

    def test_both_met_returns_roi(self, monkeypatch):
        gs = get_settings()
        monkeypatch.setattr(gs, "crypto_real_dynamic_roi_enabled", True)
        monkeypatch.setattr(gs, "crypto_real_dynamic_roi_tiers", "120:1.0,240:0.8")
        pos = _old_pos(300, 1.0)
        assert dynamic_roi_exit(pos, 101.0) == EXIT_ROI

    def test_tier_selection_first_age_reached(self, monkeypatch):
        gs = get_settings()
        monkeypatch.setattr(gs, "crypto_real_dynamic_roi_enabled", True)
        monkeypatch.setattr(gs, "crypto_real_dynamic_roi_tiers", "120:5.0,240:0.8")
        pos = _old_pos(300, 1.0)
        # 5h old → second tier (240 min, 0.8%) applies → profit 1% ≥ 0.8 → ROI
        assert dynamic_roi_exit(pos, 101.0) == EXIT_ROI

    def test_break_when_tier_reached_but_profit_too_thin(self, monkeypatch):
        gs = get_settings()
        monkeypatch.setattr(gs, "crypto_real_dynamic_roi_enabled", True)
        monkeypatch.setattr(gs, "crypto_real_dynamic_roi_tiers", "120:1.0,240:0.8")
        pos = _old_pos(130, 0.5)  # ≥120 min but profit 0.5 < 1.0 → wait longer
        assert dynamic_roi_exit(pos, 100.5) is None

    def test_fallback_single_tier_when_no_tiers(self, monkeypatch):
        gs = get_settings()
        monkeypatch.setattr(gs, "crypto_real_dynamic_roi_enabled", True)
        monkeypatch.setattr(gs, "crypto_real_dynamic_roi_tiers", "")
        monkeypatch.setattr(gs, "crypto_real_dynamic_roi_min", 240)
        monkeypatch.setattr(gs, "crypto_real_dynamic_roi_percent", 0.8)
        pos = _old_pos(300, 1.0)
        assert dynamic_roi_exit(pos, 101.0) == EXIT_ROI

    def test_naive_created_at_treated_as_utc(self, monkeypatch):
        gs = get_settings()
        monkeypatch.setattr(gs, "crypto_real_dynamic_roi_enabled", True)
        monkeypatch.setattr(gs, "crypto_real_dynamic_roi_tiers", "240:0.8")
        pos = make_pos(entry=100.0, sl=95.0, atr=2.0,
                       created_dt=datetime(2020, 1, 1, 12, 0))  # naive
        assert dynamic_roi_exit(pos, 101.0) == EXIT_ROI

    def test_missing_created_at_never_exits(self, monkeypatch):
        gs = get_settings()
        monkeypatch.setattr(gs, "crypto_real_dynamic_roi_enabled", True)
        monkeypatch.setattr(gs, "crypto_real_dynamic_roi_tiers", "240:0.8")
        pos = make_pos(entry=100.0, sl=95.0, atr=2.0, created_dt=None)
        assert dynamic_roi_exit(pos, 101.0) is None