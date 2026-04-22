
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
    """Handle natural language messages."""
    text = update.message.text.strip()
    
    # Send typing indicator
    await update.message.chat.send_action("typing")
    
    try:
        # 1. Ask LLM to extract intent and ticker
        prompt = NLP_INTENT_PROMPT.format(user_message=text)
        response = await llm_client.generate(
            system_prompt="You are a helper that extracts stock ticker and intent from user messages. Respond only in JSON.",
            user_prompt=prompt,
            temperature=0.1, # Keep it deterministic
            max_tokens=200
        )
        
        # 2. Parse JSON response
        try:
            # Clean up potential markdown formatting in response
            json_str = response.strip()
            if json_str.startswith("```json"):
                json_str = json_str[7:-3].strip()
            elif json_str.startswith("```"):
                json_str = json_str[3:-3].strip()
                
            data = json.loads(json_str)
            ticker = data.get("ticker")
            intent = data.get("intent", "other")
        except Exception as e:
            logger.error(f"Failed to parse NLP response: {response}. Error: {e}")
            # Fallback: look for 4-letter uppercase words
            matches = re.findall(r'\b[A-Z]{4}\b', text.upper())
            ticker = matches[0] if matches else None
            intent = "analyze" if ticker else "other"

        # 3. Route based on intent
        if ticker:
            ticker = ticker.upper()
            context.args = [ticker]
            
            if intent == "analyze":
                # For NLP, we pass the original text as a question
                logger.info(f"NLP Routing to analyze: {ticker} (reason: {data.get('reasoning')})")
                await analyze_handler(update, context)
            else:
                logger.info(f"NLP Routing to stock lookup: {ticker}")
                await stock_handler(update, context)
        else:
            # General chat or no ticker found
            logger.info("NLP: No ticker found, responding as general assistant")
            general_response = await llm_client.generate(
                system_prompt="You are IDX AI, a helpful Indonesian stock assistant. Respond briefly to the user.",
                user_prompt=text,
                temperature=0.7
            )
            await update.message.reply_text(general_response)

    except Exception as e:
        logger.error(f"Error in nlp_handler: {e}")
        await update.message.reply_text(
            "💡 Maaf, saya sedang kesulitan memahami pesan Anda.\n\n"
            "Coba gunakan perintah langsung seperti `/stock BBCA` atau `/analyze BBCA`."
        )
