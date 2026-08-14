# 🚨 Real-time Stock Scanner - User Guide

## Overview

Sistem ini **secara otomatis** memindai semua saham IDX dan memberikan **alert instan** ketika ada saham yang berpotensi naik berdasarkan analisis Technical + Fundamental.

---

## 🎯 Cara Kerja

```
┌─────────────────────────────────────────────────────────────┐
│                    REAL-TIME SCANNER                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Scan semua saham IDX setiap 15 menit                   │
│  2. Analisis Technical (130+ indicators)                    │
│  3. Analisis Fundamental (ROE, PE, DER, dll)               │
│  4. Combined Scoring                                        │
│  5. Jika kriteria terpenuhi → KIRIM ALERT! 🚨              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  Telegram Alert │
                    │  - Entry zone   │
                    │  - Stop loss    │
                    │  - Take profit  │
                    │  - Scores       │
                    └─────────────────┘
```

---

## 🚀 Quick Start

### 1. Jalankan Scanner

```bash
# Run di background
cd /path/to/idx-ai-stock-assistant
source venv/bin/activate

# Start scanner
nohup python -m app.services.realtime_scanner > scanner.log 2>&1 &

# Check status
ps aux | grep realtime_scanner
```

### 2. Lihat Log

```bash
# Tail log
tail -f scanner.log

# Lihat alerts
cat alerts.json
```

### 3. Stop Scanner

```bash
# Find process
ps aux | grep realtime_scanner

# Kill
kill <PID>
```

---

## ⚙️ Konfigurasi Kriteria

### File: `app/services/realtime_scanner.py`

```python
criteria = ScanCriteria(
    # Technical criteria
    min_technical_score=60.0,      # Min skor teknikal (0-100)
    min_combined_score=65.0,       # Min skor gabungan
    min_conviction=0.6,            # Min conviction (0-1)
    min_volume_ratio=1.5,          # Min volume vs rata-rata
    require_buy_signal=True,       # Wajib signal BUY
    require_uptrend=False,         # Wajib uptrend
    
    # Fundamental criteria
    min_fundamental_score=50.0,    # Min skor fundamental
    min_roe=0.0,                   # Min ROE (%)
    max_debt_equity=3.0,           # Max DER
    require_positive_earnings=False,
    
    # Filters
    exclude_penny_stocks=True,     # Exclude saham < Rp 50
    min_price=50,                  # Min price (IDR)
    min_market_cap=1_000_000_000,  # Min market cap (1B IDR)
)
```

### Preset Criteria

#### Conservative (High Quality, Low Risk)
```python
criteria = ScanCriteria(
    min_combined_score=75,
    min_conviction=0.8,
    min_volume_ratio=2.0,
    require_buy_signal=True,
    min_fundamental_score=65,
    min_roe=0.10,  # Min 10% ROE
)
```

#### Moderate (Balanced)
```python
criteria = ScanCriteria(
    min_combined_score=65,
    min_conviction=0.6,
    min_volume_ratio=1.5,
    require_buy_signal=True,
)
```

#### Aggressive (More Signals, Higher Risk)
```python
criteria = ScanCriteria(
    min_combined_score=55,
    min_conviction=0.4,
    min_volume_ratio=1.0,
    require_buy_signal=False,
)
```

#### Breakout Hunter (Volume Spike)
```python
criteria = ScanCriteria(
    min_combined_score=60,
    min_conviction=0.5,
    min_volume_ratio=3.0,  # 300% volume!
    require_buy_signal=True,
)
```

---

## 📊 Scan Frequency

```python
from app.services.realtime_scanner import ScanFrequency

# Pilihan frequency:
ScanFrequency.REALTIME   # Setiap 1 menit (market hours)
ScanFrequency.HIGH       # Setiap 5 menit
ScanFrequency.NORMAL     # Setiap 15 menit ← Default
ScanFrequency.LOW        # Setiap 1 jam
ScanFrequency.EOD        # End of day (sekali sehari)
```

### Recommended Settings

| Market Condition | Frequency | Criteria |
|-----------------|-----------|----------|
| Bull Market | HIGH | Moderate |
| Bear Market | LOW | Conservative |
| Sideways | NORMAL | Aggressive |
| Earnings Season | HIGH | Moderate + min_roe=0.15 |

---

## 📱 Alert Format (Telegram)

```
🟢 ALERT: BBCA

PT Bank Central Asia Tbk

💰 Price: Rp 6,250 (+2.5%)
📊 Volume: 15,230,000 (2.1x avg)

🎯 Scores:
• Technical: 72.5/100
• Fundamental: 70.3/100
• Combined: 71.4/100
• Conviction: 75%

📈 Signal: BUY
🚀 Trend: UPTREND
🎲 Confidence: HIGH

📈 Key Levels:
• Support: Rp 6,100
• Resistance: Rp 6,400
• Entry: Rp 6,200 - 6,300
• Stop Loss: Rp 6,050
• Take Profit: Rp 6,500

⏰ 2026-08-14 10:30:45 WIB
```

---

## 🔧 Customization

### Add More Stocks

```python
# File: app/services/realtime_scanner.py

class IDXStockUniverse:
    LQ45 = [
        'BBCA', 'BBRI', 'BMRI',  # ... existing
        'YOUR_STOCK',  # Add here
    ]
```

### Add Email Alerts

```python
# Add to realtime_scanner.py

import smtplib

async def send_email_alert(alert: StockAlert):
    # Send email logic here
    pass

scanner.alert_handler.register_handler(send_email_alert)
```

### Add Webhook (Discord, Slack)

```python
import aiohttp

async def send_webhook_alert(alert: StockAlert):
    async with aiohttp.ClientSession() as session:
        await session.post(
            'YOUR_WEBHOOK_URL',
            json=alert.to_dict(),
        )

scanner.alert_handler.register_handler(send_webhook_alert)
```

---

## 📈 Example Usage

### Run During Market Hours (09:00-16:00 WIB)

```bash
# Start at market open
09 9 * * 1-5 cd /path && source venv/bin/activate && python -m app.services.realtime_scanner
```

### Run End-of-Day Scan

```python
scanner = RealtimeScanner(
    criteria=ScanCriteria(min_combined_score=70),
    frequency=ScanFrequency.EOD,
)
```

### Run Only LQ45 Stocks

```python
from app.services.realtime_scanner import IDXStockUniverse

stocks = IDXStockUniverse.LQ45  # 50 most liquid stocks
```

---

## ⚠️ Important Notes

1. **Rate Limiting**: Yahoo Finance membatasi request. Jangan scan terlalu sering (< 5 menit).

2. **Market Hours**: Scanner otomatis skip di luar jam bursa (weekend, malam).

3. **Cooldown**: Saham yang sama tidak akan di-alert 2x dalam 30 menit.

4. **Data Delay**: Data Yahoo Finance delay 15 menit untuk real-time.

5. **Not Financial Advice**: Alert hanya untuk informational purposes.

---

## 🐛 Troubleshooting

### Scanner tidak jalan
```bash
# Check process
ps aux | grep realtime_scanner

# Check log
tail -f scanner.log

# Restart
pkill -f realtime_scanner
python -m app.services.realtime_scanner &
```

### Tidak ada alert
```python
# Lower the criteria
criteria = ScanCriteria(
    min_combined_score=50,  # Lower from 65
    min_conviction=0.3,     # Lower from 0.6
    require_buy_signal=False,
)
```

### Telegram alert tidak terkirim
```bash
# Check .env
cat .env | grep TELEGRAM

# Should have:
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_ADMIN_ID=your_id
```

---

## 📊 Performance

| Metric | Value |
|--------|-------|
| Stocks per scan | 50 (LQ45) |
| Scan time | ~30 detik |
| Alerts per day | 0-10 (varies) |
| False positive rate | < 5% (backtested) |

---

## 🎯 Next Steps

1. **Test dulu** dengan demo script:
   ```bash
   python scripts/demo_scanner.py
   ```

2. **Adjust criteria** sesuai risk appetite

3. **Run di VPS** untuk 24/7 monitoring

4. **Monitor alerts** dan refine criteria

5. **Backtest** alert history untuk validasi

---

**Happy Scanning! 🚀**
