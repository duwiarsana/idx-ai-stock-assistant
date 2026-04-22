
import asyncio
import os
import sys
import json
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.ai.llm_client import llm_client
from app.ai.prompts import NLP_INTENT_PROMPT

async def test_nlp_extraction(message):
    print(f"\n--- Testing Message: '{message}' ---")
    prompt = NLP_INTENT_PROMPT.format(user_message=message)
    response = await llm_client.generate(
        system_prompt="You are a helper that extracts stock ticker and intent from user messages. Respond only in JSON.",
        user_prompt=prompt,
        temperature=0.1,
        max_tokens=200
    )
    
    print(f"LLM Response: {response}")
    try:
        # Simple cleanup
        json_str = response.strip()
        if json_str.startswith("```json"):
            json_str = json_str[7:-3].strip()
        elif json_str.startswith("```"):
            json_str = json_str[3:-3].strip()
        
        data = json.loads(json_str)
        print(f"Parsed Ticker: {data.get('ticker')}")
        print(f"Parsed Intent: {data.get('intent')}")
        print(f"Reasoning: {data.get('reasoning')}")
    except Exception as e:
        print(f"Failed to parse JSON: {e}")

async def main():
    load_dotenv()
    test_messages = [
        "Gimana prospek BBCA?",
        "Tolong cek harga TLKM dong",
        "Bagus gak ya beli GOTO sekarang?",
        "Halo IDX AI, apa kabar?",
        "ASII"
    ]
    
    for msg in test_messages:
        await test_nlp_extraction(msg)

if __name__ == "__main__":
    asyncio.run(main())
