"""Shared Freqtrade-style exit helpers for the paper & real engines.

Two pure decision functions used identically by ``crypto_paper`` and
``crypto_real`` so their exits never drift apart:

* :func:`trailing_stop_effective` — dynamic stop-loss that only starts moving
  once floating profit passes an optional trigger %, then trails a fixed %
  below the highest price (or the legacy max(ATR×mult, entry×min%) distance).
* :func:`dynamic_roi_exit` — time-based early exit (Freqtrade "minimal_roi"):
  once a position is old enough AND sitting at (at least) a thin profit, close
  it to free capital instead of waiting for a full take-profit.

Both read settings at call time so a config change applies on the next cycle,
and both are pure functions of ``(pos, price)`` → unit-testable without DB/async.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

# Exit reason persisted to positions / shown in stats & Telegram.
EXIT_ROI = "ROI"


def parse_minimal_roi_tiers(raw: str) -> list[tuple[int, float]]:
    """Parse ``"120:1.0, 240:0.8"`` → ``[(120, 1.0), (240, 0.8)]``.

    Minutes are int, profit is a percent (non-negative). Bad entries are
    skipped; the result is sorted ascending by minutes.
    """
    tiers: list[tuple[int, float]] = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        minutes_raw, pct_raw = part.split(":", 1)
        try:
            minutes = int(minutes_raw.strip())
            pct = float(pct_raw.strip())
        except (TypeError, ValueError):
            logger.warning(f"Ignoring invalid ROI tier {part!r} "
                           f"(expected 'minutes:profit_pct')")
            continue
        if minutes < 0 or pct < 0:
            logger.warning(f"Ignoring negative ROI tier {part!r}")
            continue
        tiers.append((minutes, pct))
    return sorted(tiers)


def trailing_stop_effective(pos, price: float, settings=None) -> tuple[Optional[float], float]:
    """Compute the effective stop-loss for an open position.

    Returns ``(effective_sl, highest_seen)``. ``highest_seen`` is the running
    peak including the current price, ready to persist onto the position.

    Rules (Freqtrade-style):
    * trailing disabled  → effective SL is just the static ``stop_loss``.
    * ``trailing_only_after_pct > 0`` → trailing arms only once the PEAK
      (``highest_price``) has reached that floating-profit % (matches Freqtrade
      "trailing_only_offset_is_reached": once the offset is touched, the stop
      keeps trailing on pullbacks — it does NOT disarm when price retraces).
    * Once trailing is active, the distance below the peak is either
      ``highest × trailing_pct%`` (when set, Freqtrade "trailing_stop_positive")
      or the legacy ``max(ATR×mult, entry×min%)``.
    * The trailing stop is never below the original ``stop_loss``.
    """
    settings = settings or get_settings()
    entry = pos.entry_price or price
    sl = pos.stop_loss
    highest = max(pos.highest_price or entry, price)

    # ── Auto BEP (Break-Even Point) ──────────────────────────────────
    # If auto-BEP is enabled and peak profit touches bep_trigger_pct (or 50% to TP1),
    # establish a baseline stop-loss at:
    # - LONG : entry * (1 + bep_buffer_pct/100) (default +0.45% offset)
    # - SHORT: entry * (1 - bep_buffer_pct/100) (default -0.45% offset)
    # This guarantees that once in profit, the SL covers round-trip fees (0.10% open + 0.10% close = 0.20%)
    # plus market sell slippage (0.25%) for a true risk-free break-even.
    bep_floor: Optional[float] = None
    if getattr(settings, "crypto_real_bep_enabled", False) and entry:
        trigger_pct = getattr(settings, "crypto_real_bep_trigger_pct", 0.8)
        buffer_pct = getattr(settings, "crypto_real_bep_buffer_pct", 0.45)
        side = (getattr(pos, "side", None) or getattr(pos, "direction", "LONG") or "LONG").upper()
        tp1 = getattr(pos, "take_profit_1", None)

        if side == "SHORT":
            # For SHORT, profit is when price drops below entry
            lowest = min(getattr(pos, "lowest_price", entry) or entry, price)
            profit_pct = (entry - lowest) / entry * 100.0
            # 50% distance towards TP1 trigger check
            half_tp1_pct = ((entry - tp1) / entry * 100.0 * 0.5) if (tp1 and tp1 < entry) else None
            effective_trigger = min(trigger_pct, half_tp1_pct) if half_tp1_pct is not None else trigger_pct
            if profit_pct >= effective_trigger:
                bep_floor = entry * (1.0 - buffer_pct / 100.0)
        else:
            # For LONG (spot default)
            peak_profit_pct = (highest - entry) / entry * 100.0
            # 50% distance towards TP1 trigger check
            half_tp1_pct = ((tp1 - entry) / entry * 100.0 * 0.5) if (tp1 and tp1 > entry) else None
            effective_trigger = min(trigger_pct, half_tp1_pct) if half_tp1_pct is not None else trigger_pct
            if peak_profit_pct >= effective_trigger:
                bep_floor = entry * (1.0 + buffer_pct / 100.0)

    is_short = (getattr(pos, "side", None) or getattr(pos, "direction", "LONG") or "LONG").upper() == "SHORT"

    if not settings.crypto_real_trailing_enabled:
        if is_short:
            effective_sl = min(sl, bep_floor) if (sl and bep_floor) else (bep_floor or sl)
        else:
            effective_sl = max(sl, bep_floor) if (sl and bep_floor) else (bep_floor or sl)
        return effective_sl, highest

    if settings.crypto_real_trailing_only_after_pct > 0:
        peak_profit_pct = (highest - entry) / entry * 100.0 if entry else 0.0
        if peak_profit_pct < settings.crypto_real_trailing_only_after_pct:
            if is_short:
                effective_sl = min(sl, bep_floor) if (sl and bep_floor) else (bep_floor or sl)
            else:
                effective_sl = max(sl, bep_floor) if (sl and bep_floor) else (bep_floor or sl)
            return effective_sl, highest  # peak hasn't hit trailing offset yet

    # Distance below the peak:
    #  * trailing_pct > 0 → Freqtrade "trailing_stop_positive": % of the peak
    #    (e.g. 1.5 → stop 1.5% below the highest price). This REPLACES the
    #    ATR distance when configured.
    #  * otherwise → legacy max(ATR×mult, entry×min%) so low-ATR coins keep a
    #    meaningful cushion.
    if settings.crypto_real_trailing_pct > 0:
        distance = highest * (settings.crypto_real_trailing_pct / 100.0)
    else:
        atr = pos.atr_value or (entry * 0.02)
        distance = max(
            atr * settings.crypto_real_trailing_mult,
            entry * (settings.crypto_real_trailing_min_pct / 100.0),
        )

    trailing_stop = highest - distance
    if is_short:
        candidates = [val for val in (sl, bep_floor) if val is not None]
        return min(candidates) if candidates else None, highest
    else:
        candidates = [val for val in (sl, bep_floor, trailing_stop) if val is not None]
        return max(candidates) if candidates else None, highest


def dynamic_roi_exit(pos, price: float, settings=None) -> Optional[str]:
    """Freqtrade ``minimal_roi``: close an old, thin-profit position early.

    Iterates the configured tiers in ascending age order; the FIRST tier whose
    age is reached applies — exit when floating profit ≥ that tier's %. Returns
    ``EXIT_ROI`` or ``None``. Off when ``crypto_real_dynamic_roi_enabled`` is
    False (legacy behaviour). Positions without a ``created_at`` never exit via
    ROI (age unknown → treated as fresh).
    """
    settings = settings or get_settings()
    if not settings.crypto_real_dynamic_roi_enabled:
        return None

    entry = pos.entry_price or price
    if not entry:
        return None

    created = getattr(pos, "created_at", None)
    if created is None:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    open_minutes = (datetime.now(timezone.utc) - created).total_seconds() / 60.0
    if open_minutes < 0:
        open_minutes = 0.0

    tiers = parse_minimal_roi_tiers(settings.crypto_real_dynamic_roi_tiers)
    if not tiers:
        tiers = [(int(settings.crypto_real_dynamic_roi_min),
                  float(settings.crypto_real_dynamic_roi_percent))]

    profit_pct = (price - entry) / entry * 100.0
    # Applicable tier = the one with the largest age whose minutes are reached
    # (Freqtrade semantics: the profit threshold loosens as time passes). Tiers
    # are expected to decrease (or stay equal) in min_profit over time.
    applicable = None
    for minutes, min_profit in tiers:
        if open_minutes >= minutes:
            applicable = (minutes, min_profit)
        else:
            break  # tiers sorted ascending → no later tier is reached either
    if applicable is None:
        return None
    return EXIT_ROI if profit_pct >= applicable[1] else None