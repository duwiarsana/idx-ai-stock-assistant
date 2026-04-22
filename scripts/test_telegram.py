
import asyncio
import os
from dotenv import load_dotenv
from telegram import Bot

async def test_telegram():
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN not found in .env")
        return
        
    print(f"Testing Telegram Bot Token: {token[:10]}...")
    bot = Bot(token)
    
    try:
        me = await bot.get_me()
        print(f"✅ Success! Bot Name: @{me.username} (ID: {me.id})")
    except Exception as e:
        print(f"❌ Error connecting to Telegram: {e}")

if __name__ == "__main__":
    asyncio.run(test_telegram())
