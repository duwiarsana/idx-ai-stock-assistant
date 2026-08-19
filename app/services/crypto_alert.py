"""Telegram alerting + anti-spam for the crypto scanner.

Anti-spam uses Redis (the project's existing cache/persistence layer):
* ``crypto:alert:<symbol>`` — stores the last alert payload + sent timestamp,
  with a TTL equal to the cooldown window. A pair is only re-alerted when the
  cooldown has expired, the score improved significantly (+10), or a brand new
  breakout appeared.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from telegram import Bot

from app.config import get_settings
from app.services.cache_service import cache_service

logger = logging.getLogger(__name__)
settings = get_settings()

ALERT_KEY_PREFIX = "crypto:alert:"
SCORE_IMPROVEMENT_THRESHOLD = 10  # points
DISCLAIMER = "Signal monitoring only, not financial advice."


def _trend_arrow(trend: Optional[str]) -> str:
    return {"bullish": "🟢", "bearish": "🔴"}.get(trend or "", "⚪")


def format_alert_message(candidate: dict, verdict: dict) -> str:
    """Build a compact, mobile-friendly alert message.

    ``candidate`` is a scored candidate dict; ``verdict`` is the AI verdict dict.
    """
    display = candidate.get("display", candidate.get("symbol", "?"))
    score = float(candidate.get("score", 0) or 0)
    price_change = candidate.get("price_change", {}) or {}
    tf_summaries = candidate.get("tf_summaries", {}) or {}
    s5 = tf_summaries.get("5m", {}) or {}
    s15 = tf_summaries.get("15m", {}) or {}
    s1h = tf_summaries.get("1h", {}) or {}
    price_levels = candidate.get("price_levels") or {}

    price = s1h.get("price") or candidate.get("price")
    rv_1h = s1h.get("relative_volume")
    confidence = verdict.get("confidence", 50)
    risk = verdict.get("risk", "MEDIUM")
    reasons = verdict.get("reason", [])
    warning = verdict.get("warning", "")
    ai_unavailable = "unavailable" in (verdict.get("warning", "") or "").lower()

    lines = [
        "🚨 *CRYPTO MOMENTUM ALERT*",
        "",
        f"🔥 *{display}*",
        f"Score: *{score:.0f}/100*  |  AI confidence: {confidence}%",
        f"Risk: {risk}",
        "",
    ]

    if price is not None:
        quote = candidate.get("quote", "USDT")
        lines.append(f"💰 Price: {_fmt_price(price)} {quote}")
    if price_change.get("1h") is not None:
        lines.append(f"📈 1H: {price_change['1h']:+.1f}%")
    if price_change.get("4h") is not None:
        lines.append(f"📈 4H: {price_change['4h']:+.1f}%")
    if rv_1h is not None:
        lines.append(f"📊 Volume: {rv_1h:.1f}x average")
    lines.append("")

    # ── Entry / TP / SL price levels ──────────────────────────────────
    entry = price_levels.get("entry")
    tp1 = price_levels.get("take_profit_1")
    tp2 = price_levels.get("take_profit_2")
    sl = price_levels.get("stop_loss")
    rr = price_levels.get("risk_reward")
    if entry is not None and tp1 is not None and tp2 is not None and sl is not None:
        lines.append("🎯 *Level Harga:*")
        note = price_levels.get("entry_note")
        if note:
            lines.append(f"   💎 Entry: {_fmt_price(entry)} ({note})")
        else:
            lines.append(f"   💎 Entry: {_fmt_price(entry)}")
        lines.append(f"   🎯 TP1: {_fmt_price(tp1)}  {_pct(entry, tp1)}")
        lines.append(f"   🎯 TP2: {_fmt_price(tp2)}  {_pct(entry, tp2)}")
        lines.append(f"   🛑 SL: {_fmt_price(sl)}  {_pct(entry, sl)}")
        if rr is not None:
            lines.append(f"   ⚖️ Risk/Reward: 1:{rr}")
        lines.append("")

    # Multi-timeframe trend row.
    lines.append("Trend:")
    lines.append(
        f"5m {_trend_arrow(s5.get('trend'))}   "
        f"15m {_trend_arrow(s15.get('trend'))}   "
        f"1h {_trend_arrow(s1h.get('trend'))}"
    )
    lines.append("")

    if reasons:
        lines.append("Signals:")
        for r in reasons[:5]:
            lines.append(f"• {r}")
        lines.append("")

    if s1h.get("rsi") is not None:
        lines.append(f"⚠️ RSI 15m: {s15.get('rsi') or s1h.get('rsi'):.0f}")

    if warning:
        lines.append("")
        lines.append(f"AI: {warning}")

    if ai_unavailable:
        lines.append("")
        lines.append("⚠️ AI analysis unavailable — based on technical score only.")

    lines.append("")
    lines.append(f"_Time: {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC_")
    lines.append(f"_{DISCLAIMER}_")

    return "\n".join(lines)


def _fmt_price(value: float) -> str:
    if value >= 1000:
        return f"{value:,.2f}"
    if value >= 1:
        return f"{value:.4f}"
    return f"{value:.6f}"


def _pct(base: float, target: float) -> str:
    """Percent change between two prices, e.g. '+3.2%'."""
    if not base:
        return ""
    return f"{((target - base) / base) * 100:+.1f}%"


async def _load_last_alert(symbol: str) -> Optional[dict]:
    try:
        raw = await cache_service.redis.get(f"{ALERT_KEY_PREFIX}{symbol}")
        if raw:
            return json.loads(raw)
    except Exception as e:
        logger.warning(f"Failed to load last alert for {symbol}: {e}")
    return None


async def _store_alert(symbol: str, payload: dict, cooldown: int) -> None:
    try:
        await cache_service.redis.setex(
            f"{ALERT_KEY_PREFIX}{symbol}",
            cooldown,
            json.dumps(payload, default=str),
        )
    except Exception as e:
        logger.warning(f"Failed to store alert state for {symbol}: {e}")


async def should_alert(candidate: dict, cooldown_minutes: Optional[int] = None) -> tuple[bool, str]:
    """Anti-spam gate for a candidate.

    Returns ``(should_send, skip_reason)``. A pair is eligible when:
    * it was never alerted, OR
    * the cooldown expired, OR
    * the score improved by >= SCORE_IMPROVEMENT_THRESHOLD, OR
    * a brand new breakout appeared (price now at/recent high when it wasn't before).
    """
    symbol = candidate.get("symbol")
    if not symbol:
        return False, "missing symbol"

    cooldown = (cooldown_minutes or settings.crypto_alert_cooldown_minutes) * 60
    last = await _load_last_alert(symbol)

    if not last:
        return True, "first alert"

    elapsed = datetime.now(timezone.utc) - datetime.fromisoformat(last.get("sent_at", "1970-01-01T00:00:00+00:00"))
    if elapsed >= timedelta(seconds=cooldown):
        return True, "cooldown expired"

    prev_score = float(last.get("score") or 0)
    new_score = float(candidate.get("score") or 0)
    if new_score - prev_score >= SCORE_IMPROVEMENT_THRESHOLD:
        return True, f"score improved by {new_score - prev_score:.0f} pts"

    prev_breakout = bool(last.get("at_high"))
    new_breakout = bool(candidate.get("tf_summaries", {}).get("1h", {}).get("at_high"))
    if new_breakout and not prev_breakout:
        return True, "new breakout"

    return False, "cooldown active"


async def send_crypto_alert(candidate: dict, verdict: dict, dry_run: Optional[bool] = None) -> dict:
    """Send a Telegram alert for a candidate (or simulate when dry-run).

    Returns a dict with ``{sent, delivery, reason}``.
    """
    symbol = candidate.get("symbol", "")
    message = format_alert_message(candidate, verdict)
    is_dry_run = settings.crypto_scanner_dry_run if dry_run is None else dry_run

    result = {"sent": False, "dry_run": is_dry_run, "reason": "", "error": None}

    if is_dry_run:
        logger.info(f"[DRY-RUN] Crypto alert would be sent for {symbol}:\n{message}")
        result["sent"] = True
        result["reason"] = "dry-run (logged only)"
        # Deliberately do NOT store cooldown state in dry-run: dry runs must
        # not affect production anti-spam behaviour.
        return result

    if not settings.crypto_alert_telegram_enabled:
        logger.info(f"Crypto alert for {symbol}: Telegram alerts disabled, skipped")
        result["reason"] = "telegram alerts disabled"
        return result

    chat_id = settings.telegram_chat_id or settings.telegram_admin_id
    if not settings.telegram_bot_token or not chat_id:
        result["reason"] = "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not configured"
        logger.warning(result["reason"])
        return result

    try:
        bot = Bot(token=settings.telegram_bot_token)
        await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode="Markdown",
        )
        result["sent"] = True
        result["reason"] = "sent"
        await _store_alert(symbol, _alert_payload(candidate), settings.crypto_alert_cooldown_minutes * 60)
    except Exception as e:
        result["error"] = str(e)
        result["reason"] = f"send failed: {e}"
        logger.error(f"Failed to send crypto alert for {symbol}: {e}")

    return result


def _alert_payload(candidate: dict) -> dict:
    """Snapshot of the candidate state stored for anti-spam decisions."""
    s1h = candidate.get("tf_summaries", {}).get("1h", {}) or {}
    return {
        "symbol": candidate.get("symbol", ""),
        "score": float(candidate.get("score") or 0),
        "at_high": bool(s1h.get("at_high")),
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "display": candidate.get("display", candidate.get("symbol", "")),
    }
