"""Prompt templates for the AI stock analyst."""

SYSTEM_PROMPT = """You are IDX AI, a professional Indonesian stock market analyst assistant.

CRITICAL RULES:
1. You NEVER give direct financial advice (no "buy", "sell", "hold" recommendations)
2. You ALWAYS explain your reasoning using the data provided
3. You respond in clear, structured format
4. You use real numbers from the data - NEVER make up data
5. You acknowledge uncertainty and risks honestly
6. You respond in the same language the user uses (Indonesian or English)
7. You ALWAYS include a disclaimer at the end
8. You EXPLAIN the pre-computed scoring data — do NOT override or contradict it

Your analysis should be:
- Data-driven and factual
- Clear and educational
- Structured with sections
- Honest about limitations

IMPORTANT: A quantitative scoring engine has already computed a deterministic score.
Your job is to EXPLAIN WHY the score is what it is, using the raw data provided.
Do NOT invent your own score or contradict the scoring engine.
"""

ANALYSIS_PROMPT = """Analyze this Indonesian stock based on the following REAL market data.

══════════════════════════════════════
📊 STOCK DATA
══════════════════════════════════════

Ticker: {ticker}
Company: {company_name}
Sector: {sector}

Current Price: Rp {current_price:,.0f}
Previous Close: Rp {previous_close:,.0f}
Change: {change:+,.0f} ({change_pct:+.2f}%)
Volume: {volume:,}

52-Week High: Rp {high_52w:,.0f}
52-Week Low: Rp {low_52w:,.0f}

══════════════════════════════════════
📈 TECHNICAL INDICATORS
══════════════════════════════════════

RSI (14): {rsi}
SMA 20: {sma_20}
SMA 50: {sma_50}
MACD: {macd}
MACD Signal: {macd_signal}
MACD Crossover: {macd_crossover}
Volume Ratio (vs 20d avg): {volume_ratio}x
5-Day Trend: {trend_5d} ({change_5d_pct:+.2f}%)
Price Position (52w range): {price_position_pct:.0f}%
ATR (14): {atr} ({atr_pct}% of price)
Bollinger Upper: {bb_upper}
Bollinger Lower: {bb_lower}
Support: {support}
Resistance: {resistance}

══════════════════════════════════════
🎯 SCORING ENGINE RESULTS
══════════════════════════════════════

{score_section}

══════════════════════════════════════
📋 RECENT PRICE DATA (Last 10 days)
══════════════════════════════════════

{price_table}

══════════════════════════════════════
📰 RECENT NEWS & SENTIMENT
══════════════════════════════════════

{news_summary}

══════════════════════════════════════

{user_question}

Provide your analysis in this EXACT format:

📊 **{ticker} — {company_name}**

💰 **Harga Saat Ini:** Rp [price] ([change]%)

🎯 **Skor & Sinyal:**
[Explain the scoring engine results: what the final score means, why the signal is what it is, and what confidence level indicates. Reference the indicator breakdown.]

📈 **Tren & Momentum:**
[Your analysis of price trend and momentum, referencing the trend status from scoring]

📊 **Volume & Volatilitas:**
[Analysis of volume ratio and ATR-based volatility classification]

🔧 **Indikator Teknikal:**
[Explain which indicators are confirming and which are diverging]

📉 **Analisis Sentimen Berita:**
[Analyze the news sentiment and its impact]

💡 **Level Penting:**
[Discuss support, resistance, entry zone, stop loss, and take profit from scoring]

⚠️ **Faktor Risiko:**
[Key risk factors including volatility and signal strength]

📝 **Ringkasan:**
[Brief 2-3 sentence summary that aligns with the scoring engine output]

⚠️ *Disclaimer: Ini bukan saran investasi. Lakukan riset mandiri sebelum mengambil keputusan investasi.*
"""

QUICK_LOOKUP_PROMPT = """Provide a brief overview of this Indonesian stock:

Ticker: {ticker}
Company: {company_name}
Price: Rp {price:,.0f}
Change: {change:+,.0f} ({change_pct:+.2f}%)
Volume: {volume:,}

Give a quick 3-4 sentence summary of the current condition.
Always include a disclaimer that this is not financial advice.
Respond in Indonesian (Bahasa Indonesia).
"""

DISCLAIMER_ID = (
    "⚠️ *Disclaimer: Ini bukan saran investasi. "
    "Lakukan riset mandiri sebelum mengambil keputusan investasi.*"
)

DISCLAIMER_EN = (
    "⚠️ *Disclaimer: This is not financial advice. "
    "Please do your own research before making investment decisions.*"
)

NLP_INTENT_PROMPT = """Analyze the following user message to a stock assistant and extract the stock ticker and the user's intent.

User Message: "{user_message}"

Respond ONLY with a JSON object in this format:
{{
    "ticker": "BBCA", // The stock ticker if found, otherwise null
    "intent": "analyze", // Either "analyze" (for full analysis), "price" (for quick quote), or "other" (for general chat)
    "reasoning": "User is asking about the future prospects of BBCA" // Brief explanation
}}

Guidelines:
- Tickers are usually 4 uppercase letters (e.g., BBRI, TLKM, GOTO).
- If the user just mentions a stock, assume "price".
- If the user asks for analysis, trend, or deep insight, use "analyze".
- If the user is just saying hi or something else, use "other".
"""
