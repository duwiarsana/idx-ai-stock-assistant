"""CryptoScanner orchestrator — Tokocrypto momentum scanner.

Pipeline:
1. Fetch supported trading symbols (cached), filter by quote assets + liquidity.
2. Fetch 24h tickers for all pairs at once (batch endpoint).
3. Filter out stablecoin vs stablecoin, illiquid markets, inactive pairs.
4. Download OHLCV (5m / 15m / 1h) for the surviving candidates (concurrency-limited).
5. Compute deterministic indicators per timeframe.
6. Compute the momentum score with a component breakdown.
7. Send top candidates to the AI for a structured verdict.
8. Enforce anti-spam cooldown and send Telegram alerts.
9. Persist scan + alert history for later performance evaluation.

The scanner never trades — it only produces momentum candidates.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from app.config import get_settings
from app.data.tokocrypto_client import TokocryptoClient, tokocrypto_client
from app.services.crypto_indicators import (
    candles_to_closes,
    compute_indicator_summary,
    price_change_percent,
)
from app.services.crypto_scoring import compute_momentum_score
from app.services.crypto_ai import analyze_candidates
from app.services.crypto_alert import send_crypto_alert, should_alert
from app.services.cache_service import cache_service

logger = logging.getLogger(__name__)
settings = get_settings()

TIMEFRAMES = ("5m", "15m", "1h")
KLINE_LIMIT = 200

# Percent-change lookbacks, in terms of number of timeframes.
PRICE_CHANGE_LOOKBACKS = {"1h": 1, "4h": 4, "24h": 24}  # in 1h bars


def _parse_quotes(value: Optional[str]) -> list[str]:
    if not value:
        return []
    return [q.strip().upper() for q in value.split(",") if q.strip()]


def _parse_stablequotes(value: Optional[str]) -> set[str]:
    if not value:
        return {"USDT", "USDC", "BUSD", "DAI", "TUSD", "FRAX", "PAX", "FDUSD"}
    return {q.strip().upper() for q in value.split(",") if q.strip()}


class CryptoScanner:
    """Orchestrates one crypto scan cycle."""

    def __init__(self, client: Optional[TokocryptoClient] = None):
        self.client = client or tokocrypto_client
        self.lock = asyncio.Lock()  # prevents overlapping scans
        self.state = {
            "last_scan_at": None,
            "last_scan_status": "idle",
            "last_error": None,
            "last_results": [],
            "pairs_found": 0,
            "pairs_analysed": 0,
        }

    async def run_scan(self, dry_run: Optional[bool] = None) -> dict:
        """Execute one full scan cycle. Safe against overlapping runs."""
        if self.lock.locked():
            logger.warning("Crypto scan skipped — previous scan still running")
            return {"status": "skipped", "reason": "lock held by another scan"}

        async with self.lock:
            started = time.monotonic()
            self.state["last_scan_status"] = "running"
            logger.info("🚀 Crypto scanner cycle started")

            summary = {
                "status": "ok",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "pairs_found": 0,
                "pairs_liquid": 0,
                "candidates": 0,
                "ai_analysed": 0,
                "alerts_sent": 0,
                "paper_opened": 0,
                "paper_closed": 0,
                "errors": 0,
                "duration_ms": 0,
                "top_candidate": None,
                "results": [],
            }

            try:
                summary.update(await self._run_pipeline(dry_run=dry_run))
            except Exception as e:
                summary["status"] = "error"
                summary["errors"] += 1
                summary["last_error"] = str(e)
                self.state["last_error"] = str(e)
                logger.exception(f"Crypto scan failed: {e}")

            summary["duration_ms"] = int((time.monotonic() - started) * 1000)
            summary["ended_at"] = datetime.now(timezone.utc).isoformat()

            self.state["last_scan_at"] = summary["started_at"]
            self.state["last_scan_status"] = summary["status"]
            self.state["pairs_found"] = summary["pairs_found"]
            self.state["pairs_analysed"] = summary.get("pairs_analysed", summary["pairs_liquid"])
            self.state["last_results"] = summary["results"]

            self._log_summary(summary)
            return summary

    async def _run_pipeline(self, dry_run: Optional[bool] = None) -> dict:
        pairs_found = 0
        pairs_liquid = 0
        errors = 0
        candidates: list[dict] = []

        # ── 1. Symbols ────────────────────────────────────────────────
        try:
            symbols = await self.client.fetch_symbols()
        except Exception as e:
            logger.error(f"Failed to fetch symbols: {e}")
            return {"status": "error", "errors": 1, "last_error": f"symbols: {e}", "pairs_found": 0}

        quotes = _parse_quotes(settings.crypto_quote_assets) or ["USDT"]
        stable_quotes = _parse_stablequotes(settings.crypto_stablecoin_quotes)

        quote_set = set(quotes)
        filtered = [
            s for s in symbols
            if s.quote in quote_set
            and s.base not in stable_quotes        # no stablecoin-to-stablecoin pairs
            and s.spot_trading
        ]
        pairs_found = len(filtered)
        logger.info(f"Pairs for quote(s) {quotes}: {pairs_found}")

        # ── 2. Tickers (batch) + liquidity filter ─────────────────────
        try:
            tickers = await self.client.fetch_tickers()
        except Exception as e:
            logger.error(f"Failed to fetch tickers: {e}")
            return {"status": "error", "errors": 1, "last_error": f"tickers: {e}", "pairs_found": pairs_found}

        min_quote_volume = self._min_quote_volume()
        liquid: list[tuple] = []  # (symbol, ticker)
        for sym in filtered:
            ticker = tickers.get(sym.normalized_symbol)
            if not ticker:
                continue
            quote_volume = ticker.get("quoteVolume")
            if quote_volume is None or quote_volume < min_quote_volume:
                continue
            liquid.append((sym, ticker))
        pairs_liquid = len(liquid)
        logger.info(f"Pairs passing liquidity filter (≥{min_quote_volume:,.0f} quote vol): {pairs_liquid}")

        # Cap the number of pairs we actually analyse per cycle to respect
        # rate limits; sort by quote volume descending so the most liquid are
        # analysed first.
        liquid.sort(key=lambda item: (item[1].get("quoteVolume") or 0), reverse=True)
        analysis_budget = max(settings.crypto_min_volume_pairs, 50)
        liquid = liquid[:analysis_budget]

        # ── 3. Technicals + scoring per pair ──────────────────────────
        scored: list[dict] = []
        sem = asyncio.Semaphore(settings.crypto_max_concurrency)

        async def analyse_pair(sym, ticker) -> None:
            nonlocal errors
            try:
                async with sem:
                    tf_klines = await self._fetch_tf_klines(sym)
                if not tf_klines.get("1h"):
                    return
                candidate = self._score_pair(sym, ticker, tf_klines)
                if candidate is None:
                    return
                scored.append(candidate)
            except Exception as e:
                errors += 1
                logger.warning(f"Error analysing {sym.raw_symbol}: {e}")

        await asyncio.gather(*(analyse_pair(sym, ticker) for sym, ticker in liquid))

        scored.sort(key=lambda c: c.get("score", 0), reverse=True)
        threshold = settings.crypto_min_score_alert
        candidates = [c for c in scored if c.get("score", 0) >= threshold]
        logger.info(
            f"Analysed {len(scored)} pairs; {len(candidates)} candidates ≥ score {threshold}"
        )

        # ── 4. AI analysis on top candidates ──────────────────────────
        # Only run the LLM when telegram alerts are actually being sent. When
        # alerts are disabled we keep the deterministic fallback verdicts
        # (free) — the paper trader runs its own AI filter on the shortlist.
        ai_input = candidates[: settings.crypto_max_candidates_ai]
        ai_verdicts: dict[str, dict] = {}
        ai_llm_count = 0
        effective_dry_run = bool(settings.crypto_scanner_dry_run or dry_run)
        if ai_input and not effective_dry_run and settings.crypto_alert_telegram_enabled:
            try:
                raw_verdicts = await analyze_candidates(ai_input)
                ai_verdicts = {k: v.to_dict() for k, v in raw_verdicts.items()}
                ai_llm_count = len(ai_verdicts)
                logger.info(f"AI analysed {ai_llm_count} candidates")
            except Exception as e:
                logger.warning(f"AI analysis failed: {e}; continuing with deterministic")
        # Dry-run / AI-failure / alerts-disabled: fall back to deterministic.
        from app.services.crypto_ai import deterministic_fallback
        if not ai_verdicts:
            ai_verdicts = {c["symbol"]: deterministic_fallback(c).to_dict() for c in ai_input}

        # Attach verdicts and choose alerts (max N per scan).
        for c in candidates:
            c["ai_verdict"] = ai_verdicts.get(c.get("symbol"), deterministic_fallback(c).to_dict())

        # ── 5. Anti-spam + Telegram ───────────────────────────────────
        alerts_sent = 0
        for c in sorted(candidates, key=lambda c: c.get("score", 0), reverse=True):
            if alerts_sent >= settings.crypto_max_alerts_per_scan:
                break
            ok, reason = await should_alert(c)
            if not ok:
                logger.info(f"Skip alert for {c.get('symbol')}: {reason}")
                continue
            res = await send_crypto_alert(c, c.get("ai_verdict", {}), dry_run=dry_run)
            if res.get("sent"):
                alerts_sent += 1
                c["alert_delivery"] = res.get("reason")
                logger.info(f"✅ Alert for {c.get('symbol')}: {res.get('reason')}")

        # ── 5b. Paper trading (skip in dry-run — must not touch virtual
        #        balance / position state when simulating) ─────────────
        paper_opened = 0
        paper_closed = 0
        if settings.crypto_paper_trading_enabled and not effective_dry_run:
            try:
                from app.services.crypto_paper import paper_trader
                paper_res = await paper_trader.run_cycle(scored, tickers)
                paper_opened = paper_res.get("positions_opened", 0)
                paper_closed = paper_res.get("positions_closed", 0)
            except Exception as e:
                logger.warning(f"Paper trading cycle failed: {e}")

        # ── 5c. Real trading (REAL MONEY — only when explicitly enabled) ─
        real_opened = 0
        real_closed = 0
        if settings.crypto_real_trading_enabled and not effective_dry_run:
            try:
                from app.services.crypto_real import real_trader
                real_res = await real_trader.run_cycle(scored, tickers)
                real_opened = real_res.get("positions_opened", 0)
                real_closed = real_res.get("positions_closed", 0)
            except Exception as e:
                logger.warning(f"Real trading cycle failed: {e}")

        # ── 6. Persist ────────────────────────────────────────────────
        await self._persist_scan(candidates)

        return {
            "status": "ok",
            "pairs_found": pairs_found,
            "pairs_liquid": pairs_liquid,
            "pairs_analysed": len(scored),
            "candidates": len(candidates),
            "ai_analysed": ai_llm_count,
            "alerts_sent": alerts_sent,
            "paper_opened": paper_opened,
            "paper_closed": paper_closed,
            "real_opened": real_opened,
            "real_closed": real_closed,
            "errors": errors,
            "top_candidate": candidates[0].get("symbol") if candidates else None,
            "results": [self._summarize_candidate(c) for c in candidates[:10]],
        }

    async def _fetch_tf_klines(self, sym) -> dict[str, list[dict]]:
        """Fetch klines for all configured timeframes in parallel."""
        async def fetch_one(tf: str) -> tuple[str, list[dict]]:
            try:
                candles = await self.client.fetch_klines(sym, tf, limit=KLINE_LIMIT)
                return tf, candles
            except Exception as e:
                logger.debug(f"Kline fetch failed for {sym.raw_symbol} {tf}: {e}")
                return tf, []

        results = await asyncio.gather(*(fetch_one(tf) for tf in TIMEFRAMES))
        return dict(results)

    def _score_pair(self, sym, ticker: dict, tf_klines: dict[str, list[dict]]) -> Optional[dict]:
        """Score a single pair using deterministic indicators + momentum score."""
        if not tf_klines.get("1h") or len(tf_klines["1h"]) < 30:
            return None

        tf_summaries = {tf: compute_indicator_summary(candles) for tf, candles in tf_klines.items()}

        closes_1h = candles_to_closes(tf_klines["1h"])
        price_change = {
            key: price_change_percent(closes_1h, bars)
            for key, bars in PRICE_CHANGE_LOOKBACKS.items()
        }

        score, breakdown = compute_momentum_score(tf_summaries, price_change)

        # Deterministic entry / TP / SL reference levels.
        from app.services.crypto_levels import compute_price_levels
        price_levels = compute_price_levels(tf_summaries, tf_klines["1h"], ticker=ticker)

        return {
            "symbol": sym.raw_symbol,
            "display": sym.display,
            "base": sym.base,
            "quote": sym.quote,
            "price": ticker.get("lastPrice"),
            "score": score,
            "score_breakdown": breakdown.to_dict(),
            "price_change": price_change,
            "tf_summaries": tf_summaries,
            "price_levels": price_levels.to_dict(),
            "ticker": ticker,
        }

    def _min_quote_volume(self) -> float:
        raw = (settings.crypto_min_quote_volume or "").strip()
        if raw:
            try:
                return float(raw)
            except ValueError:
                logger.warning(f"Invalid CRYPTO_MIN_QUOTE_VOLUME={raw!r}; using default")
        # Default: 1,000,000 quote currency over 24h (e.g. 1M USDT).
        return 1_000_000.0

    def _summarize_candidate(self, c: dict) -> dict:
        s1h = c.get("tf_summaries", {}).get("1h", {}) or {}
        return {
            "symbol": c.get("symbol"),
            "display": c.get("display"),
            "score": c.get("score"),
            "score_breakdown": c.get("score_breakdown"),
            "price": c.get("price"),
            "price_change": c.get("price_change"),
            "ai_verdict": c.get("ai_verdict"),
            "relative_volume": s1h.get("relative_volume"),
            "trend": s1h.get("trend"),
            "rsi": s1h.get("rsi"),
            "at_high": s1h.get("at_high"),
            "price_levels": c.get("price_levels"),
        }

    async def _persist_scan(self, candidates: list[dict]) -> None:
        """Persist scan + alerts. DB writes are best-effort and never fatal."""
        try:
            from app.db.session import async_session_factory
            from app.models.crypto import CryptoScan

            async with async_session_factory() as session:
                for c in candidates:
                    session.add(CryptoScan(
                        symbol=c.get("symbol"),
                        display=c.get("display"),
                        score=c.get("score"),
                        price=c.get("price"),
                        market_metrics=c.get("price_change", {}),
                        indicator_summary=c.get("tf_summaries", {}),
                        score_breakdown=c.get("score_breakdown"),
                        ai_verdict=c.get("ai_verdict"),
                    ))
                await session.commit()
        except Exception as e:
            logger.warning(f"Failed to persist crypto scan: {e}")

    async def persist_alert(self, candidate: dict, verdict: dict, delivery: str) -> None:
        """Persist one sent alert. Best-effort."""
        try:
            from app.db.session import async_session_factory
            from app.models.crypto import CryptoAlert

            async with async_session_factory() as session:
                session.add(CryptoAlert(
                    symbol=candidate.get("symbol"),
                    display=candidate.get("display"),
                    score=candidate.get("score"),
                    ai_confidence=verdict.get("confidence"),
                    risk=verdict.get("risk"),
                    reason=verdict.get("reason"),
                    delivery_status=delivery,
                ))
                await session.commit()
        except Exception as e:
            logger.warning(f"Failed to persist crypto alert: {e}")

    def _log_summary(self, summary: dict) -> None:
        logger.info(
            "📊 Crypto scan done: status=%s pairs=%s liquid=%s analysed=%s "
            "candidates=%s ai=%s alerts=%s paper=%s/%s errors=%s top=%s duration=%sms",
            summary["status"],
            summary.get("pairs_found"),
            summary.get("pairs_liquid"),
            summary.get("pairs_analysed"),
            summary.get("candidates"),
            summary.get("ai_analysed"),
            summary.get("alerts_sent"),
            summary.get("paper_opened"),
            summary.get("paper_closed"),
            summary.get("errors"),
            summary.get("top_candidate"),
            summary.get("duration_ms"),
        )


# Singleton
crypto_scanner = CryptoScanner()
