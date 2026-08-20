"""Advanced Stock Analysis Engine — Weighted scoring with signal validation.

Replaces ad-hoc indicator interpretation with a deterministic, reproducible
scoring system.  Every indicator is normalised to [0, 1], weighted, and
combined into a composite score (0–100).

Design choices
--------------
* All scoring is *deterministic* — no LLM in the loop.
* The LLM receives the pre-computed score card and **explains** it, rather
  than inventing its own numbers.
* Weights are configurable via the ``INDICATOR_WEIGHTS`` dict.

Enhanced Features (Phase 1)
---------------------------
* Integration with EnhancedTechnicalEngine (130+ indicators)
* Multi-timeframe analysis support
* Divergence detection (RSI, MACD)
* Candlestick pattern recognition
* Professional-grade support/resistance levels
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field, asdict
from typing import Optional

import numpy as np
import pandas as pd

from app.services.enhanced_technicals import (
    EnhancedTechnicalEngine,
    TechnicalAnalysisResult,
    format_technical_summary,
)

logger = logging.getLogger(__name__)

# ── Configurable indicator weights (must sum to 1.0) ─────────────────────
INDICATOR_WEIGHTS = {
    "ma_trend": 0.25,
    "rsi": 0.15,
    "macd": 0.25,
    "volume": 0.20,
    "breakout": 0.15,
}

# ── Thresholds ────────────────────────────────────────────────────────────
MIN_CONFIRMING_INDICATORS = 3     # for STRONG signal
CONFIRMING_THRESHOLD = 0.60       # indicator score ≥ this counts as confirming
MIN_RISK_REWARD = 1.5             # minimum R:R for BUY recommendation (lowered from 2.0)
ATR_EXTREME_MULTIPLIER = 2.0     # ATR above median×this = extreme volatility
LOOKBACK_SUPPORT_RESISTANCE = 20  # days for S/R detection


# ── Data classes ──────────────────────────────────────────────────────────

@dataclass
class IndicatorDetail:
    """Individual indicator score breakdown."""
    name: str
    raw: dict
    normalized: float   # 0.0 – 1.0
    weight: float
    weighted: float     # normalized × weight
    signal: str         # "bullish" / "bearish" / "neutral"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AnalysisResult:
    """Complete analysis output produced by the engine."""
    ticker: str

    # ── Composite ──
    final_score: float          # 0 – 100
    confidence: str             # "HIGH" / "MEDIUM" / "LOW"
    signal: str                 # "BUY" / "SELL" / "HOLD"
    signal_strength: str        # "STRONG" / "WEAK"
    trend_status: str           # "BULLISH" / "SIDEWAYS" / "BEARISH"

    # ── Risk / Reward ──
    entry_zone: dict            # {"low": float, "high": float}
    stop_loss: float
    take_profit: float
    risk_reward_ratio: float

    # ── Meta ──
    volatility: str             # "LOW" / "MEDIUM" / "HIGH" / "EXTREME"
    atr: float
    support: float
    resistance: float
    confirming_indicators: int

    # ── Breakdown ──
    indicators: dict = field(default_factory=dict)   # name -> IndicatorDetail dict

    # ── ML (filled later) ──
    ml_probability: Optional[float] = None
    ml_direction: Optional[str] = None
    combined_score: Optional[float] = None  # tech×0.6 + ml×0.4

    def to_dict(self) -> dict:
        return asdict(self)


# ── Helper functions ──────────────────────────────────────────────────────

def _sigmoid(x: float, k: float = 1.0) -> float:
    """Squash *x* into (0, 1)."""
    return 1.0 / (1.0 + math.exp(-k * x))


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


# ── Normalisation functions ───────────────────────────────────────────────

def _normalise_rsi(rsi: float) -> tuple[float, str]:
    """Normalise RSI (14) to 0–1.

    Interpretation: low RSI → oversold → bullish opportunity (score ↑).
    * RSI ≤ 30  → 1.0  (strongly oversold = very bullish)
    * RSI = 50  → 0.5  (neutral)
    * RSI ≥ 70  → 0.0  (strongly overbought = bearish)
    """
    if rsi <= 30:
        score = 1.0
    elif rsi >= 70:
        score = 0.0
    else:
        # Linear mapping: 30→1.0, 70→0.0
        score = (70 - rsi) / 40.0

    if rsi < 30:
        signal = "bullish"
    elif rsi > 70:
        signal = "bearish"
    else:
        signal = "neutral"

    return round(_clamp(score), 4), signal


def _normalise_macd(macd_hist: float, atr: float) -> tuple[float, str]:
    """Normalise MACD histogram via sigmoid, scaled by ATR.

    Positive histogram → bullish, negative → bearish.
    Scaling by ATR avoids bias from absolute price level.
    """
    if atr <= 0:
        atr = 1.0
    ratio = macd_hist / atr
    score = _sigmoid(ratio, k=2.0)

    if macd_hist > 0:
        signal = "bullish"
    elif macd_hist < 0:
        signal = "bearish"
    else:
        signal = "neutral"

    return round(_clamp(score), 4), signal


def _normalise_ma_trend(
    price: float,
    sma20: float | None,
    sma50: float | None,
) -> tuple[float, str]:
    """Score based on moving-average trend alignment.

    Full marks when: price > SMA50 AND SMA20 > SMA50
    Partial marks for each condition met individually.
    """
    score = 0.0
    factors = 0

    if sma50 is not None and sma50 > 0:
        if price > sma50:
            score += 0.40
        # Distance above/below SMA50 (capped ±10 %)
        dist = (price - sma50) / sma50
        score += _clamp((dist + 0.10) / 0.20, 0.0, 0.20)
        factors += 1

    if sma20 is not None and sma50 is not None and sma50 > 0:
        if sma20 > sma50:
            score += 0.40
        factors += 1

    if factors == 0:
        return 0.5, "neutral"

    score = _clamp(score)

    if score >= 0.7:
        signal = "bullish"
    elif score <= 0.3:
        signal = "bearish"
    else:
        signal = "neutral"

    return round(score, 4), signal


def _normalise_volume(volume_ratio: float) -> tuple[float, str]:
    """Normalise volume ratio (current / 20-day average).

    Higher ratio → more conviction → higher score (capped at 1.0).
    """
    score = _clamp(volume_ratio / 2.0)

    if volume_ratio >= 1.5:
        signal = "bullish"
    elif volume_ratio <= 0.5:
        signal = "bearish"
    else:
        signal = "neutral"

    return round(score, 4), signal


def _detect_higher_highs_lows(highs: pd.Series, lows: pd.Series, window: int = 5) -> tuple[float, str]:
    """Detect higher-highs & higher-lows pattern over last *window* periods.

    Returns a 0–1 score (1.0 = strong uptrend pattern).
    """
    if len(highs) < window * 2 or len(lows) < window * 2:
        return 0.5, "neutral"

    recent_highs = highs.tail(window)
    prev_highs = highs.iloc[-(window * 2):-window]
    recent_lows = lows.tail(window)
    prev_lows = lows.iloc[-(window * 2):-window]

    hh = float(recent_highs.max()) > float(prev_highs.max())
    hl = float(recent_lows.min()) > float(prev_lows.min())

    if hh and hl:
        score, signal = 1.0, "bullish"
    elif hh or hl:
        score, signal = 0.65, "neutral"
    else:
        ll = float(recent_lows.min()) < float(prev_lows.min())
        lh = float(recent_highs.max()) < float(prev_highs.max())
        if ll and lh:
            score, signal = 0.0, "bearish"
        elif ll or lh:
            score, signal = 0.35, "neutral"
        else:
            score, signal = 0.5, "neutral"

    return round(score, 4), signal


# ── ATR calculation ───────────────────────────────────────────────────────

def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
    """Average True Range (14-period)."""
    if len(close) < period + 1:
        return 0.0

    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr = tr.rolling(window=period).mean()
    val = atr.iloc[-1]
    return round(float(val), 2) if not pd.isna(val) else 0.0


# ── Support / Resistance ─────────────────────────────────────────────────

def find_support_resistance(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int = LOOKBACK_SUPPORT_RESISTANCE,
) -> tuple[float, float]:
    """Simple support/resistance from rolling min/max."""
    recent_low = low.tail(window)
    recent_high = high.tail(window)

    support = float(recent_low.min())
    resistance = float(recent_high.max())

    return round(support, 2), round(resistance, 2)


# ── Main analysis function ────────────────────────────────────────────────

def analyze(ticker: str, history: list[dict]) -> Optional[AnalysisResult]:
    """Run the full weighted scoring analysis on a stock.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol (e.g. "BBCA").
    history : list[dict]
        OHLCV history dicts with keys: date, open, high, low, close, volume.

    Returns
    -------
    AnalysisResult or None if insufficient data.
    """
    if not history or len(history) < 30:
        logger.warning(f"Insufficient history for {ticker}: {len(history) if history else 0} bars")
        return None

    df = pd.DataFrame(history)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]
    current_price = float(close.iloc[-1])

    # ── Raw indicators ────────────────────────────────────────────────

    # RSI-14
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
    rs = gain / loss
    rsi_series = 100 - (100 / (1 + rs))
    rsi_val = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else 50.0

    # Moving averages
    sma20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else None
    sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None

    # MACD
    if len(close) >= 26:
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist_series = macd_line - signal_line
        macd_hist_val = float(macd_hist_series.iloc[-1])
        macd_val = float(macd_line.iloc[-1])
        macd_signal_val = float(signal_line.iloc[-1])
    else:
        macd_hist_val = 0.0
        macd_val = 0.0
        macd_signal_val = 0.0

    # Volume ratio
    if len(volume) >= 20:
        avg_vol = volume.rolling(20).mean().iloc[-1]
        vol_ratio = float(volume.iloc[-1] / avg_vol) if avg_vol > 0 else 1.0
    else:
        vol_ratio = 1.0

    # ATR
    atr = calculate_atr(high, low, close)

    # Support / Resistance
    support, resistance = find_support_resistance(high, low, close)

    # ── Normalise indicators ──────────────────────────────────────────

    rsi_score, rsi_signal = _normalise_rsi(rsi_val)
    macd_score, macd_signal = _normalise_macd(macd_hist_val, atr if atr > 0 else 1.0)
    ma_score, ma_signal = _normalise_ma_trend(current_price, sma20, sma50)
    vol_score, vol_signal = _normalise_volume(vol_ratio)
    breakout_score, breakout_signal = _detect_higher_highs_lows(high, low)

    # ── Build indicator details ───────────────────────────────────────

    indicators = {}

    def _add(name: str, raw: dict, normalised: float, signal: str):
        w = INDICATOR_WEIGHTS[name]
        indicators[name] = IndicatorDetail(
            name=name,
            raw=raw,
            normalized=normalised,
            weight=w,
            weighted=round(normalised * w, 4),
            signal=signal,
        ).to_dict()

    _add("ma_trend", {
        "price": current_price,
        "sma20": sma20,
        "sma50": sma50,
        "price_above_sma50": (current_price > sma50) if sma50 else None,
        "sma20_above_sma50": (sma20 > sma50) if (sma20 and sma50) else None,
    }, ma_score, ma_signal)

    _add("rsi", {"rsi_14": round(rsi_val, 2)}, rsi_score, rsi_signal)

    _add("macd", {
        "macd": round(macd_val, 2),
        "signal": round(macd_signal_val, 2),
        "histogram": round(macd_hist_val, 2),
    }, macd_score, macd_signal)

    _add("volume", {
        "current_volume": int(volume.iloc[-1]),
        "avg_volume_20d": int(volume.rolling(20).mean().iloc[-1]) if len(volume) >= 20 else 0,
        "volume_ratio": round(vol_ratio, 2),
    }, vol_score, vol_signal)

    _add("breakout", {
        "higher_highs": breakout_score >= 0.65,
        "higher_lows": breakout_score >= 0.65,
    }, breakout_score, breakout_signal)

    # ── Weighted composite score ──────────────────────────────────────

    raw_score = sum(ind["weighted"] for ind in indicators.values())
    # Scale to 0–100
    final_score = round(raw_score * 100, 1)

    # ── ATR volatility filter ─────────────────────────────────────────

    atr_pct = (atr / current_price * 100) if current_price > 0 else 0
    if atr_pct > 5.0:
        volatility = "EXTREME"
        final_score = max(0, final_score - 15)  # heavy penalty
    elif atr_pct > 3.0:
        volatility = "HIGH"
        final_score = max(0, final_score - 5)   # mild penalty
    elif atr_pct > 1.5:
        volatility = "MEDIUM"
    else:
        volatility = "LOW"

    final_score = round(_clamp(final_score, 0, 100), 1)

    # ── Signal validation ─────────────────────────────────────────────

    confirming = sum(
        1 for ind in indicators.values()
        if ind["normalized"] >= CONFIRMING_THRESHOLD
    )

    # ── Trend confirmation ────────────────────────────────────────────

    trend_aligned = (
        sma50 is not None
        and current_price > sma50
        and sma20 is not None
        and sma20 > sma50
    )

    # ── Trend status ──────────────────────────────────────────────────

    if final_score >= 60 and trend_aligned:
        trend_status = "BULLISH"
    elif final_score <= 40:
        trend_status = "BEARISH"
    else:
        trend_status = "SIDEWAYS"

    # ── Risk / Reward ─────────────────────────────────────────────────

    downside = current_price - support if support < current_price else atr
    upside = resistance - current_price if resistance > current_price else atr
    rr_ratio = round(upside / downside, 2) if downside > 0 else 0.0

    # ── Signal determination ──────────────────────────────────────────

    buy_conditions = (
        final_score >= 55
        and rr_ratio >= MIN_RISK_REWARD
        and trend_status != "BEARISH"
    )

    if buy_conditions:
        signal = "BUY"
    elif final_score <= 35:
        signal = "SELL"
    else:
        signal = "HOLD"

    # Downgrade if trend not confirmed or not enough confirming indicators
    if signal == "BUY" and (not trend_aligned or confirming < MIN_CONFIRMING_INDICATORS):
        signal_strength = "WEAK"
    elif signal == "BUY" and confirming >= MIN_CONFIRMING_INDICATORS and trend_aligned:
        signal_strength = "STRONG"
    else:
        signal_strength = "WEAK" if confirming < MIN_CONFIRMING_INDICATORS else "MODERATE"

    # ── Confidence ────────────────────────────────────────────────────

    if final_score >= 70:
        confidence = "HIGH"
    elif final_score >= 40:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    # ── Entry zone / SL / TP ──────────────────────────────────────────

    entry_low = round(current_price - atr * 0.3, 2) if atr > 0 else current_price
    entry_high = round(current_price + atr * 0.2, 2) if atr > 0 else current_price
    stop_loss = round(support - atr * 0.5, 2) if atr > 0 else support
    take_profit = round(resistance + atr * 0.3, 2) if atr > 0 else resistance

    # ── Build result ──────────────────────────────────────────────────

    return AnalysisResult(
        ticker=ticker,
        final_score=final_score,
        confidence=confidence,
        signal=signal,
        signal_strength=signal_strength,
        trend_status=trend_status,
        entry_zone={"low": entry_low, "high": entry_high},
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_reward_ratio=rr_ratio,
        volatility=volatility,
        atr=atr,
        support=support,
        resistance=resistance,
        confirming_indicators=confirming,
        indicators=indicators,
    )


def format_score_card(result: AnalysisResult) -> str:
    """Format a compact score card for Telegram display."""
    # Confidence emoji
    conf_emoji = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "⚪"}.get(result.confidence, "⚪")
    signal_emoji = {"BUY": "📈", "SELL": "📉", "HOLD": "⏸"}.get(result.signal, "⏸")
    vol_emoji = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🟠", "EXTREME": "🔴"}.get(result.volatility, "⚪")
    trend_emoji = {"BULLISH": "📈", "BEARISH": "📉", "SIDEWAYS": "↔️"}.get(result.trend_status, "↔️")
    strength = f" ({result.signal_strength})" if result.signal == "BUY" else ""

    lines = [
        f"┌───────────────────────────────────┐",
        f"│ {conf_emoji} {result.ticker} Score: {result.final_score}/100",
        f"│ {signal_emoji} Signal: {result.signal}{strength}",
        f"│ {trend_emoji} Trend: {result.trend_status}",
        f"│ 🎯 Confidence: {result.confidence} ({result.final_score}%)",
        f"│ ⚖️ R:R Ratio: 1:{result.risk_reward_ratio}",
        f"│ {vol_emoji} Volatility: {result.volatility} (ATR: {result.atr:,.0f})",
        f"│",
        f"│ 💰 Entry Zone: Rp {result.entry_zone['low']:,.0f} – {result.entry_zone['high']:,.0f}",
        f"│ 🛑 Stop Loss: Rp {result.stop_loss:,.0f}",
        f"│ 🎯 Take Profit: Rp {result.take_profit:,.0f}",
        f"│ 📊 Support: Rp {result.support:,.0f} | Resistance: Rp {result.resistance:,.0f}",
        f"│ ✅ Confirming Indicators: {result.confirming_indicators}/5",
        f"└───────────────────────────────────┘",
    ]

    # ML section if available
    if result.ml_probability is not None:
        ml_dir = result.ml_direction or "N/A"
        ml_pct = f"{result.ml_probability * 100:.0f}%" if result.ml_probability else "N/A"
        combined = f"{result.combined_score:.1f}" if result.combined_score else "N/A"
        lines.insert(-1, f"│ 🤖 ML: {ml_dir} ({ml_pct}) | Combined: {combined}")

    return "\n".join(lines)


# ── Enhanced Analysis Functions (Phase 1) ─────────────────────────────────

def analyze_enhanced(ticker: str, history: list[dict]) -> Optional[TechnicalAnalysisResult]:
    """Run enhanced technical analysis with 130+ indicators.
    
    Uses the EnhancedTechnicalEngine for comprehensive analysis including:
    - 130+ technical indicators via pandas-ta
    - Divergence detection (RSI, MACD)
    - Candlestick pattern recognition
    - Professional support/resistance levels
    - Multi-category scoring (Trend, Momentum, Volatility, Volume)
    
    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    history : list[dict]
        OHLCV history with keys: date, open, high, low, close, volume
    
    Returns
    -------
    TechnicalAnalysisResult or None if insufficient data
    """
    if not history or len(history) < 50:
        logger.warning(f"Insufficient history for enhanced analysis: {len(history) if history else 0} bars")
        return None
    
    df = pd.DataFrame(history)
    
    try:
        engine = EnhancedTechnicalEngine()
        result = engine.analyze(df, ticker)
        
        logger.info(
            f"Enhanced analysis for {ticker}: "
            f"signal={result.signal}, score={result.composite_score}, "
            f"trend={result.trend_direction}"
        )
        
        return result
    
    except Exception as e:
        logger.error(f"Enhanced analysis error for {ticker}: {e}")
        return None


def format_enhanced_summary(result: TechnicalAnalysisResult) -> str:
    """Format enhanced technical analysis for Telegram display."""
    return format_technical_summary(result)


def get_enhanced_signal_summary(result: TechnicalAnalysisResult) -> dict:
    """Get concise signal summary for AI/LLM consumption."""
    return {
        'ticker': result.ticker,
        'signal': result.signal,
        'signal_strength': result.signal_strength,
        'composite_score': result.composite_score,
        'trend_direction': result.trend_direction,
        'category_scores': {
            'trend': result.trend_score,
            'momentum': result.momentum_score,
            'volatility': result.volatility_score,
            'volume': result.volume_score,
        },
        'patterns_detected': len(result.candlestick_patterns),
        'divergences_detected': len(result.divergences),
        'key_levels': {
            'supports': [s['level'] for s in result.support_levels[:2]],
            'resistances': [r['level'] for r in result.resistance_levels[:2]],
        },
    }
