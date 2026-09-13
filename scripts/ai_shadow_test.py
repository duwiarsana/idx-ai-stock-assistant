#!/usr/bin/env python3
"""AI shadow test — compare LLM verdicts vs the deterministic gate on the live
shortlist WITHOUT trading anything.

Runs one read-only scan (no positions, no alerts, no DB writes), feeds the exact
shortlist the paper/real engines would see into the LLM, and prints a
deterministic-vs-AI comparison + a rough token/cost estimate. A JSON snapshot is
saved so decisions can be re-evaluated against actual fills later.

Usage:
    python scripts/ai_shadow_test.py [--limit N] [--offline]

--offline reconstructs candidates from the bot's last DB scan snapshots and
fetches fresh klines for the top symbols only (no tickers call) — useful when
Tokocrypto's /ticker/24hr rate limit is hot.

Relies on the container working directory (/app) — the scanner uses relative
paths only for persistence, which we avoid here.
"""

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.data.tokocrypto_client import tokocrypto_client
from app.services.crypto_ai import analyze_candidates, deterministic_fallback
from app.services.crypto_real import passes_entry_gate
from app.services.crypto_scanner import (
    CryptoScanner,
    _parse_quotes,
    _parse_stablequotes,
)

settings = get_settings()

# gpt-oss-120b pricing (USD per 1M tokens) — adjust if model changes.
PRICE_PER_M_IN = 0.36
PRICE_PER_M_OUT = 1.0
EST_OUTPUT_TOKENS = 1000  # empirical for a JSON verdict array


async def scan_candidates(scanner: CryptoScanner, limit: Optional[int]) -> tuple[list[dict], list]:
    """Replicate the scanner's candidate pipeline read-only (no persistence)."""
    symbols = await scanner.client.fetch_symbols()
    tickers = await scanner.client.fetch_tickers()

    quotes = _parse_quotes(settings.crypto_quote_assets) or ["USDT"]
    stable = _parse_stablequotes(settings.crypto_stablecoin_quotes)
    quote_set = set(q.upper() for q in quotes)
    filtered = [
        s for s in symbols
        if s.quote in quote_set and s.base not in stable and s.spot_trading
    ]

    min_qv = scanner._min_quote_volume()
    liquid = [
        (s, t) for s in filtered
        if (t := tickers.get(s.normalized_symbol)) is not None
        and (t.get("quoteVolume") or 0) >= min_qv
    ]
    liquid.sort(key=lambda item: (item[1].get("quoteVolume") or 0), reverse=True)
    liquid = liquid[: max(settings.crypto_min_volume_pairs, 50)]

    scored: list[dict] = []
    sem = asyncio.Semaphore(settings.crypto_max_concurrency)

    async def analyse(sym, ticker):
        try:
            async with sem:
                tf_klines = await scanner._fetch_tf_klines(sym)
            if not tf_klines.get("1h"):
                return
            c = scanner._score_pair(sym, ticker, tf_klines)
            if c is not None:
                scored.append(c)
        except Exception:
            pass

    await asyncio.gather(*(analyse(s, t) for s, t in liquid))
    scored.sort(key=lambda c: c.get("score", 0), reverse=True)
    candidates = [c for c in scored if c.get("score", 0) >= settings.crypto_min_score_alert]
    return candidates, scored


async def scan_offline(scanner: CryptoScanner, limit: Optional[int]) -> tuple[list[dict], list]:
    """Reconstruct candidates from the bot's own last scan snapshots in the DB,
    fetching fresh klines only for the top symbols (no tickers call — resilient
    to Tokocrypto ticker rate-limits)."""
    from sqlalchemy import select
    from app.db.session import async_session_factory
    from app.models.crypto import CryptoScan
    from app.services.crypto_indicators import (
        candles_to_closes,
        compute_indicator_summary,
        price_change_percent,
    )
    from app.services.crypto_levels import compute_price_levels
    from app.services.crypto_scanner import PRICE_CHANGE_LOOKBACKS
    from app.services.crypto_scoring import compute_momentum_score

    symbols = await scanner.client.fetch_symbols()
    by_raw = {s.raw_symbol: s for s in symbols}

    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(CryptoScan).order_by(CryptoScan.id.desc()).limit(600)
            )
        ).scalars().all()

    best = {}
    for r in rows:
        if r.symbol not in best or (r.score or 0) > (best[r.symbol].score or 0):
            best[r.symbol] = r
    top = sorted(best.values(), key=lambda r: r.score or 0, reverse=True)[: (limit or 10)]

    lookback = settings.crypto_ai_candle_lookback or 0
    scored: list[dict] = []
    for r in top:
        sym = by_raw.get(r.symbol)
        if sym is None:
            continue
        tf_klines = {}
        for tf in ("1h", "15m"):
            try:
                tf_klines[tf] = await scanner.client.fetch_klines(sym, tf, limit=200)
            except Exception:
                tf_klines[tf] = []
        if not tf_klines.get("1h"):
            continue
        tf_summaries = {tf: compute_indicator_summary(c) for tf, c in tf_klines.items()}
        closes_1h = candles_to_closes(tf_klines["1h"])
        price_change = {
            k: price_change_percent(closes_1h, bars)
            for k, bars in PRICE_CHANGE_LOOKBACKS.items()
        }
        score, breakdown = compute_momentum_score(tf_summaries, price_change)
        series = {}
        if lookback > 0:
            series = {
                tf: [round(c, 6) for c in candles_to_closes(tf_klines[tf])[-lookback:]]
                for tf in ("1h", "15m")
                if tf_klines.get(tf)
            }
        levels = compute_price_levels(tf_summaries, tf_klines["1h"])
        scored.append({
            "symbol": r.symbol,
            "display": r.display or r.symbol,
            "base": sym.base,
            "quote": sym.quote,
            "price": r.price,
            "score": score,
            "score_breakdown": breakdown.to_dict(),
            "price_change": price_change,
            "tf_summaries": tf_summaries,
            "price_levels": levels.to_dict(),
            "series": series,
            "ticker": {},
        })

    scored.sort(key=lambda c: c.get("score", 0), reverse=True)
    return scored, []


def cost_estimate(n_chars_input: int) -> dict:
    tok_in = max(1, n_chars_input // 4)
    return {
        "input_tokens_est": tok_in,
        "output_tokens_est": EST_OUTPUT_TOKENS,
        "usd_est": round(
            (tok_in * PRICE_PER_M_IN + EST_OUTPUT_TOKENS * PRICE_PER_M_OUT) / 1e6, 4
        ),
    }


async def main() -> int:
    limit = None
    if "--limit" in sys.argv:
        try:
            limit = int(sys.argv[sys.argv.index("--limit") + 1])
        except (ValueError, IndexError):
            limit = None

    t0 = time.monotonic()
    scanner = CryptoScanner()
    # The live bot also polls Tokocrypto every 5 min; give the shadow scan room
    # to ride out rate-limit windows without failing.
    scanner.client.max_retries = 8
    if "--offline" in sys.argv:
        print("Offline mode: reconstructing candidates from DB scan snapshots ...")
        scored, _ = await scan_offline(scanner, limit)
    else:
        try:
            scored, _ = await scan_candidates(scanner, limit)
        except Exception as e:
            print(f"Scan failed: {e} (try --offline to use the bot's DB snapshots)")
            return 2

    candidates = scored[: (limit or settings.crypto_max_candidates_ai + 10)]
    print(f"Scanned: {len(candidates)} top candidates")
    if not candidates:
        print("No candidates — nothing to analyse.")
        return 0

    sl = candidates[: settings.crypto_max_candidates_ai]
    gate_ok = {c["symbol"]: bool(passes_entry_gate(c)) for c in sl}
    n_gate = sum(gate_ok.values())
    print(f"Top {len(sl)} candidates (of {len(candidates)}): "
          f"{', '.join(c['symbol'] for c in sl)}")
    print(f"Pass deterministic 85-gate: {n_gate}/{len(sl)} "
          "(only these would feed the AI filter in production)")
    if not sl:
        print("No candidates — nothing to analyse.")
        return 0

    # Deterministic verdicts (what runs today with AI off).
    det = {c["symbol"]: deterministic_fallback(c) for c in sl}

    n_chars_input = 0
    from app.services.crypto_ai import build_candidate_payload

    n_chars_input = sum(len(json.dumps(build_candidate_payload(c).to_dict())) for c in sl)

    print(f"\nAsking LLM ({settings.groq_model}) on {len(sl)} symbols ...")
    ai: dict = {}
    try:
        ai = await analyze_candidates(sl)
    except Exception as e:
        print(f"LLM failed: {e} -> snapshot skipped")
        return 3

    print("\n{:<12} {:>6} {:<6} {:<14} {:<14} {:>5} {:>6}  {}".format(
        "SYMBOL", "SCORE", "GATE", "DETERMINISTIC", "LLM", "CONF", "RISK", "VERDICT"))
    print("-" * 96)
    agreement = disagreements = 0
    for c in sl:
        sym = c["symbol"]
        d = det[sym]
        a = ai.get(sym)
        same = d.verdict == a.verdict if a else False
        agreement += bool(same)
        disagreements += not same
        reason = (a.reason[0] if a and a.reason else "-")[:52]
        sym_disp = f"{sym:<12}"[:12]
        score = f"{c.get('score', 0):6.1f}"
        gate = "YES" if gate_ok.get(sym) else "-"
        print(f"{sym_disp} {score:>6} {gate:>6} {d.verdict:<14} {(a.verdict if a else 'N/A'):<14} "
              f"{(a.confidence if a else 0):>5}  {(a.risk if a else '-'):>6}  "
              f"{'AGREE' if same else 'DIFFERS'}  {reason}")

    est = cost_estimate(n_chars_input)
    print(f"\nAgreement: {agreement}/{len(sl)}   Disagreements: {disagreements}/{len(sl)}")
    print(f"Prompt chars: {n_chars_input:,}  (est tokens in: {est['input_tokens_est']:,})")
    print(f"Est. LLM cost per scan: ${est['usd_est']} "
          f"({est['input_tokens_est'] + est['output_tokens_est']:,} tokens total)")

    out_dir = Path(__file__).resolve().parent.parent / "data" / "ai_shadow"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    snap = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "model": settings.groq_model,
        "cost_est_usd": est["usd_est"],
        "results": [
            {
                "symbol": c["symbol"],
                "score": c.get("score"),
                "entry": (c.get("price_levels") or {}).get("entry"),
                "deterministic": det[c["symbol"]].to_dict(),
                "llm": ai[c["symbol"]].to_dict() if c["symbol"] in ai else None,
            }
            for c in sl
        ],
    }
    path = out_dir / f"snap_{stamp}.json"
    path.write_text(json.dumps(snap, indent=2))
    print(f"\nSnapshot: {path}  (elapsed {time.monotonic() - t0:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))