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
# Optimised for better reward:risk with realistic SL (wider to avoid noise).
# TP1 increased to 2.5×ATR to ensure profit covers trading fees (~0.2%).
TP1_ATR_MULT = 2.5
TP2_ATR_MULT = 4.0
SL_ATR_MULT = 1.5


@dataclass
class PriceLevels:
    entry: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    stop_loss: Optional[float] = None
    risk_reward: Optional[float] = None
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
) -> PriceLevels:
    """Compute entry / TP1 / TP2 / SL from the 1h timeframe summary + klines.

    Strategy (momentum, breakout-oriented):
    * If price is above the recent high → trend-riding: entry = current price,
      TP1 = +tp1_mult×ATR, TP2 = +tp2_mult×ATR, SL = -sl_mult×ATR.
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

    if above_high and high is not None:
        # Breakout / above resistance — ride the trend.
        tp1_price = price + tp1_mult * atr
        tp2_price = price + tp2_mult * atr
        sl_price = price - sl_mult * atr
        
        # Ensure TP1 is at least 2% above entry to cover trading fees (~0.2%)
        min_tp1 = price * 1.02
        if tp1_price < min_tp1:
            tp1_price = min_tp1
            levels.tp1_note = f"TP1 = min(2%, {tp1_mult}×ATR) untuk cover fee"
        
        levels.take_profit_1 = tp1_price
        levels.take_profit_2 = tp2_price
        levels.stop_loss = sl_price
        levels.entry_note = "Breakout — entry di harga pasar"
        levels.tp2_note = f"TP2 = harga + {tp2_mult}×ATR (level 2)"
        levels.sl_note = f"SL = harga - {sl_mult}×ATR (breakout gagal)"
    else:
        # Range — buy near support / EMA pullback, target the resistance high.
        if high is not None:
            tp1_price = high
            # Ensure TP1 is at least 2% above entry to cover trading fees
            min_tp1 = price * 1.02
            if tp1_price < min_tp1:
                tp1_price = min_tp1
                levels.tp1_note = f"TP1 = max(resistance, 2%) untuk cover fee"
            levels.take_profit_1 = tp1_price
            levels.tp1_note = levels.tp1_note if hasattr(levels, 'tp1_note') else "TP1 = resistance terdekat (min 2%)"
        else:
            tp1_price = price + tp1_mult * atr
            min_tp1 = price * 1.02
            if tp1_price < min_tp1:
                tp1_price = min_tp1
                levels.tp1_note = f"TP1 = min(2%, {tp1_mult}×ATR) untuk cover fee"
            levels.take_profit_1 = tp1_price
            levels.tp1_note = levels.tp1_note if hasattr(levels, 'tp1_note') else f"TP1 = harga + {tp1_mult}×ATR"

        levels.take_profit_2 = (high or price) + tp2_mult * atr
        levels.tp2_note = f"TP2 = +{tp2_mult}×ATR di atas resistance"

        if low is not None:
            levels.stop_loss = min(low, (price - sl_mult * atr))
            levels.sl_note = "SL = di bawah recent low"
        else:
            levels.stop_loss = price - sl_mult * atr
            levels.sl_note = f"SL = harga - {sl_mult}×ATR"

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
    
    # Store ATR for trailing stop calculation
    levels.atr = atr

    return levels