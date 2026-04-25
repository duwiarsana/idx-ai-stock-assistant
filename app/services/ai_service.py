"""AI analysis service — orchestrates scoring engine + LLM for analysis."""

import logging
from datetime import datetime
from typing import Optional

from app.ai.llm_client import llm_client
from app.ai.prompts import (
    SYSTEM_PROMPT,
    ANALYSIS_PROMPT,
    QUICK_LOOKUP_PROMPT,
    DISCLAIMER_ID,
)
from app.services.stock_service import stock_service
from app.services.cache_service import cache_service
from app.services.analysis_engine import analyze as run_analysis, format_score_card, AnalysisResult
from app.data.news_fetcher import news_fetcher

logger = logging.getLogger(__name__)


class AIService:
    """Orchestrates stock data retrieval, deterministic scoring, and AI analysis."""

    def __init__(self):
        self.llm = llm_client
        self.stocks = stock_service
        self.cache = cache_service

    async def analyze_stock(
        self,
        ticker: str,
        user_question: Optional[str] = None,
    ) -> dict:
        """
        Full AI analysis of a stock.

        Flow:
        1. Fetch stock data (with cache)
        2. Calculate technicals
        3. Run deterministic scoring engine
        4. Build prompt with real data + score card
        5. Send to LLM (LLM explains the scores, doesn't invent them)
        6. Return structured response

        Returns:
            dict with analysis text, score_data, data summary, disclaimer
        """
        ticker = ticker.upper().strip()

        # Check analysis cache first (15 min)
        if not user_question:
            cached = await self.cache.get_analysis(ticker)
            if cached:
                logger.debug(f"Analysis cache hit for {ticker}")
                return cached

        # Fetch full stock data
        data = await self.stocks.get_stock_data(ticker)
        if not data:
            return {
                "ticker": ticker,
                "company_name": "Unknown",
                "analysis": f"❌ Tidak dapat menemukan data untuk ticker **{ticker}**.\n\n"
                            f"Pastikan kode saham benar (contoh: BBCA, TLKM, ASII).",
                "score_data": None,
                "score_card": "",
                "data_summary": {},
                "disclaimer": DISCLAIMER_ID,
                "generated_at": datetime.now().isoformat(),
            }

        # Prepare technicals and news
        technicals = data.get("technicals", {})
        price_table = self.stocks.format_price_table(data.get("history", []))
        news_summary = await news_fetcher.get_news_summary_text(f"{ticker} saham indonesia", limit=10)

        # ── Run deterministic scoring engine ──────────────────────────
        history = data.get("history", [])
        score_result: Optional[AnalysisResult] = run_analysis(ticker, history)

        score_card_text = ""
        score_section = "Scoring engine: Insufficient data for scoring."
        score_data_dict = None

        if score_result:
            # ── ML Prediction ─────────────────────────────────────────
            try:
                from app.services.ml_predictor import ml_predictor

                ml_features = ml_predictor.extract_features({
                    **technicals,
                    "current_price": float(data.get("current_price", 0)),
                })
                ml_pred = ml_predictor.predict(ticker, ml_features)

                if ml_pred:
                    score_result.ml_probability = ml_pred.probability
                    score_result.ml_direction = ml_pred.direction
                    ml_score = ml_pred.probability * 100
                    score_result.combined_score = round(
                        score_result.final_score * 0.6 + ml_score * 0.4, 1
                    )
            except Exception as ml_err:
                logger.debug(f"ML prediction skipped for {ticker}: {ml_err}")

            score_card_text = format_score_card(score_result)
            score_data_dict = score_result.to_dict()

            # Build a structured score section for the LLM prompt
            ind_lines = []
            for name, detail in score_result.indicators.items():
                ind_lines.append(
                    f"  {name}: normalized={detail['normalized']:.2f}, "
                    f"weight={detail['weight']}, signal={detail['signal']}"
                )
            indicators_text = "\n".join(ind_lines)

            score_section = (
                f"Final Score: {score_result.final_score}/100\n"
                f"Confidence: {score_result.confidence}\n"
                f"Signal: {score_result.signal} ({score_result.signal_strength})\n"
                f"Trend: {score_result.trend_status}\n"
                f"Risk/Reward Ratio: 1:{score_result.risk_reward_ratio}\n"
                f"Volatility: {score_result.volatility} (ATR: {score_result.atr:,.0f})\n"
                f"Support: Rp {score_result.support:,.0f}\n"
                f"Resistance: Rp {score_result.resistance:,.0f}\n"
                f"Entry Zone: Rp {score_result.entry_zone['low']:,.0f} – {score_result.entry_zone['high']:,.0f}\n"
                f"Stop Loss: Rp {score_result.stop_loss:,.0f}\n"
                f"Take Profit: Rp {score_result.take_profit:,.0f}\n"
                f"Confirming Indicators: {score_result.confirming_indicators}/5\n\n"
                f"Indicator Breakdown:\n{indicators_text}"
            )

            # Add ML section if available
            if score_result.ml_probability is not None:
                score_section += (
                    f"\n\nML Prediction: {score_result.ml_direction} "
                    f"({score_result.ml_probability * 100:.0f}% probability)\n"
                    f"Combined Score (Tech 60% + ML 40%): {score_result.combined_score}"
                )

        # Build the analysis prompt with real data + scoring data
        prompt = ANALYSIS_PROMPT.format(
            ticker=ticker,
            company_name=data.get("name", "Unknown"),
            sector=data.get("sector", "N/A"),
            current_price=float(data.get("current_price", 0)),
            previous_close=float(data.get("previous_close", 0)),
            change=float(data.get("change", 0)),
            change_pct=float(data.get("change_pct", 0)),
            volume=data.get("volume", 0),
            high_52w=float(data.get("high_52w", 0) or 0),
            low_52w=float(data.get("low_52w", 0) or 0),
            rsi=technicals.get("rsi_14", "N/A"),
            sma_20=technicals.get("sma_20", "N/A"),
            sma_50=technicals.get("sma_50", "N/A"),
            macd=technicals.get("macd", "N/A"),
            macd_signal=technicals.get("macd_signal", "N/A"),
            macd_crossover=technicals.get("macd_crossover", "N/A"),
            volume_ratio=technicals.get("volume_ratio", "N/A"),
            trend_5d=technicals.get("trend_5d", "N/A"),
            change_5d_pct=float(technicals.get("change_5d_pct", 0) or 0),
            price_position_pct=float(technicals.get("price_position_pct", 50) or 50),
            atr=technicals.get("atr_14", "N/A"),
            atr_pct=technicals.get("atr_pct", "N/A"),
            bb_upper=technicals.get("bb_upper", "N/A"),
            bb_lower=technicals.get("bb_lower", "N/A"),
            support=technicals.get("support", "N/A"),
            resistance=technicals.get("resistance", "N/A"),
            price_table=price_table,
            news_summary=news_summary,
            score_section=score_section,
            user_question=(
                f"\nUser's specific question: {user_question}" if user_question
                else "\nProvide a comprehensive general analysis."
            ),
        )

        # Generate AI analysis
        analysis_text = await self.llm.generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=0.6,
            max_tokens=2000,
        )

        # Ensure disclaimer is included
        if "bukan saran investasi" not in analysis_text.lower():
            analysis_text += f"\n\n{DISCLAIMER_ID}"

        result = {
            "ticker": ticker,
            "company_name": data.get("name", "Unknown"),
            "analysis": analysis_text,
            "score_data": score_data_dict,
            "score_card": score_card_text,
            "history": data.get("history", []),
            "data_summary": {
                "price": float(data.get("current_price", 0)),
                "change_pct": float(data.get("change_pct", 0)),
                "volume": data.get("volume", 0),
                "rsi": technicals.get("rsi_14"),
                "macd_crossover": technicals.get("macd_crossover"),
                "trend_5d": technicals.get("trend_5d"),
                "final_score": score_result.final_score if score_result else None,
                "signal": score_result.signal if score_result else None,
                "confidence": score_result.confidence if score_result else None,
            },
            "disclaimer": DISCLAIMER_ID,
            "generated_at": datetime.now().isoformat(),
        }

        # Cache if no specific question (general analysis)
        if not user_question:
            await self.cache.set_analysis(ticker, result)

        return result

    async def quick_lookup(self, ticker: str) -> str:
        """Quick stock lookup with brief AI commentary."""
        ticker = ticker.upper().strip()

        quote = await self.stocks.get_quick_quote(ticker)
        if not quote:
            return (
                f"❌ Tidak dapat menemukan data untuk **{ticker}**.\n"
                f"Pastikan kode saham benar (contoh: BBCA, TLKM, ASII)."
            )

        # Format quick response without LLM (faster)
        arrow = "📈" if float(quote["change_pct"]) > 0 else "📉" if float(quote["change_pct"]) < 0 else "➡️"

        response = (
            f"📊 **{quote['ticker']}** — {quote['name']}\n\n"
            f"💰 Harga: **Rp {float(quote['price']):,.0f}**\n"
            f"{arrow} Perubahan: {float(quote['change']):+,.0f} ({float(quote['change_pct']):+.2f}%)\n"
            f"📦 Volume: {quote['volume']:,}\n\n"
            f"_Ketik /analyze {ticker} untuk analisis lengkap_\n\n"
            f"{DISCLAIMER_ID}"
        )

        return response


# Singleton
ai_service = AIService()
