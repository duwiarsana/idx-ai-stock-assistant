"""AI analysis service — orchestrates stock data + LLM for analysis."""

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
from app.data.news_fetcher import news_fetcher

logger = logging.getLogger(__name__)


class AIService:
    """Orchestrates stock data retrieval and AI-powered analysis."""

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

        1. Fetch stock data (with cache)
        2. Calculate technicals
        3. Build prompt with real data
        4. Send to LLM
        5. Return structured response

        Returns:
            dict with analysis text, data summary, disclaimer
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
                "data_summary": {},
                "disclaimer": DISCLAIMER_ID,
                "generated_at": datetime.now().isoformat(),
            }

        # Prepare technicals and news
        technicals = data.get("technicals", {})
        price_table = self.stocks.format_price_table(data.get("history", []))
        news_summary = await news_fetcher.get_news_summary_text(ticker)

        # Build the analysis prompt with real data
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
            price_table=price_table,
            news_summary=news_summary,
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
            "history": data.get("history", []),
            "data_summary": {
                "price": float(data.get("current_price", 0)),
                "change_pct": float(data.get("change_pct", 0)),
                "volume": data.get("volume", 0),
                "rsi": technicals.get("rsi_14"),
                "macd_crossover": technicals.get("macd_crossover"),
                "trend_5d": technicals.get("trend_5d"),
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
