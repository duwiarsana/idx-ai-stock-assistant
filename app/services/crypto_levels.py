"""Deterministic price levels (entry / take-profit / stop-loss) for a candidate.

Levels are derived purely from the technical indicators computed elsewhere in
this codebase (EMA, ATR, recent swing high/low) — no LLM involvement, fully
reproducible. They are **reference levels for monitoring**, not trading advice.
"""

import logging
from dataclasses import dataclass, field, asdict
from typing import Optional

from app.services.crypto_indicators import recent_high, recent_low, candles_to_closes

logger = logging.getLogger(__name__)

# Multiples used to derive take-profit / stop-loss from ATR.
# Optimised for better win rate: wider SL to avoid premature stop-outs, and a
# TP1 far enough from entry that the trailing stop doesn't shave it before it
# fills. TP1 at 3×ATR ensures profit covers trading fees (~0.2%) + room to breathe.
TP1_ATR_MULT = 3.0  # pullback-in-uptrend TP1 (target = resistance high)
TP2_ATR_MULT = 5.0  # consistent spacing above TP1
# SL dikembalikan ke 2×ATR untuk meminimalisir nilai kerugian per transaksi (SL lebih kecil)
# digabung dengan trailing stop yang lebih lebar agar R:R nominal jauh lebih sehat.
SL_ATR_MULT = 2.0  # diubah dari 3.0 menjadi 2.0 untuk memperkecil kerugian
# Breakout TP1 uses a WIDER ATR multiplier so the R:R against the 3×ATR stop is
# >= 1.5 — matching the real-trading entry gate (CRYPTO_REAL_ENTRY_MIN_RISK_REWARD).
# SL=3×ATR + TP1=4.5×ATR → R:R = 1.5. Without this the breakout branch produced
# TP1=3×ATR vs SL=3×ATR (R:R = 1.0) and every breakout candidate was rejected at
# the gate, so the bot never auto-opened the strongest momentum setups.
BREAKOUT_TP1_ATR_MULT = 4.5


@dataclass
class PriceLevels:
    entry: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    stop_loss: Optional[float] = None
    risk_reward: Optional[float] = None
    # Fee/slippage-adjusted R:R for reporting (never used as a gate).
    risk_reward_net: Optional[float] = None
    atr: Optional[float] = None
    entry_note: str = ""
    tp1_note: str = ""
    tp2_note: str = ""
    sl_note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def is_complete(self) -> bool:
        return all(
            v is not None
            for v in (self.entry, self.take_profit_1, self.take_profit_2, self.stop_loss)
        )


def compute_price_levels(
    tf_summaries: dict[str, dict],
    candles_1h: list[dict],
    ticker: Optional[dict] = None,
    tp1_mult: float = TP1_ATR_MULT,
    tp2_mult: float = TP2_ATR_MULT,
    sl_mult: float = SL_ATR_MULT,
    breakout_tp1_mult: float = BREAKOUT_TP1_ATR_MULT,
) -> PriceLevels:
    """Compute entry / TP1 / TP2 / SL from the 1h timeframe summary + klines.

    Strategy (momentum, breakout-oriented):
    * If price is above the recent high → trend-riding: entry = current price,
      TP1 = +breakout_tp1_mult×ATR, TP2 = +tp2_mult×ATR, SL = -sl_mult×ATR.
      The wider breakout TP1 keeps R:R >= 1.5 against the 3×ATR SL so the
      strongest momentum setups pass the real-trading entry gate.
    * If price is below the recent high (approaching resistance) → range: entry
      near the EMA20 pullback, TP1 = recent high, TP2 = +tp2_mult×ATR past the
      high, SL = below recent low.
    """
    s1h = tf_summaries.get("1h") or {}
    s15 = tf_summaries.get("15m") or {}
    s5 = tf_summaries.get("5m") or {}

    price = s1h.get("price")
    atr = s1h.get("atr")
    if not price:
        return PriceLevels()

    # Prefer a fresh 5m/15m ATR; fall back to 1h ATR.
    atr = atr or s15.get("atr") or s5.get("atr")
    if not atr:
        # ATR is always available on our indicator summaries; guard anyway.
        atr = price * 0.01

    closes = candles_to_closes(candles_1h) if candles_1h else []
    high = recent_high(closes, 24) if closes else None
    low = recent_low(closes, 24) if closes else None

    ema20 = s1h.get("ema20")
    at_high = bool(s1h.get("at_high"))
    above_high = at_high or (high is not None and price >= high)

    levels = PriceLevels(entry=price)

    # Hard cap on initial Stop Loss: maximum allowed distance from entry (default 3.0%)
    max_sl_pct = 3.0
    try:
        from app.config import get_settings
        max_sl_pct = getattr(get_settings(), "crypto_real_max_sl_pct", 3.0)
    except Exception:
        pass
    hard_sl_floor = price * (1.0 - max_sl_pct / 100.0)

    if above_high and high is not None:
        # Breakout / above resistance — ride the trend.
        # TP1 uses the wider breakout multiplier so R:R vs SL stays >= 1.5
        # (SL = 3×ATR, TP1 = 4.5×ATR → R:R = 1.5) and the entry gate passes.
        tp1_price = price + breakout_tp1_mult * atr
        tp2_price = price + tp2_mult * atr
        sl_price = max(price - sl_mult * atr, hard_sl_floor)
        
        # Ensure TP1 floor is at least 3.5% above entry so trades can ride trends
        # while Auto BEP (+1.5%) protects capital and trailing stop locks profit.
        min_tp1 = price * 1.035
        if tp1_price < min_tp1:
            tp1_price = min_tp1
            levels.tp1_note = f"TP1 = min(3.5%, {breakout_tp1_mult}×ATR)"
        
        levels.take_profit_1 = tp1_price
        levels.take_profit_2 = tp2_price
        levels.stop_loss = sl_price
        levels.entry_note = "Breakout — entry di harga pasar"
        levels.tp1_note = f"TP1 = harga + {breakout_tp1_mult}×ATR (breakout, R:R>=1.5)"
        levels.tp2_note = f"TP2 = harga + {tp2_mult}×ATR (level 2)"
        levels.sl_note = f"SL = harga - {sl_mult}×ATR (cap -{max_sl_pct}%)"
    else:
        # Range — buy near support / EMA pullback, target the resistance high.
        if high is not None:
            tp1_price = high
            # Ensure TP1 floor is at least 3.5% above entry
            min_tp1 = price * 1.035
            if tp1_price < min_tp1:
                tp1_price = min_tp1
                levels.tp1_note = f"TP1 = max(resistance, 3.5%)"
            levels.take_profit_1 = tp1_price
            levels.tp1_note = levels.tp1_note if hasattr(levels, 'tp1_note') else "TP1 = resistance terdekat (min 3.5%)"
        else:
            tp1_price = price + tp1_mult * atr
            min_tp1 = price * 1.035
            if tp1_price < min_tp1:
                tp1_price = min_tp1
                levels.tp1_note = f"TP1 = min(3.5%, {tp1_mult}×ATR)"
            levels.take_profit_1 = tp1_price
            levels.tp1_note = levels.tp1_note if hasattr(levels, 'tp1_note') else f"TP1 = harga + {tp1_mult}×ATR"

        levels.take_profit_2 = (high or price) + tp2_mult * atr
        levels.tp2_note = f"TP2 = +{tp2_mult}×ATR di atas resistance"

        if low is not None:
            raw_sl = min(low, (price - sl_mult * atr))
            levels.stop_loss = max(raw_sl, hard_sl_floor)
            levels.sl_note = f"SL = di bawah recent low (cap -{max_sl_pct}%)"
        else:
            levels.stop_loss = max(price - sl_mult * atr, hard_sl_floor)
            levels.sl_note = f"SL = harga - {sl_mult}×ATR (cap -{max_sl_pct}%)"

        if ema20 and ema20 < price:
            levels.entry = ema20
            levels.entry_note = "Entry ideal = pullback ke EMA20"
        else:
            levels.entry_note = "Entry = area support saat ini"

    # Risk/reward ratio: (TP1 - entry) / (entry - SL)
    if levels.is_complete() and levels.entry and levels.stop_loss and levels.entry > levels.stop_loss:
        risk = levels.entry - levels.stop_loss
        reward = levels.take_profit_1 - levels.entry
        levels.risk_reward = round(reward / risk, 2) if risk > 0 else None
        # Net R:R (informational only): subtract round-trip taker fees (~0.1% ×
        # 2) from the reward and add them to the risk so alerts/reports show a
        # realistic expectancy. The hard entry gate keeps using the gross ratio
        # (CRYPTO_REAL_ENTRY_MIN_RISK_REWARD) — a strict fee-adjusted gate is
        # mathematically incompatible with equal ATR multipliers (any TP1/SL
        # multiple that yields exactly 1.5 gross will dip below it net of fees).
        round_trip_fee_pct = 0.2
        risk_pct = risk / levels.entry * 100.0
        reward_pct = reward / levels.entry * 100.0
        net_reward = reward_pct - round_trip_fee_pct
        net_risk = risk_pct + round_trip_fee_pct
        if net_reward > 0 and net_risk > 0:
            levels.risk_reward_net = round(net_reward / net_risk, 2)
    
    # Store ATR for trailing stop calculation
    levels.atr = atr

    return levels