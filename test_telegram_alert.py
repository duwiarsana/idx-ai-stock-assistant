#!/usr/bin/env python3
"""Send test alert to Telegram."""

import asyncio
import httpx

BOT_TOKEN = "8898405035:AAHLhE6RXCaHm_HymaUChqfBYC5U_iVxT1s"
ADMIN_ID = "5994671522"

async def send_test_alert():
    """Send test alert to Telegram."""
    
    message = """
🚨 *STRONG BUY ALERT* 🚨

📈 *BBCA* - Bank Central Asia Tbk
💰 Price: Rp 9,500 (+2.5%)
📊 Score: 78.5/100

┌─────────────────────────────┐
│  🎯 SIGNAL: BUY            │
│  💪 Conviction: 82%        │
│  📊 Volume: 2.3x avg       │
└─────────────────────────────┘

🔍 *Technical Analysis:*
• RSI: 58.5 (Neutral-Bullish)
• MACD: BULLISH crossover
• Trend: UPTREND
• Support: 9,200
• Resistance: 9,800

📊 *Fundamental:*
• PER: 12.5x
• PBV: 2.8x
• ROE: 18.5%
• Sector: Financials

💡 *Recommendation:*
• Entry: 9,400-9,500
• TP1: 9,800 (+3.2%)
• TP2: 10,200 (+7.4%)
• SL: 9,100 (-4.2%)
• Risk/Reward: 1:2.5

⚠️ *Disclaimer:* Do your own research!

━━━━━━━━━━━━━━━━━━━━
🧪 *TEST ALERT* - Ini adalah test message dari sistem IDX AI Stock Scanner.
"""
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    payload = {
        "chat_id": ADMIN_ID,
        "text": message.strip(),
        "parse_mode": "Markdown"
    }
    
    print("="*80)
    print("SENDING TEST ALERT TO TELEGRAM...")
    print("="*80)
    print(f"Bot Token: {BOT_TOKEN[:20]}...")
    print(f"Admin ID: {ADMIN_ID}")
    print("="*80)
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=10)
            result = response.json()
            
            if result.get('ok'):
                print("\n✅ SUCCESS! Alert sent to Telegram!")
                print(f"   Message ID: {result.get('result', {}).get('message_id')}")
                print("\n📱 Check your Telegram now!")
            else:
                print(f"\n❌ Failed: {result}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    
    print("="*80)

if __name__ == '__main__':
    asyncio.run(send_test_alert())
