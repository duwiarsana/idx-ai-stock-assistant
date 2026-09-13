"""Freqtrade-style liquidity filters for the crypto scanner.

Two pure decision helpers, both config-driven and unit-testable without
network/DB:

* :func:`check_spread` — reject pairs whose best bid/ask spread exceeds the
  configured % (protects market orders from eating a wide spread). Uses the
  24h ticker's ``bidPrice``/``askPrice`` snapshot, so it costs no extra API
  call. Pairs without bid/ask data are allowed through (can't measure).
* :func:`check_volume_consistency` — reject pairs whose recent volume is
  concentrated in a single candle spike (pump & dump) instead of being spread
  evenly across the window. Evaluated on the last N hours of 1h candles and on
  the equivalent 15m window. A candle is treated as a dominant spike when BOTH
  its ratio to the window median AND its share of total window volume exceed
  the configured bounds.
"""

import logging
import statistics
from dataclasses import dataclass
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class FilterResult:
    """Outcome of one liquidity check."""

    ok: bool
    key: str = ""          # "spread" / "volume" / "spread_missing"
    detail: Optional[dict] = None
    reason: str = ""


def spread_pct(ticker: dict) -> Optional[float]:
    """Best bid/ask spread as a % of the best bid. ``None`` when unmeasurable."""
    bid = ticker.get("bidPrice")
    ask = ticker.get("askPrice")
    if not bid or not ask or bid <= 0 or ask <= 0:
        return None
    return (ask - bid) / bid * 100.0


def check_spread(ticker: dict, settings=None) -> FilterResult:
    """Reject a pair when its quoted spread exceeds ``crypto_spread_max_pct``."""
    settings = settings or get_settings()
    if not settings.crypto_spread_filter_enabled:
        return FilterResult(ok=True, key="spread")

    pct = spread_pct(ticker)
    if pct is None:
        return FilterResult(
            ok=True, key="spread_missing", reason="no bid/ask in ticker — cannot measure"
        )

    limit = float(settings.crypto_spread_max_pct)
    ok = pct <= limit
    return FilterResult(
        ok=ok,
        key="spread",
        detail={"spread_pct": round(pct, 4), "max_spread_pct": limit},
        reason="" if ok else f"spread {pct:.3f}% > max {limit}%",
    )


def _dominant_spike_check(volumes: list[float], max_spike_ratio: float,
                          max_single_share: float) -> Optional[dict]:
    """Return the spike info when a single candle dominates the window."""
    vols = [v for v in volumes if v and v > 0]
    if len(vols) < 2:
        return None
    median = statistics.median(vols)
    if median <= 0:
        return None
    peak = max(vols)
    total = sum(vols)
    spike_ratio = peak / median
    share = peak / total if total > 0 else 1.0
    # Both must overshoot: one big candle in a quiet market is fine; a candle
    # that is both huge vs its peers AND a large fraction of the window (no
    # broad participation) signals an artificial pump.
    if spike_ratio > max_spike_ratio and share > max_single_share:
        return {
            "spike_ratio": round(spike_ratio, 2),
            "share": round(share, 3),
            "peak_volume": peak,
        }
    return None


def check_volume_consistency(tf_klines: dict, settings=None) -> FilterResult:
    """Reject a pair when recent volume distribution is spike-dominated."""
    settings = settings or get_settings()
    if not settings.crypto_volume_consistency_enabled:
        return FilterResult(ok=True, key="volume")

    hours = int(settings.crypto_volume_consistency_window_hours)
    max_spike_ratio = float(settings.crypto_volume_consistency_max_spike_ratio)
    max_single_share = float(settings.crypto_volume_consistency_max_single_share)
    min_bars = int(settings.crypto_volume_consistency_min_bars)

    windows = []
    if tf_klines.get("1h"):
        windows.append(("1h", tf_klines["1h"][-hours:]))
    if tf_klines.get("15m"):
        windows.append(("15m", tf_klines["15m"][-(hours * 4):]))

    worst = None
    for tf, candles in windows:
        volumes = [c.get("volume") for c in candles if isinstance(c, dict)]
        volumes = [v for v in volumes if v is not None]
        if len(volumes) < min_bars:
            continue
        spike = _dominant_spike_check(volumes, max_spike_ratio, max_single_share)
        if spike:
            spike = {"tf": tf, **spike}
            if worst is None or spike["share"] > worst["share"]:
                worst = spike

    if worst is not None:
        reason = (
            f"volume spike {worst['tf']}: {worst['spike_ratio']}×median, "
            f"{worst['share'] * 100:.0f}% of window in one candle"
        )
        return FilterResult(ok=False, key="volume", detail=worst, reason=reason)
    return FilterResult(ok=True, key="volume")