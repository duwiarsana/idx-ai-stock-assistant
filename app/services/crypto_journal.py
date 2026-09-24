"""Crypto Trade Forensics & Journaling Service.

Records deep technical snapshots at entry, in-trade telemetry (peaks, troughs,
trailing SL updates, BEP activations), and comprehensive post-mortem analyses
upon trade exit. Writes to PostgreSQL and appends to data/trade_journal.jsonl.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_JOURNAL_PATH = "data/trade_journal.jsonl"


def build_entry_dossier(
    candidate: dict,
    exec_price: float,
    initial_sl: float,
    qty_filled: float,
    invested: float,
    quote: str,
    btc_candidate: Optional[dict] = None,
    execution_strategy: str = "PULLBACK",
) -> dict[str, Any]:
    """Assemble a comprehensive technical snapshot at the moment of entry."""
    s1h = (candidate.get("tf_summaries") or {}).get("1h") or {}
    s15 = (candidate.get("tf_summaries") or {}).get("15m") or {}
    s4h = (candidate.get("tf_summaries") or {}).get("4h") or {}
    levels = candidate.get("price_levels") or {}
    ticker = candidate.get("ticker") or {}

    ema20_1h = s1h.get("ema20")
    dist_ema20_pct = None
    if ema20_1h and exec_price:
        dist_ema20_pct = round(((exec_price - ema20_1h) / ema20_1h) * 100.0, 2)

    tp1 = levels.get("take_profit_1")
    tp2 = levels.get("take_profit_2")
    sl_dist_pct = round(((initial_sl - exec_price) / exec_price) * 100.0, 2) if exec_price else None
    tp1_dist_pct = round(((tp1 - exec_price) / exec_price) * 100.0, 2) if (tp1 and exec_price) else None
    tp2_dist_pct = round(((tp2 - exec_price) / exec_price) * 100.0, 2) if (tp2 and exec_price) else None

    # BTC context snapshot
    btc_ctx: dict[str, Any] = {}
    if btc_candidate:
        btc_1h = (btc_candidate.get("tf_summaries") or {}).get("1h") or {}
        btc_ctx = {
            "btc_price": btc_candidate.get("price") or btc_1h.get("price"),
            "btc_score": btc_candidate.get("score"),
            "btc_trend_1h": btc_1h.get("trend"),
            "btc_macd_1h": btc_1h.get("macd_state"),
            "btc_rsi_1h": btc_1h.get("rsi"),
        }

    now_iso = datetime.now(timezone.utc).isoformat()

    return {
        "version": "1.0",
        "entry_snapshot": {
            "timestamp": now_iso,
            "symbol": candidate.get("symbol"),
            "display": candidate.get("display"),
            "strategy": execution_strategy,
            "entry_price": exec_price,
            "quantity": qty_filled,
            "invested": invested,
            "quote": quote,
            "score": candidate.get("score"),
            "score_breakdown": candidate.get("score_breakdown") or {},
            "technicals_1h": {
                "price": s1h.get("price") or exec_price,
                "ema20": ema20_1h,
                "distance_to_ema20_pct": dist_ema20_pct,
                "rsi": s1h.get("rsi"),
                "macd_state": s1h.get("macd_state"),
                "relative_volume": s1h.get("relative_volume"),
                "atr": s1h.get("atr"),
                "trend": s1h.get("trend"),
                "at_high": s1h.get("at_high"),
                "support_level": s1h.get("support"),
                "resistance_level": s1h.get("resistance"),
            },
            "technicals_15m": {
                "trend": s15.get("trend"),
                "macd_state": s15.get("macd_state"),
                "rsi": s15.get("rsi"),
            },
            "technicals_4h": {
                "trend": s4h.get("trend"),
                "macd_state": s4h.get("macd_state"),
                "rsi": s4h.get("rsi"),
            },
            "market_context": {
                "volume_24h": ticker.get("quoteVolume"),
                "price_change_24h": ticker.get("priceChangePercent"),
                "btc": btc_ctx,
            },
            "planned_levels": {
                "entry_ideal": levels.get("entry_ideal"),
                "initial_sl": initial_sl,
                "sl_dist_pct": sl_dist_pct,
                "tp1": tp1,
                "tp1_dist_pct": tp1_dist_pct,
                "tp2": tp2,
                "tp2_dist_pct": tp2_dist_pct,
                "risk_reward": levels.get("risk_reward"),
                "entry_note": levels.get("entry_note"),
            },
            "ai_verdict": candidate.get("ai_verdict") or {},
        },
        "telemetry": {
            "highest_price": exec_price,
            "max_floating_profit_pct": 0.0,
            "lowest_price": exec_price,
            "max_floating_loss_pct": 0.0,
            "trailing_updates": [],
            "bep_activated": False,
            "bep_timestamp": None,
            "bep_lock_price": None,
            "partial_tp1_filled": False,
            "partial_tp1_timestamp": None,
            "partial_tp1_price": None,
            "partial_tp1_pnl": None,
        },
        "exit_snapshot": None,
    }


def _get_or_create_meta(pos) -> dict[str, Any]:
    meta = getattr(pos, "trade_metadata", None)
    if not isinstance(meta, dict):
        meta = {}
        try:
            setattr(pos, "trade_metadata", meta)
        except Exception:
            pass
    return meta


def update_in_trade_telemetry(pos, current_price: float) -> None:
    """Update high-water, low-water, and drawdown metrics in the position metadata."""
    if not pos or not current_price or current_price <= 0:
        return

    meta = _get_or_create_meta(pos)
    telemetry = meta.setdefault("telemetry", {})
    entry_price = getattr(pos, "entry_price", None) or current_price

    telemetry.setdefault("highest_price", entry_price)
    telemetry.setdefault("lowest_price", entry_price)
    telemetry.setdefault("max_floating_profit_pct", 0.0)
    telemetry.setdefault("max_floating_loss_pct", 0.0)

    # Track high-water mark & max floating gain
    prev_high = telemetry.get("highest_price") or entry_price
    if current_price > prev_high:
        telemetry["highest_price"] = current_price
        gain_pct = round(((current_price - entry_price) / entry_price) * 100.0, 2)
        telemetry["max_floating_profit_pct"] = max(telemetry.get("max_floating_profit_pct", 0.0), gain_pct)

    # Track low-water mark & max floating drawdown
    prev_low = telemetry.get("lowest_price") or entry_price
    if current_price < prev_low:
        telemetry["lowest_price"] = current_price
        drawdown_pct = round(((current_price - entry_price) / entry_price) * 100.0, 2)
        telemetry["max_floating_loss_pct"] = min(telemetry.get("max_floating_loss_pct", 0.0), drawdown_pct)


def record_trailing_update(pos, old_sl: float, new_sl: float, trigger_price: float) -> None:
    """Record a Trailing Stop adjustment event."""
    if not pos:
        return
    meta = _get_or_create_meta(pos)
    telemetry = meta.setdefault("telemetry", {})
    updates = telemetry.setdefault("trailing_updates", [])
    now_iso = datetime.now(timezone.utc).isoformat()
    updates.append({
        "timestamp": now_iso,
        "old_sl": old_sl,
        "new_sl": new_sl,
        "trigger_price": trigger_price,
    })


def record_bep_activation(pos, lock_price: float, trigger_price: float) -> None:
    """Record Auto-BEP activation event."""
    if not pos:
        return
    meta = _get_or_create_meta(pos)
    telemetry = meta.setdefault("telemetry", {})
    now_iso = datetime.now(timezone.utc).isoformat()
    telemetry["bep_activated"] = True
    telemetry["bep_timestamp"] = now_iso
    telemetry["bep_lock_price"] = lock_price
    telemetry["bep_trigger_price"] = trigger_price


def record_partial_tp1_fill(pos, price: float, pnl: float, qty_sold: float) -> None:
    """Record Partial TP1 fill event."""
    if not pos:
        return
    meta = _get_or_create_meta(pos)
    telemetry = meta.setdefault("telemetry", {})
    now_iso = datetime.now(timezone.utc).isoformat()
    telemetry["partial_tp1_filled"] = True
    telemetry["partial_tp1_timestamp"] = now_iso
    telemetry["partial_tp1_price"] = price
    telemetry["partial_tp1_pnl"] = pnl
    telemetry["partial_tp1_qty"] = qty_sold


def build_exit_dossier(
    pos,
    exit_price: float,
    action: str,
    cost_basis: float,
    proceeds: float,
    pnl: float,
    fee_rate: float,
    est_entry_fee: float,
    est_exit_fee: float,
    total_fees: float,
) -> dict[str, Any]:
    """Generate final financial analysis and post-mortem diagnosis upon trade exit."""
    meta = _get_or_create_meta(pos)
    telemetry = meta.get("telemetry", {})

    entry_price = pos.entry_price or (cost_basis / pos.quantity if pos.quantity else exit_price)
    gross_move_pct = round(((exit_price - entry_price) / entry_price) * 100.0, 2) if entry_price else 0.0
    net_pnl_pct = round((pnl / cost_basis) * 100.0, 2) if cost_basis else 0.0

    # Duration calculation
    duration_minutes = 0.0
    duration_str = "-"
    created_at = getattr(pos, "created_at", None)
    if created_at:
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        dur_secs = (datetime.now(timezone.utc) - created_at).total_seconds()
        duration_minutes = round(dur_secs / 60.0, 1)
        hours = int(dur_secs // 3600)
        mins = int((dur_secs % 3600) // 60)
        if hours > 0:
            duration_str = f"{hours} jam {mins} menit"
        else:
            duration_str = f"{mins} menit"

    # Automated Post-Mortem Diagnosis
    max_gain = telemetry.get("max_floating_profit_pct", 0.0)
    max_loss = telemetry.get("max_floating_loss_pct", 0.0)
    bep_active = telemetry.get("bep_activated", False)

    diagnosis_tag = "UNKNOWN"
    diagnosis_reason = ""

    action_clean = (action or "").upper()
    if "SL" in action_clean:
        if bep_active or (exit_price >= entry_price):
            diagnosis_tag = "BEP_PROTECTED"
            diagnosis_reason = (
                f"Stop Loss tersentuh di level BEP/Profit Lock. Modal terlindungi dari penurunan lebih dalam."
            )
        elif max_gain >= 1.5:
            diagnosis_tag = "GAIN_REVERSAL"
            diagnosis_reason = (
                f"Harga sempat floating profit hingga +{max_gain:.2f}% sebelum berbalik arah tajam menembus SL. "
                f"Koreksi: Pertimbangkan aktivasi BEP lebih awal saat floating gain mencapai +1.5%."
            )
        elif abs(max_loss) >= 2.5 and max_gain < 0.5:
            diagnosis_tag = "IMMEDIATE_BREAKDOWN"
            diagnosis_reason = (
                f"Harga langsung melemah sejak entry tanpa pantulan berarti (peak gain hanya +{max_gain:.2f}%). "
                f"Kemungkinan level support/EMA20 gagal bertahan atau terseret tren pasar BTC."
            )
        elif "STALE" in action_clean:
            diagnosis_tag = "STALE_TIMEOUT"
            diagnosis_reason = (
                f"Posisi dipangkas setelah stagnan selama {duration_str} dengan floating loss. "
                f"Mencegah modal terkunci dalam pergerakan sideways yang melemah."
            )
        else:
            diagnosis_tag = "STOP_LOSS_HIT"
            diagnosis_reason = (
                f"Stop Loss normal tersentuh di {exit_price:.6f} (-{abs(gross_move_pct):.2f}%). "
                f"Disiplin cut loss sesuai batas toleransi risiko."
            )
    elif "TP" in action_clean:
        diagnosis_tag = "TARGET_HIT"
        diagnosis_reason = (
            f"Target {action_clean} tercapai sempurna. Peak profit mencapai +{max_gain:.2f}%. "
            f"Strategi take-profit berhasil mengamankan profit."
        )
    elif "ROI" in action_clean:
        diagnosis_tag = "DYNAMIC_ROI"
        diagnosis_reason = (
            f"Exit dinamis ROI setelah {duration_str}. Profit tipis diamankan untuk melepaskan alokasi dana."
        )
    else:
        diagnosis_tag = action_clean
        diagnosis_reason = f"Posisi ditutup via {action_clean}."

    exit_dossier = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "exit_action": action,
        "exit_price": exit_price,
        "duration_minutes": duration_minutes,
        "duration_formatted": duration_str,
        "cost_basis": cost_basis,
        "proceeds": proceeds,
        "gross_move_pct": gross_move_pct,
        "fees": {
            "fee_rate": fee_rate,
            "est_entry_fee": est_entry_fee,
            "est_exit_fee": est_exit_fee,
            "total_fees": total_fees,
        },
        "net_pnl": pnl,
        "net_pnl_pct": net_pnl_pct,
        "post_mortem": {
            "tag": diagnosis_tag,
            "peak_floating_profit_pct": max_gain,
            "max_drawdown_pct": max_loss,
            "bep_was_active": bep_active,
            "diagnosis": diagnosis_reason,
        },
    }

    meta["exit_snapshot"] = exit_dossier
    try:
        setattr(pos, "trade_metadata", meta)
    except Exception:
        pass
    return exit_dossier


def append_to_journal_file(
    pos,
    journal_path: str = DEFAULT_JOURNAL_PATH,
) -> bool:
    """Safely append a completed trade dossier as a JSON line into the trade journal."""
    try:
        path = Path(journal_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        meta = _get_or_create_meta(pos)
        journal_record = {
            "id": str(getattr(pos, "id", "")),
            "symbol": getattr(pos, "symbol", ""),
            "display": getattr(pos, "display", ""),
            "mode": getattr(pos, "mode", "REAL"),
            "entry_price": getattr(pos, "entry_price", None),
            "exit_price": getattr(pos, "exit_price", None),
            "quantity": getattr(pos, "quantity", None),
            "invested": getattr(pos, "invested", None),
            "exit_reason": getattr(pos, "exit_reason", None),
            "realized_pnl": getattr(pos, "realized_pnl", None),
            "created_at": getattr(pos, "created_at", None).isoformat() if getattr(pos, "created_at", None) else None,
            "closed_at": getattr(pos, "closed_at", None).isoformat() if getattr(pos, "closed_at", None) else None,
            "dossier": meta,
        }

        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(journal_record, default=str) + "\n")

        logger.info(f"📜 Trade journal logged for {pos.symbol} in {journal_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to append trade journal to {journal_path}: {e}")
        return False
