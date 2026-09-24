"""Unit tests for crypto trade forensics & journaling service."""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.crypto_journal import (
    append_to_journal_file,
    build_entry_dossier,
    build_exit_dossier,
    record_bep_activation,
    record_partial_tp1_fill,
    record_trailing_update,
    update_in_trade_telemetry,
)


def test_build_entry_dossier():
    candidate = {
        "symbol": "POL_USDT",
        "display": "POL/USDT",
        "score": 85.0,
        "score_breakdown": {"trend": 35.0, "volume": 25.0, "volatility": 25.0},
        "tf_summaries": {
            "1h": {
                "price": 0.25,
                "ema20": 0.248,
                "rsi": 54.0,
                "macd_state": "bullish",
                "relative_volume": 1.8,
                "atr": 0.008,
                "trend": "bullish",
                "at_high": False,
            },
            "15m": {
                "trend": "bullish",
                "macd_state": "bullish",
                "rsi": 58.0,
            },
        },
        "price_levels": {
            "entry_ideal": 0.249,
            "take_profit_1": 0.260,
            "take_profit_2": 0.270,
            "risk_reward": 2.5,
            "entry_note": "Pullback test to EMA20",
        },
        "ticker": {
            "quoteVolume": 1500000.0,
            "priceChangePercent": 3.2,
        },
        "ai_verdict": {
            "verdict": "STRONG_WATCH",
            "confidence": 88,
            "reason": "Strong continuation after EMA20 retest",
        },
    }

    btc_cand = {
        "symbol": "BTC_USDT",
        "price": 68000.0,
        "score": 75.0,
        "tf_summaries": {
            "1h": {
                "price": 68000.0,
                "trend": "bullish",
                "macd_state": "bullish",
                "rsi": 56.0,
            }
        },
    }

    dossier = build_entry_dossier(
        candidate=candidate,
        exec_price=0.250,
        initial_sl=0.2425,
        qty_filled=100.0,
        invested=25.0,
        quote="USDT",
        btc_candidate=btc_cand,
        execution_strategy="PULLBACK",
    )

    assert dossier["version"] == "1.0"
    entry = dossier["entry_snapshot"]
    assert entry["symbol"] == "POL_USDT"
    assert entry["strategy"] == "PULLBACK"
    assert entry["entry_price"] == 0.250
    assert entry["quantity"] == 100.0
    assert entry["technicals_1h"]["rsi"] == 54.0
    assert entry["technicals_1h"]["distance_to_ema20_pct"] == pytest.approx(0.81, abs=0.05)
    assert entry["technicals_15m"]["trend"] == "bullish"
    assert entry["market_context"]["btc"]["btc_price"] == 68000.0
    assert entry["planned_levels"]["sl_dist_pct"] == -3.0
    assert entry["ai_verdict"]["verdict"] == "STRONG_WATCH"


def test_in_trade_telemetry_tracking():
    pos = SimpleNamespace(
        entry_price=10.0,
        trade_metadata={},
    )

    # 1. Price rises to 10.5 (+5%)
    update_in_trade_telemetry(pos, 10.5)
    telemetry = pos.trade_metadata["telemetry"]
    assert telemetry["highest_price"] == 10.5
    assert telemetry["max_floating_profit_pct"] == 5.0
    assert telemetry["lowest_price"] == 10.0

    # 2. Price dips to 9.8 (-2%)
    update_in_trade_telemetry(pos, 9.8)
    assert telemetry["highest_price"] == 10.5
    assert telemetry["lowest_price"] == 9.8
    assert telemetry["max_floating_loss_pct"] == -2.0

    # 3. Trailing update
    record_trailing_update(pos, old_sl=9.5, new_sl=10.1, trigger_price=10.6)
    assert len(telemetry["trailing_updates"]) == 1
    assert telemetry["trailing_updates"][0]["new_sl"] == 10.1

    # 4. BEP activation
    record_bep_activation(pos, lock_price=10.12, trigger_price=10.3)
    assert telemetry["bep_activated"] is True
    assert telemetry["bep_lock_price"] == 10.12


def test_build_exit_dossier_and_journal_file(tmp_path):
    entry_time = datetime.now(timezone.utc) - timedelta(hours=1, minutes=30)
    pos = SimpleNamespace(
        id="pos-test-123",
        symbol="POL_USDT",
        display="POL/USDT",
        mode="REAL",
        entry_price=1.0,
        quantity=20.0,
        invested=20.0,
        created_at=entry_time,
        closed_at=datetime.now(timezone.utc),
        exit_reason="SL",
        realized_pnl=-0.70,
        trade_metadata={
            "telemetry": {
                "highest_price": 1.018,
                "max_floating_profit_pct": 1.8,
                "lowest_price": 0.97,
                "max_floating_loss_pct": -3.0,
                "bep_activated": False,
                "trailing_updates": [],
            }
        },
    )

    exit_dossier = build_exit_dossier(
        pos=pos,
        exit_price=0.97,
        action="SL",
        cost_basis=20.0,
        proceeds=19.4,
        pnl=-0.70,
        fee_rate=0.005,
        est_entry_fee=0.10,
        est_exit_fee=0.097,
        total_fees=0.197,
    )

    assert exit_dossier["duration_minutes"] >= 89.0
    assert "1 jam 30 menit" in exit_dossier["duration_formatted"]
    assert exit_dossier["gross_move_pct"] == -3.0
    assert exit_dossier["fees"]["total_fees"] == 0.197
    assert exit_dossier["post_mortem"]["tag"] == "GAIN_REVERSAL"
    assert "Pertimbangkan aktivasi BEP lebih awal" in exit_dossier["post_mortem"]["diagnosis"]

    # Test file journaling
    journal_file = str(tmp_path / "trade_journal.jsonl")
    ok = append_to_journal_file(pos, journal_path=journal_file)
    assert ok is True

    # Verify journal file content
    with open(journal_file, "r") as f:
        lines = f.readlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["symbol"] == "POL_USDT"
    assert record["dossier"]["exit_snapshot"]["post_mortem"]["tag"] == "GAIN_REVERSAL"
