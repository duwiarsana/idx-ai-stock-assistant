
import logging
import json
import re
from telegram import Update
from telegram.ext import ContextTypes

from app.services.ai_service import ai_service
from app.ai.llm_client import llm_client
from app.ai.prompts import NLP_INTENT_PROMPT
from app.bot.handlers.stock import stock_handler
from app.bot.handlers.analyze import analyze_handler

logger = logging.getLogger(__name__)

async def nlp_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle natural language messages with memory."""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    # Send typing indicator
    await update.message.chat.send_action("typing")
    
    # 0. Get chat history
    from app.services.cache_service import cache_service
    history = await cache_service.get_history(user_id)
    
    try:
        # 1. Ask LLM to extract intent and ticker
        # We also pass history to help understand pronouns like "it", "that stock", etc.
        history_context = ""
        if history:
            history_context = "Context from previous messages:\n"
            for msg in history[-3:]: # last 3 for context
                history_context += f"{msg['role']}: {msg['content']}\n"

        prompt = f"{history_context}\nUser Message: \"{text}\"\n\n{NLP_INTENT_PROMPT}"
        response = await llm_client.generate(
            system_prompt="You are a helper that extracts stock ticker and intent. Respond only in JSON.",
            user_prompt=prompt,
            temperature=0.1,
            max_tokens=200
        )
        
        # 2. Parse JSON response
        try:
            # ... (parsing logic) ...
            json_str = response.strip()
            if json_str.startswith("```json"):
                json_str = json_str[7:-3].strip()
            elif json_str.startswith("```"):
                json_str = json_str[3:-3].strip()
                
            data = json.loads(json_str)
            ticker = data.get("ticker")
            intent = data.get("intent", "other")
            query = data.get("query", text)
            region = data.get("region", "ID")
            if region == "AUTO":
                region = "ID"
        except Exception as e:
            logger.error(f"Failed to parse NLP response: {response}. Error: {e}")
            ticker = None
            intent = "other"
            query = text
            region = "ID"

        # 3. Route based on intent
        response_text = ""
        if ticker:
            ticker = ticker.upper()
            context.args = [ticker]
            
            if intent == "analyze" or intent == "news":
                logger.info(f"NLP Routing to analyze: {ticker}")
                # Analyze handler will send its own response
                await analyze_handler(update, context)
                # We don't save to history here as analyze_handler is a complex flow
                return 
            else:
                logger.info(f"NLP Routing to stock lookup: {ticker}")
                await stock_handler(update, context)
                return
        elif intent == "news":
            logger.info(f"NLP: General news request for '{query}'")
            from app.data.news_fetcher import news_fetcher
            news_text = await news_fetcher.get_news_summary_text(query, limit=7, region=region)
            
            response_text = await llm_client.generate(
                system_prompt="You are IDX AI. Summarize the news and remember the context.",
                user_prompt=f"Berikut berita terbaru untuk '{query}':\n{news_text}",
                history=history,
                temperature=0.7
            )
        else:
            logger.info("NLP: Responding as general assistant with memory")
            response_text = await llm_client.generate(
                system_prompt="You are IDX AI, a helpful Indonesian stock assistant. Use the history to provide context.",
                user_prompt=text,
                history=history,
                temperature=0.7
            )

        if response_text:
            try:
                await update.message.reply_text(response_text, parse_mode="Markdown")
            except Exception:
                await update.message.reply_text(response_text)
                
            # 4. Save to history
            await cache_service.add_to_history(user_id, "user", text)
            await cache_service.add_to_history(user_id, "assistant", response_text)

    except Exception as e:
        logger.error(f"Error in nlp_handler: {e}")
        await update.message.reply_text("💡 Maaf, saya sedang kesulitan memahami pesan Anda.")

