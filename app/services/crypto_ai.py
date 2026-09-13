"""AI analysis layer for the crypto scanner.

The deterministic scanner selects candidates first; this module adds an
AI interpretation layer on top. The AI does NOT compute indicators from raw
candles — it receives a rich, sanitised summary (real recent closes + every
computed indicator/level) and produces a structured verdict.

AI is never a single point of failure: if the LLM fails, the caller falls back
to a deterministic verdict derived from the momentum score.
"""

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from app.ai.llm_client import llm_client
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

ALLOWED_VERDICTS = ("STRONG_WATCH", "WATCH", "NEUTRAL", "AVOID")

_SYSTEM_PROMPT = """You are a cryptocurrency momentum scanner. You receive a compact
summary of technical data for a candidate coin, INCLUDING hundreds of recent
closing prices and every indicator/parameter the deterministic engine computed.
Your job:
- Interpret the data.
- Judge setup QUALITY, not price direction certainty.
- Flag possible false breakouts / pumps.
- Classify risk.
- Give a short human-readable reason.

How to use the data:
- Use the full candle series (candles_1h, candles_15m: most recent LAST) to
  verify trend structure, swing highs/lows, support/resistance, how extended
  price is, and whether an entry near the current price offers good risk/reward.
- Check where entry / takeProfit1 / takeProfit2 / stopLoss sit relative to the
  recent swing levels from the series.
- Cross-check the score components (trend/momentum/volume/breakout/risk_penalty)
  and the per-timeframe indicators (RSI, EMA trend, MACD, ATR%, relative volume).
- A genuine setup: trend up on 1H, price pulling back near support, RSI not
  overbought on the entry timeframe, volume confirming, risk/reward favourable.
- Flag counter-evidence: overbought RSI, price extended far above the 1H EMA,
  no true swing support below, falling volume, warning signs of a pump.

Rules:
- ONLY use the data provided. NEVER invent numbers.
- Never say "guaranteed profit" or similar. Use words like momentum, candidate,
  setup, potential, watchlist.
- Do NOT use BUY/SELL verdicts.

Allowed verdicts:
- STRONG_WATCH (excellent momentum setup, low counter-evidence)
- WATCH (decent setup worth watching)
- NEUTRAL (mixed signals)
- AVOID (poor / risky setup)

Respond with a SINGLE JSON array (no markdown fences) — one object per symbol.
Each object has EXACTLY this schema:
{
  "symbol": "XXX_USDT",
  "verdict": "WATCH",
  "confidence": 78,
  "risk": "LOW",
  "reason": ["bullet point 1", "bullet point 2"],
  "warning": "short warning or empty string"
}
responses.
- reason: 1–3 short bullet points, each ≤15 words, no fluff.
- risk is one of: LOW, MEDIUM, HIGH."""


@dataclass
class CandidatPayload:
    """Rich candidate summary sent to the AI. Includes the full score
    breakdown, per-timeframe indicators, entry/TP/SL levels and (when available)
    a compact series of recent closes per timeframe so the LLM can verify trend
    structure. Never carries raw OHLCV of every timeframe — closes only."""
    symbol: str
    score: float
    price: Optional[float]
    priceChange1h: Optional[float]
    priceChange4h: Optional[float]
    priceChange24h: Optional[float]
    rsi5m: Optional[float]
    rsi15m: Optional[float]
    rsi1h: Optional[float]
    emaTrend: Optional[str]
    macd: Optional[str]
    relativeVolume: Optional[float]
    breakout: bool
    volatility: Optional[str]
    entry: Optional[float] = None
    takeProfit1: Optional[float] = None
    takeProfit2: Optional[float] = None
    stopLoss: Optional[float] = None
    scoreBreakdown: Optional[dict] = None
    volume24h: Optional[float] = None
    candles_1h: list[float] = field(default_factory=list)
    candles_15m: list[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in asdict(self).items()}


@dataclass
class AIVerdict:
    symbol: str = ""
    verdict: str = "NEUTRAL"
    confidence: int = 50
    risk: str = "MEDIUM"
    reason: list[str] = field(default_factory=list)
    warning: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def is_watch(self) -> bool:
        return self.verdict in ("STRONG_WATCH", "WATCH")


def build_candidate_payload(candidate: dict) -> CandidatPayload:
    """Build an AI-safe compact payload from a scored candidate dict."""
    summaries = candidate.get("tf_summaries", {})
    s5 = summaries.get("5m", {}) or {}
    s15 = summaries.get("15m", {}) or {}
    s1h = summaries.get("1h", {}) or {}
    price_change = candidate.get("price_change", {}) or {}

    volatility_label = "low"
    atr_pct = s1h.get("atr_pct")
    if atr_pct is not None:
        volatility_label = "high" if atr_pct > 5 else ("medium" if atr_pct > 2 else "low")

    levels = candidate.get("price_levels") or {}
    return CandidatPayload(
        symbol=candidate.get("symbol", ""),
        score=float(candidate.get("score", 0) or 0),
        price=s1h.get("price"),
        priceChange1h=price_change.get("1h"),
        priceChange4h=price_change.get("4h"),
        priceChange24h=price_change.get("24h"),
        rsi5m=s5.get("rsi"),
        rsi15m=s15.get("rsi"),
        rsi1h=s1h.get("rsi"),
        emaTrend=s1h.get("trend"),
        macd=s1h.get("macd_state"),
        relativeVolume=s1h.get("relative_volume"),
        breakout=bool(s1h.get("at_high")),
        volatility=volatility_label,
        entry=levels.get("entry"),
        takeProfit1=levels.get("take_profit_1"),
        takeProfit2=levels.get("take_profit_2"),
        stopLoss=levels.get("stop_loss"),
        scoreBreakdown=(candidate.get("score_breakdown") or None),
        volume24h=((candidate.get("ticker") or {}).get("quoteVolume") or None),
        candles_1h=list((candidate.get("series") or {}).get("1h") or []),
        candles_15m=list((candidate.get("series") or {}).get("15m") or []),
    )


def parse_verdict(raw: str, fallback_symbol: str = "") -> AIVerdict:
    """Robustly parse an AI response into an :class:`AIVerdict`.

    Tolerates markdown fences, leading text, and missing fields. Falls back to a
    safe NEUTRAL verdict if the payload cannot be parsed.
    """
    text = (raw or "").strip()

    # Strip markdown code fences if present.
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)

    # Try to extract a JSON object.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        logger.warning("AI response contained no JSON object, using neutral verdict")
        return AIVerdict(symbol=fallback_symbol, verdict="NEUTRAL", reason=["AI response unparseable"])

    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        logger.warning(f"AI JSON parse failed: {e}; raw={text[:200]}")
        return AIVerdict(symbol=fallback_symbol, verdict="NEUTRAL", reason=["AI response unparseable"])

    verdict = str(data.get("verdict", "NEUTRAL")).upper()
    if verdict not in ALLOWED_VERDICTS:
        verdict = "NEUTRAL"

    try:
        confidence = int(data.get("confidence", 50))
    except (TypeError, ValueError):
        confidence = 50
    confidence = max(0, min(100, confidence))

    risk = str(data.get("risk", "MEDIUM")).upper()
    if risk not in ("LOW", "MEDIUM", "HIGH"):
        risk = "MEDIUM"

    reason = data.get("reason", [])
    if isinstance(reason, str):
        reason = [reason]
    reason = [str(r) for r in reason if r][:5]

    warning = str(data.get("warning", "") or "")

    return AIVerdict(
        symbol=str(data.get("symbol", fallback_symbol)),
        verdict=verdict,
        confidence=confidence,
        risk=risk,
        reason=reason,
        warning=warning,
    )


def deterministic_fallback(candidate: dict) -> AIVerdict:
    """Score-based fallback used when the AI is unavailable."""
    score = float(candidate.get("score", 0) or 0)
    symbol = candidate.get("symbol", "")

    if score >= 80:
        verdict, confidence, risk = "STRONG_WATCH", min(90, int(score)), "MEDIUM"
    elif score >= settings.crypto_min_score_alert:
        verdict, confidence, risk = "WATCH", min(85, int(score)), "MEDIUM"
    elif score >= 60:
        verdict, confidence, risk = "NEUTRAL", 55, "MEDIUM"
    else:
        verdict, confidence, risk = "AVOID", 40, "HIGH"

    reasons = [f"Deterministic momentum score {score:.0f}/100"]
    summaries = candidate.get("tf_summaries", {}) or {}
    s1h = summaries.get("1h", {}) or {}
    if s1h.get("trend") == "bullish":
        reasons.append("Trend 1H bullish")
    if s1h.get("macd_state") == "bullish":
        reasons.append("MACD bullish")
    if s1h.get("at_high"):
        reasons.append("Testing recent high")
    if s1h.get("relative_volume") and s1h["relative_volume"] >= 1.5:
        reasons.append("Volume above average")

    return AIVerdict(
        symbol=symbol,
        verdict=verdict,
        confidence=confidence,
        risk=risk,
        reason=reasons,
        warning="AI analysis unavailable; based on technical score only.",
    )


# Safety cap for the AI batch prompt — bound token cost even if lookback or
# candidate count grows. We trim candle detail, never indicator fields.
_MAX_BATCH_CHARS = 120_000


def _trim_payloads(payloads: list[dict]) -> list[dict]:
    """Shrink candle series of a big batch so the LLM prompt stays in budget."""
    total = sum(len(json.dumps(p)) for p in payloads)
    if total <= _MAX_BATCH_CHARS:
        return payloads
    # First cut: drop 15m series.
    for p in payloads:
        if isinstance(p, dict):
            p.pop("candles_15m", None)
    total = sum(len(json.dumps(p)) for p in payloads)
    if total <= _MAX_BATCH_CHARS:
        return payloads
    # Second cut: keep only the last 100 1h closes per symbol.
    for p in payloads:
        if isinstance(p, dict) and isinstance(p.get("candles_1h"), list):
            p["candles_1h"] = p["candles_1h"][-100:]
    return payloads


async def analyze_candidates(candidates: list[dict]) -> dict[str, AIVerdict]:
    """Analyse a batch of candidate summaries with the AI.

    Returns a dict ``symbol -> AIVerdict``. On AI failure every candidate gets a
    deterministic fallback verdict, so the scanner keeps working.
    """
    if not candidates:
        return {}

    payloads = _trim_payloads([build_candidate_payload(c).to_dict() for c in candidates])
    user_prompt = (
        "Here are the top candidate coins from the deterministic scanner. Each "
        "object contains the full score breakdown, per-timeframe indicators, "
        "entry/TP/SL levels and the most recent closing prices (candles_1h and "
        "candles_15m, oldest FIRST, latest LAST):\n"
        f"{json.dumps(payloads, indent=2, default=str)}\n\n"
        "Analyse each and return a JSON array of objects with the schema described in the "
        "system prompt (one object per symbol)."
    )

    results: dict[str, AIVerdict] = {}
    try:
        raw = await llm_client.generate(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.3,
            # N verdicts × (bullets + warning): 2000 trims the JSON array, 4000
            # trims it again with rich 200-candle context (long reasons) →
            # truncated JSON → silent fallback. 16000 gives the model comfortable
            # headroom for 10 symbols; cheap because output is the small part.
            max_tokens=16000,
        )
        verdicts = _parse_batch(raw, candidates)
        if verdicts:
            results = verdicts
        else:
            logger.warning("AI returned no parseable verdicts; using deterministic fallback")
            results = {c.get("symbol", ""): deterministic_fallback(c) for c in candidates}
    except Exception as e:
        logger.error(f"AI analysis failed: {e}; using deterministic fallback")
        results = {c.get("symbol", ""): deterministic_fallback(c) for c in candidates}

    # Ensure every candidate has a verdict even if AI missed one.
    for c in candidates:
        symbol = c.get("symbol", "")
        if symbol and symbol not in results:
            results[symbol] = deterministic_fallback(c)

    return results


def _parse_batch(raw: str, candidates: list[dict]) -> dict[str, AIVerdict]:
    """Parse a JSON array (or object) of AI verdicts."""
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)

    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        # Maybe the AI returned a single object instead of an array.
        single = parse_verdict(raw)
        if single.verdict != "NEUTRAL" or single.reason != ["AI response unparseable"]:
            return {single.symbol: single}
        return {}

    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        logger.warning(f"AI batch JSON parse failed: {e}")
        return {}

    if isinstance(data, dict):
        data = [data]

    out: dict[str, AIVerdict] = {}
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        v = parse_verdict(json.dumps(item))
        if v.symbol:
            out[v.symbol] = v
    return out
