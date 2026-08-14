#!/usr/bin/env python3
"""Send minimal alert with multiple stocks."""

import asyncio
import httpx

BOT_TOKEN = "8898405035:AAHLhE6RXCaHm_HymaUChqfBYC5U_iVxT1s"
ADMIN_ID = "5994671522"

async def send_minimal_alerts():
    """Send minimal format alerts for multiple stocks."""
    
    # Example: 3 stocks found in one scan
    stocks = [
        {
            'ticker': 'BBCA',
            'name': 'Bank Central Asia Tbk',
            'score': 78.5,
            'signal': 'STRONG_BUY',
            'price': 9500,
            'change': 2.5,
            'why': 'Breakout + volume spike 2.3x + foreign net buy 3 days',
            'entry': '9400-9500',
            'tp': '9800/10200',
            'sl': '9100',
            'rr': '1:2.5'
        },
        {
            'ticker': 'TLKM',
            'name': 'Telkom Indonesia Tbk',
            'score': 72.3,
            'signal': 'BUY',
            'price': 3850,
            'change': 1.8,
            'why': 'Uptrend + RSI bullish + ROE 18% undervalued',
            'entry': '3800-3850',
            'tp': '4000/4200',
            'sl': '3700',
            'rr': '1:2.0'
        },
        {
            'ticker': 'ASII',
            'name': 'Astra International Tbk',
            'score': 68.7,
            'signal': 'BUY',
            'price': 5200,
            'change': 1.2,
            'why': 'MACD crossover + accumulation pattern + PER 10x',
            'entry': '5150-5200',
            'tp': '5400/5600',
            'sl': '5050',
            'rr': '1:1.8'
        }
    ]
    
    # Build message
    message = f"""
🚨 *STOCK ALERTS* - {len(stocks)} Opportunities Found
📅 {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}

"""
    
    for i, stock in enumerate(stocks, 1):
        emoji = '🟢' if stock['score'] >= 75 else '🟡'
        message += f"""
━━━━━━━━━━━━━━━━━━━━

{i}. {emoji} *{stock['ticker']}* - {stock['name']}
   Score: *{stock['score']}/100* | Signal: *{stock['signal']}*
   Price: Rp {stock['price']:,} ({stock['change']:+.1f}%)

   📌 *Why:* {stock['why']}

   💡 *Trade Plan:*
   • Entry: {stock['entry']}
   • TP: {stock['tp']}
   • SL: {stock['sl']}
   • R/R: {stock['rr']}

"""
    
    message += f"""
━━━━━━━━━━━━━━━━━━━━

📊 *Summary:*
🟢 Strong Buy: {sum(1 for s in stocks if s['score'] >= 75)}
🟡 Buy: {sum(1 for s in stocks if 65 <= s['score'] < 75)}

⚠️ *DYOR - Do Your Own Research*
   Always use proper risk management (max 2-3% per trade)

📱 More info: http://76.13.19.250:8000/docs
"""
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    payload = {
        "chat_id": ADMIN_ID,
        "text": message.strip(),
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    
    print("="*80)
    print(f"SENDING {len(stocks)} STOCK ALERTS (Minimal Format)...")
    print("="*80)
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=15)
            result = response.json()
            
            if result.get('ok'):
                print(f"\n✅ SUCCESS!")
                print(f"   Sent {len(stocks)} stock alerts")
                print(f"   Message ID: {result.get('result', {}).get('message_id')}")
                print(f"   Length: {len(message)} characters")
                print("\n📱 Check Telegram!")
            else:
                print(f"\n❌ Failed: {result}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    
    print("="*80)

if __name__ == '__main__':
    asyncio.run(send_minimal_alerts())
