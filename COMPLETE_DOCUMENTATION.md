# 📊 IDX AI STOCK ASSISTANT - Complete Documentation

**Version:** 2.0.0  
**Last Updated:** 2026-08-20  
**Status:** Production Ready ✅

---

## 📑 **TABLE OF CONTENTS**

1. [Overview](#1-overview)
2. [System Architecture](#2-system-architecture)
3. [Features](#3-features)
4. [Installation & Deployment](#4-installation--deployment)
5. [Configuration](#5-configuration)
6. [Usage Guide](#6-usage-guide)
7. [API Reference](#7-api-reference)
8. [Telegram Bot](#8-telegram-bot)
9. [Scanner & Alerts](#9-scanner--alerts)
10. [Machine Learning](#10-machine-learning)
11. [Foreign Flow Analysis](#11-foreign-flow-analysis)
12. [Troubleshooting](#12-troubleshooting)
13. [FAQ](#13-faq)
14. [**Trading Lessons Learned**](#14-trading-lessons-learned) ⚠️ **WAJIB BACA**
15. [**IDX Stock Scanner**](#15-idx-stock-scanner) 🆕
16. [**Crypto Trading System**](#16-crypto-trading-system) 🆕

---

## 1. **OVERVIEW**

### 1.1 What is IDX AI Stock Assistant?

AI-powered stock analysis and alert system for Indonesia Stock Exchange (IDX). Combines technical analysis, fundamental analysis, machine learning, and foreign flow tracking to identify high-potential stocks.

### 1.2 Key Features

- ✅ **130+ Technical Indicators** (RSI, MACD, Bollinger Bands, etc.)
- ✅ **Fundamental Analysis** (PE, PBV, ROE, DER, Growth)
- ✅ **ML Ensemble** (XGBoost + LightGBM + 4 models)
- ✅ **Foreign Flow Tracking** (Bandar detection)
- ✅ **Real-time Scanner** (Auto-scan every hour)
- ✅ **Telegram Alerts** (Instant notifications)
- ✅ **AI Analysis** (Qwen3.5-397b + Groq fallback)
- ✅ **Backtesting Engine** (Performance metrics)
- ✅ **Walk-Forward Validation** (Strategy robustness)

### 1.3 System Stats

| Metric | Value |
|--------|-------|
| Stock Universe | 941 IDX stocks |
| Technical Indicators | 130+ |
| ML Models | 6 (Ensemble) |
| Scan Frequency | Every hour (market hours) |
| Alert Format | Telegram (minimal + multiple) |
| Database | PostgreSQL (27,850+ records) |
| AI Provider | Qwen3.5-397b → Groq → Gemini |

---

## 2. **SYSTEM ARCHITECTURE**

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    USER INTERACTION                      │
│         Telegram Bot / API / Web Dashboard              │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                   APPLICATION LAYER                      │
│  FastAPI Server | Background Scheduler | Alert Handler  │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                   ANALYSIS ENGINE                        │
│  Technical │ Fundamental │ ML │ Foreign Flow │ AI/LLM   │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                    DATA LAYER                            │
│   PostgreSQL │ Redis Cache │ Yahoo Finance API          │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Component Diagram

```
┌──────────────────────────────────────────────────────────┐
│  VPS: 76.13.19.250                                       │
│  /opt/idx-ai-stock-assistant                             │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  idx-ai-app  │  │  idx-ai-bot  │  │ idx-ai-redis │  │
│  │   (FastAPI)  │  │ (Scheduler)  │  │   (Cache)    │  │
│  │   Port:8000  │  │  Telegram    │  │  Port:6380   │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│                                                          │
│  ┌──────────────────┐  ┌──────────────────┐            │
│  │ idx-ai-postgres  │  │   External APIs  │            │
│  │    (Database)    │  │  • Yahoo Finance │            │
│  │    Port:5433     │  │  • Qwen AI       │            │
│  └──────────────────┘  │  • Groq          │            │
│                        │  • Gemini        │            │
│                        └──────────────────┘            │
└──────────────────────────────────────────────────────────┘
```

### 2.3 Data Flow

```
1. User Request (Telegram/API)
        ↓
2. API receives request
        ↓
3. Fetch data (Yahoo Finance / Cache)
        ↓
4. Run Analysis (Technical + Fundamental + ML)
        ↓
5. Generate Score & Signal
        ↓
6. Check Criteria (Score ≥ 70, Signal = BUY)
        ↓
7. If met → Send Telegram Alert
        ↓
8. Log to Database (stock_scores, analysis_history)
```

---

## 3. **FEATURES**

### 3.1 Technical Analysis (130+ Indicators)

**Trend Indicators:**
- SMA, EMA, WMA (various periods)
- MACD, ADX, Aroon
- Parabolic SAR, Supertrend

**Momentum Indicators:**
- RSI, Stochastic, Williams %R
- CCI, ROC, Momentum
- Awesome Oscillator

**Volatility Indicators:**
- Bollinger Bands, Keltner Channel
- ATR, Standard Deviation
- Donchian Channel

**Volume Indicators:**
- OBV, MFI, CMF
- Volume Profile, VWAP
- Accumulation/Distribution

**Candlestick Patterns:**
- Doji, Hammer, Engulfing
- Morning/Evening Star
- 20+ patterns detected

### 3.2 Fundamental Analysis

**Valuation Ratios:**
- PER (Price-to-Earnings)
- PBV (Price-to-Book Value)
- PEG (Price/Earnings-to-Growth)
- EV/EBITDA

**Profitability Metrics:**
- ROE (Return on Equity)
- ROA (Return on Assets)
- Gross Margin, Net Margin
- NIM (Net Interest Margin) - for banks

**Financial Health:**
- DER (Debt-to-Equity)
- Current Ratio, Quick Ratio
- CAR (Capital Adequacy Ratio) - for banks
- NPL (Non-Performing Loan) - for banks

**Growth Metrics:**
- Revenue Growth (YoY, QoQ)
- Earnings Growth (YoY, QoQ)
- Book Value Growth

### 3.3 Machine Learning Ensemble

**Models:**
1. **XGBoost** (Gradient Boosting)
2. **LightGBM** (Gradient Boosting)
3. **Random Forest** (Bagging)
4. **Gradient Boosting** (Boosting)
5. **Logistic Regression** (Linear)
6. **MLP Neural Network** (Deep Learning)

**Ensemble Method:**
- Stacking with meta-learner
- Soft voting fallback
- Feature importance analysis
- SHAP values for interpretability

**Performance:**
- Accuracy: 65-75% (expected)
- Training time: 2-5 minutes
- Prediction time: <1 second

### 3.4 Foreign Flow Analysis (Bandar Tracking)

**Metrics Tracked:**
- Foreign Net Buy/Sell
- Foreign Ownership %
- Accumulation/Distribution
- Block Trade Detection
- Consecutive Buy/Sell Days

**Bandar Score (0-100):**
- 80-100: Strong Accumulation 🟢
- 65-79: Accumulation 🟢
- 45-64: Neutral 🟡
- 30-44: Distribution 🔴
- 0-29: Strong Distribution 🔴

### 3.5 Real-time Scanner

**Scan Frequency:**
- Every hour during market hours
- 09:00 - 15:00 WIB (Mon-Fri)
- 7 scans per day

**Criteria (Default - Conservative):**
```python
min_combined_score: 75.0
min_conviction: 0.8
min_volume_ratio: 2.0
require_buy_signal: True
require_uptrend: True
liquidity_filter: >= 1B IDR/day
```

**Alert Cooldown:**
- 24 hours per stock
- Prevents spam
- Configurable

### 3.6 Telegram Alerts

**Alert Types:**
- 🟢 STRONG BUY (Score ≥ 80)
- 🟢 BUY (Score 70-79)
- 🟡 WATCH (Score 60-69)
- 🔴 SELL (Score < 40)

**Alert Format (Minimal):**
```
🟢 BBCA - Bank Central Asia Tbk
   Score: 78.5/100 | Signal: STRONG_BUY
   Price: Rp 9,500 (+2.5%)

   📌 Why: Technical + volume + uptrend

   💡 Trade Plan:
   • Entry: 9400-9500
   • TP: 9800 | SL: 9100 | R/R: 1:2.5
```

**Features:**
- Multiple stocks per message
- WHY reasoning (1 line)
- Complete trade plan
- Summary at bottom

---

## 4. **INSTALLATION & DEPLOYMENT**

### 4.1 Prerequisites

**VPS Requirements:**
- OS: Ubuntu 20.04+ or Debian 11+
- RAM: 4GB minimum (8GB recommended)
- Storage: 20GB minimum
- Docker & Docker Compose

**External Services:**
- Telegram Bot Token (from @BotFather)
- (Optional) AI API keys (Qwen, Groq, Gemini)

### 4.2 Quick Deploy

**Step 1: Clone Repository**
```bash
cd /opt
git clone <your-repo-url> idx-ai-stock-assistant
cd idx-ai-stock-assistant
```

**Step 2: Configure Environment**
```bash
cp .env.example .env
nano .env

# Edit these values:
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_ADMIN_ID=your_admin_id
```

**Step 3: Start Services**
```bash
docker compose up -d --build
```

**Step 4: Run Migrations**
```bash
docker compose exec app alembic upgrade head
```

**Step 5: Seed Tickers**
```bash
docker compose exec app python scripts/seed_tickers.py
```

**Step 6: Verify**
```bash
docker compose ps
curl http://localhost:8000/api/v1/health
```

### 4.3 Production Deployment (VPS)

**Automated Deploy Script:**
```bash
./scripts/deploy_to_vps.sh
```

**Manual Deploy:**
```bash
# 1. SSH to VPS
ssh root@76.13.19.250

# 2. Navigate to app
cd /opt/idx-ai-stock-assistant

# 3. Pull latest code
git pull origin main

# 4. Install dependencies
source venv/bin/activate
pip install -r requirements.txt

# 5. Restart services
docker compose down
docker compose up -d --build

# 6. Check logs
docker compose logs -f
```

### 4.4 ML Dependencies

**Install ML packages:**
```bash
pip install xgboost>=2.0.0 lightgbm>=4.0.0 shap>=0.43.0
```

**Or update requirements.txt:**
```bash
# Add to requirements.txt:
xgboost>=2.0.0
lightgbm>=4.0.0
shap>=0.43.0

# Then install:
pip install -r requirements.txt
```

---

## 5. **CONFIGURATION**

### 5.1 Environment Variables (.env)

```bash
# === Application ===
APP_NAME=IDX AI Stock Assistant
APP_ENV=production
DEBUG=false
LOG_LEVEL=INFO

# === Database ===
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=idx_ai
POSTGRES_USER=idx_ai_user
POSTGRES_PASSWORD=change_me_in_production
DATABASE_URL=postgresql+asyncpg://idx_ai_user:password@postgres:5432/idx_ai

# === Redis ===
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# === Telegram ===
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN_HERE
TELEGRAM_ADMIN_ID=YOUR_TELEGRAM_ADMIN_ID_HERE
TELEGRAM_USE_WEBHOOK=false

# === AI / LLM ===
LLM_PROVIDER=qwen
QWEN_API_KEY=your_qwen_key
QWEN_MODEL=qwen3.5-397b
QWEN_BASE_URL=http://localhost:8000/v1

GROQ_API_KEY=your_groq_key
GROQ_MODEL=llama-3.3-70b-versatile

GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-2.0-flash

# === Scanner ===
SCAN_FREQUENCY=normal
DEFAULT_MIN_SCORE=75.0
DEFAULT_MIN_CONVICTION=0.8
```

### 5.2 Scanner Criteria

**Edit in `app/services/realtime_scanner.py`:**

```python
@dataclass
class ScanCriteria:
    min_combined_score: float = 75.0    # Lower for more alerts
    min_conviction: float = 0.8          # Lower for more alerts
    min_volume_ratio: float = 2.0        # Lower for more alerts
    require_buy_signal: bool = True      # Set False for any signal
    require_uptrend: bool = True         # Set False for sideways
    min_technical_score: float = 70.0    # Lower for more alerts
    min_fundamental_score: float = 50.0  # Lower for more alerts
```

### 5.3 Scheduler Configuration

**Edit in `app/scheduler/jobs.py`:**

```python
# Intraday scanner schedule
scheduler.add_job(
    intraday_scanner_job,
    CronTrigger(
        day_of_week="mon-fri",
        hour="9-15",    # 09:00 - 15:00
        minute="0",     # Top of every hour
        timezone="Asia/Jakarta",
    ),
)
```

---

## 6. **USAGE GUIDE**

### 6.1 Telegram Bot Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/start` | Start bot | `/start` |
| `/help` | Show help | `/help` |
| `/stock <ticker>` | Get stock price | `/stock BBCA` |
| `/analyze <ticker>` | AI analysis | `/analyze BBCA` |
| `/scan` | Run manual scan | `/scan` |
| `/status` | System status | `/status` |
| `/portfolio` | Track portfolio | `/portfolio` |

### 6.2 API Endpoints

**Base URL:** `http://76.13.19.250:8000`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/health` | GET | System health check |
| `/api/v1/stocks` | GET | List all stocks |
| `/api/v1/stocks/{ticker}` | GET | Get stock details |
| `/api/v1/stocks/{ticker}/quote` | GET | Real-time quote |
| `/api/v1/stocks/{ticker}/analysis` | GET | Full analysis |
| `/api/v1/scan` | POST | Run scanner |
| `/api/v1/alerts` | GET | Get alert history |

**Examples:**
```bash
# Health check
curl http://76.13.19.250:8000/api/v1/health

# Get stock analysis
curl http://76.13.19.250:8000/api/v1/stocks/BBCA/analysis

# Run scanner
curl -X POST http://76.13.19.250:8000/api/v1/scan \
  -H "Content-Type: application/json" \
  -d '{"min_score": 65}'
```

### 6.3 Manual Scan

**Via Script:**
```bash
ssh root@76.13.19.250
docker exec idx-ai-app python scripts/quick_scan.py
```

**Via API:**
```bash
curl -X POST http://76.13.19.250:8000/api/v1/scan
```

**Via Python:**
```python
from app.services.realtime_scanner import RealtimeScanner
import asyncio

async def scan():
    scanner = RealtimeScanner()
    await scanner.scan_all_stocks()

asyncio.run(scan())
```

### 6.4 Backtesting

**Run Backtest:**
```bash
docker exec idx-ai-app python scripts/demo_backtester.py
```

**Python Example:**
```python
from app.services.backtester import Backtester

backtester = Backtester(
    initial_capital=100_000_000,
    commission=0.0025,
    slippage=0.001,
)

results = backtester.run(
    ticker='BBCA',
    start_date='2024-01-01',
    end_date='2024-12-31',
    strategy='momentum',
)

print(f"Total Return: {results.total_return:.2%}")
print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
print(f"Max Drawdown: {results.max_drawdown:.2%}")
```

---

## 7. **API REFERENCE**

### 7.1 Health Check

**GET** `/api/v1/health`

**Response:**
```json
{
  "status": "healthy",
  "service": "IDX AI Stock Assistant",
  "version": "1.0.0",
  "components": {
    "database": "connected",
    "redis": "connected",
    "llm": "available"
  }
}
```

### 7.2 Get Stock Analysis

**GET** `/api/v1/stocks/{ticker}/analysis`

**Parameters:**
- `ticker` (path): Stock ticker (e.g., BBCA)

**Response:**
```json
{
  "ticker": "BBCA",
  "company_name": "Bank Central Asia Tbk",
  "price": 9500,
  "change_pct": 2.5,
  "technical_score": 82.3,
  "fundamental_score": 74.2,
  "combined_score": 78.5,
  "signal": "BUY",
  "trend": "UPTREND",
  "conviction": 0.82,
  "entry_zone": {"low": 9400, "high": 9500},
  "take_profit": 9800,
  "stop_loss": 9100,
  "risk_reward_ratio": 2.3
}
```

### 7.3 Run Scanner

**POST** `/api/v1/scan`

**Request Body:**
```json
{
  "min_score": 65,
  "min_conviction": 0.6,
  "tickers": ["BBCA", "BBRI", "TLKM"]
}
```

**Response:**
```json
{
  "scan_id": "abc123",
  "timestamp": "2026-08-14T15:40:00",
  "stocks_scanned": 32,
  "alerts_found": 3,
  "alerts": [
    {
      "ticker": "BBCA",
      "score": 78.5,
      "signal": "BUY"
    }
  ]
}
```

---

## 8. **TELEGRAM BOT**

### 8.1 Setup

**Create Bot:**
1. Open Telegram, search `@BotFather`
2. Send `/newbot`
3. Follow instructions
4. Copy bot token

**Get Admin ID:**
1. Search `@userinfobot`
2. Send any message
3. Copy your user ID

**Update .env:**
```bash
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_ADMIN_ID=your_user_id_here
```

### 8.2 Alert Format

**Single Alert:**
```
🟢 BBCA - Bank Central Asia Tbk
   Score: 78.5/100 | Signal: STRONG_BUY
   Price: Rp 9,500 (+2.5%)

   📌 Why: Technical + volume + uptrend

   💡 Trade Plan:
   • Entry: 9400-9500
   • TP: 9800 | SL: 9100 | R/R: 1:2.5

⏰ 2026-08-14 15:40
```

**Multiple Alerts:**
```
🚨 STOCK ALERTS - 3 Opportunities Found
📅 2026-08-14 15:40

━━━━━━━━━━━━━━━━━━━━

1. 🟢 BBCA - Score: 78.5/100
   📌 Why: Technical + volume
   💡 Entry/TP/SL/R/R

━━━━━━━━━━━━━━━━━━━━

2. 🟡 TLKM - Score: 72.3/100
   📌 Why: Uptrend + RSI
   💡 Entry/TP/SL/R/R

━━━━━━━━━━━━━━━━━━━━

📊 Summary:
🟢 Strong Buy: 1
🟡 Buy: 2
```

---

## 9. **SCANNER & ALERTS**

### 9.1 How Scanner Works

```
1. Fetch all active stocks (941 tickers)
        ↓
2. Download price history (60 days)
        ↓
3. Calculate technical indicators
        ↓
4. Fetch fundamental data
        ↓
5. Run ML prediction (if available)
        ↓
6. Calculate combined score
        ↓
7. Check criteria:
   • Score >= 75?
   • Conviction >= 0.8?
   • Volume ratio >= 2.0?
   • Signal = BUY?
   • Trend = UPTREND?
   • Liquidity >= 1B IDR?
   • Not in cooldown (24h)?
        ↓
8. If ALL pass → Send Telegram Alert
        ↓
9. Log to database
```

### 9.2 Alert Criteria

**Default (Conservative):**
```python
{
    "min_combined_score": 75.0,
    "min_conviction": 0.8,
    "min_volume_ratio": 2.0,
    "require_buy_signal": True,
    "require_uptrend": True,
    "min_technical_score": 70.0,
    "min_fundamental_score": 50.0,
    "min_liquidity_idr": 1_000_000_000
}
```

**Moderate (More Alerts):**
```python
{
    "min_combined_score": 65.0,  # Lowered
    "min_conviction": 0.6,        # Lowered
    "min_volume_ratio": 1.5,      # Lowered
    "require_buy_signal": False,  # Any signal
    "require_uptrend": False,     # Allow sideways
}
```

### 9.3 Alert Cooldown

**Prevents spam:**
- 24 hours per stock
- Stored in Redis
- Auto-expires

**Key format:**
```
alert_cooldown:BBCA = "sent" (expires in 86400s)
```

---

## 10. **MACHINE LEARNING**

### 10.1 ML Ensemble

**Models:**
1. XGBoost (200 estimators, depth 6)
2. LightGBM (200 estimators, depth 6)
3. Random Forest (200 trees, depth 10)
4. Gradient Boosting (100 estimators)
5. Logistic Regression (L2 regularization)
6. MLP Neural Network (128-64-32 layers)

**Ensemble:**
- Stacking with Logistic Regression meta-learner
- Soft voting fallback
- 5-fold cross-validation

### 10.2 Feature Columns (23 features)

```python
FEATURE_COLUMNS = [
    # Technical (15)
    'rsi_14', 'macd_histogram', 'ma_distance_pct', 'volume_ratio',
    'atr_pct', 'price_momentum_5d', 'bb_position', 'adx',
    'stoch_k', 'willr_14', 'cci_20', 'roc_10',
    'obv_change', 'mfi_14', 'cmf_20',
    
    # Fundamental (8)
    'revenue_growth_yoy', 'earnings_growth_yoy', 'roe', 'roa',
    'debt_to_equity', 'current_ratio', 'pe_ratio', 'pb_ratio',
]
```

### 10.3 Training ML Model

**Train:**
```bash
docker exec idx-ai-app python scripts/train_ml_ensemble.py
```

**Python:**
```python
from app.services.ml_ensemble import MLEnsemble

ensemble = MLEnsemble()

# Train
metrics = ensemble.train(X_train, y_train, X_test, y_test)

# Save
ensemble.save()

# Load
ensemble.load()

# Predict
prediction = ensemble.predict(X_test)
```

### 10.4 Performance Metrics

**Expected:**
- Accuracy: 65-75%
- Precision: 60-70%
- Recall: 60-70%
- F1 Score: 0.60-0.70
- ROC AUC: 0.65-0.75

---

## 11. **FOREIGN FLOW ANALYSIS**

### 11.1 Bandar Score Calculation

**Components (0-25 points each):**

1. **Flow Ratio** (Buy/Sell)
   - ≥3.0x → 25 pts
   - ≥2.0x → 20 pts
   - ≥1.5x → 15 pts

2. **Consecutive Days**
   - ≥5 days buy → 25 pts
   - ≥3 days buy → 20 pts

3. **Trend Consistency**
   - Net buy 5d, 10d, 20d all positive → 25 pts

4. **Flow Percentage**
   - ≥10% of volume → 25 pts
   - ≥5% of volume → 20 pts

**Total:** 0-100 points

### 11.2 Signal Mapping

| Score | Signal | Meaning |
|-------|--------|---------|
| 80-100 | STRONG_ACCUMULATION | Heavy foreign buying |
| 65-79 | ACCUMULATION | Moderate buying |
| 45-64 | NEUTRAL | Balanced |
| 30-44 | DISTRIBUTION | Moderate selling |
| 0-29 | STRONG_DISTRIBUTION | Heavy selling |

### 11.3 Usage

```python
from app.services.foreign_flow import ForeignFlowAnalyzer

analyzer = ForeignFlowAnalyzer()
flow = analyzer.analyze('BBCA')

print(f"Bandar Score: {flow.bandar_score}")
print(f"Signal: {flow.bandar_signal}")
print(f"Foreign Buy: {flow.foreign_buy:,}")
print(f"Foreign Sell: {flow.foreign_sell:,}")
```

---

## 12. **TROUBLESHOOTING**

### 12.1 Common Issues

**Problem:** Scanner not running
```bash
# Check scheduler
docker logs idx-ai-bot 2>&1 | grep "scheduler"

# Restart bot
docker compose restart bot
```

**Problem:** No alerts sent
```bash
# Check Telegram config
docker exec idx-ai-app cat .env | grep TELEGRAM

# Test connection
python scripts/test_telegram_alert.py

# Check cooldown
docker exec idx-ai-redis redis-cli keys "alert_cooldown:*"
```

**Problem:** Database connection error
```bash
# Check DB status
docker compose ps postgres

# Restart DB
docker compose restart postgres

# Run migrations
docker compose exec app alembic upgrade head
```

**Problem:** ML import error
```bash
# Install dependencies
pip install xgboost lightgbm shap

# Or rebuild
docker compose build --no-cache
docker compose up -d
```

### 12.2 Performance Issues

**Slow scans:**
- Reduce stock universe
- Increase batch size
- Add more RAM

**High memory usage:**
- Reduce cache TTL
- Limit history size
- Restart containers weekly

**API rate limits:**
- Add delays between requests
- Use caching
- Reduce scan frequency

### 12.3 Log Commands

```bash
# App logs
docker logs idx-ai-app --tail=100 -f

# Bot logs
docker logs idx-ai-bot --tail=100 -f

# Database logs
docker logs idx-ai-postgres --tail=100

# All logs
docker compose logs -f
```

---

## 13. **FAQ**

### Q: How accurate is the system?
**A:** Expected accuracy 65-75% based on backtesting. Real-world performance varies by market conditions.

### Q: How often will I get alerts?
**A:** Conservative criteria: 0-5 alerts/week. Moderate: 5-15 alerts/week. Depends on market conditions.

### Q: Can I use this for live trading?
**A:** Yes, but always use proper risk management. Start with paper trading or small positions (1-2% per trade).

### Q: Does it work for all IDX stocks?
**A:** Yes, covers all 941 active stocks. Liquidity filter ensures only tradeable stocks are alerted.

### Q: How do I adjust criteria?
**A:** Edit `app/services/realtime_scanner.py` and modify `ScanCriteria` dataclass.

### Q: Can I add custom indicators?
**A:** Yes, add to `app/services/enhanced_technicals.py` and include in feature columns.

### Q: Is historical data stored?
**A:** Scores are stored (27,850+ records). Price data is fetched on-demand from Yahoo Finance.

### Q: Can I run multiple instances?
**A:** Yes, but use different Redis DBs to avoid cooldown conflicts.

### Q: What if Yahoo Finance is down?
**A:** Scanner will skip that run. System has retry logic and will continue on next scheduled scan.

### Q: How do I backup data?
```bash
# Backup database
docker exec idx-ai-postgres pg_dump -U idx_ai_user idx_ai > backup.sql

# Restore
docker exec -i idx-ai-postgres psql -U idx_ai_user idx_ai < backup.sql
```

---

## 📞 **SUPPORT**

**Documentation Files:**
- `README.md` - Quick start guide
- `DEPLOYMENT_COMPLETE.md` - Deployment summary
- `ML_FEATURES_GUIDE.md` - ML features documentation
- `SCANNER_GUIDE.md` - Scanner usage guide
- `TELEGRAM_ALERT_EXAMPLE.md` - Alert format examples
- `LESSONS_LEARNED.md` ⚠️ **WAJIB BACA - Pelajaran trading untuk hindari kerugian**

**Quick Commands:**
```bash
# Check status
ssh root@76.13.19.250 "docker compose ps"

# View logs
ssh root@76.13.19.250 "docker compose logs -f"

# Run scan
ssh root@76.13.19.250 "docker exec idx-ai-app python quick_scan.py"
```

---

## 14. **TRADING LESSONS LEARNED** ⚠️ **WAJIB BACA SEBELUM UBAH KODE**

### 14.1 Critical Bugs Found & Fixed (2026-08-20)

| Bug | Dampak | Fix |
|-----|--------|-----|
| **Market sell slippage 3.6%** | Profit 4% jadi 0.05% | Limit order untuk TP exit |
| **PnL calculation salah** | PnL tidak akurat | Proportional cost basis |
| **R:R ratio selalu rendah** | Tidak ada BUY signal | ATR-based targets |
| **Telegram format `:.2f`** | Profit tampil 0.00 | 4 decimal + persentase |
| **Tidak ada volume filter** | Masuk pair tipis | Min 500K USDT 24h |
| **TP1 terlalu dekat entry** | Profit tidak cover fee | Min 2% di atas entry |

### 14.2 Masalah Utama: Market Order Slippage

```
POL_USDT (Real Case):
  Entry:     0.08188
  TP2 Level: 0.0852 (+4.06% dari entry)
  Market Sell Fill: 0.08214 (bukan 0.0852!)
  Actual Profit: +0.05% (bukan +4%)
  Slippage: 3.6%
```

**Penyebab:** Tokocrypto order book tipis untuk pair kecil. Price spike ke TP level tapi market order fill di harga jauh lebih rendah.

**Solusi:**
```python
# JANGAN: Market order (bisa slippage)
resp = await self.client.market_sell(symbol, qty)

# PAKAI: Limit order di TP level
limit_price = tp_level * 0.998  # 0.2% below TP
resp = await self.client.limit_sell(symbol, qty, limit_price)
```

### 14.3 R:R Ratio Calculation Mistake

```python
# JANGAN: Raw S/R (selalu rendah jika dekat resistance)
upside = resistance - current_price  # bisa sangat kecil
downside = current_price - support  # bisa sangat besar
rr_ratio = upside / downside  # hasilnya 0.02-0.56

# PAKAI: ATR-based (lebih realistis)
rr_sr = (resistance - current_price) / (current_price - support)
if rr_sr < 1.0:
    upside = atr * 2    # 2xATR sebagai target
    downside = atr       # 1xATR sebagai risk
```

### 14.4 PnL Calculation Mistake

```python
# JANGAN: Full invested amount
pnl = sell_value - pos.invested  # Salah jika qty sell < qty beli

# PAKAI: Proportional cost basis
cost_basis = (qty_sell / qty_bought) * pos.invested
pnl = sell_value - cost_basis
```

### 14.5 Checklist Sebelum Deploy

- [ ] PnL calculation sudah pakai proportional cost basis?
- [ ] TP exit sudah pakai limit order?
- [ ] Volume filter sudah aktif (min 500K USDT)?
- [ ] R:R ratio sudah pakai ATR-based fallback?
- [ ] TP1 minimum 2% di atas entry?
- [ ] Slippage guard sudah aktif?
- [ ] Telegram notification format sudah benar?
- [ ] Tidak ada debug print yang tertinggal?
- [ ] Database migration sudah dijalankan?
- [ ] Semua test passing?

### 14.6 File Penting yang Sering Diubah

| File | Fungsi | Yang Perlu Diperhatikan |
|------|--------|------------------------|
| `app/services/crypto_real.py` | Real trading engine | PnL calc, limit orders, slippage guard |
| `app/services/analysis_engine.py` | IDX stock analysis | R:R calculation, thresholds |
| `app/services/crypto_levels.py` | TP/SL levels | ATR multipliers, min TP% |
| `app/scheduler/jobs.py` | Scheduled jobs | Scanner thresholds, cooldowns |
| `app/data/tokocrypto_trade_client.py` | Exchange API | Limit orders, rate limiting |

---

## 15. **IDX STOCK SCANNER** 🆕

### 15.1 How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                    IDX STOCK SCANNER                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Scan 941 saham IDX setiap jam (market hours)           │
│  2. Filter: Volume ≥ 1.2x avg, 24h change > -5%           │
│  3. Analisis Technical (scoring system)                     │
│  4. R:R calculation (ATR-based)                            │
│  5. Jika score ≥ 55 & signal = BUY → Alert!                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 15.2 Scoring System

| Component | Weight | Description |
|-----------|--------|-------------|
| Trend | 35% | MA alignment, price above SMA50 |
| Momentum | 20% | RSI, MACD, Stochastic |
| Volume | 25% | Relative volume, volume trend |
| Breakout | 20% | Higher highs/lows, resistance proximity |

### 15.3 Entry Criteria (Real Trading)

```python
crypto_real_entry_score = 75        # Minimum score
crypto_real_entry_require_uptrend = True
crypto_real_entry_pullback_max_pct = 8.0
crypto_real_entry_min_risk_reward = 1.5
crypto_real_entry_max_atr_pct = 5.0
```

### 15.4 Telegram Commands

- `/stocks` - Top scored stocks dari scan
- `/stocks scan` - Trigger scan manual
- `/stocks watchlist` - Daftar saham dipantau

### 15.5 Scanner Thresholds

| Parameter | Value | Description |
|-----------|-------|-------------|
| Score threshold | 55 | Minimum score untuk BUY signal |
| R:R minimum | 1.5 | Risk/reward ratio |
| Liquidity filter | 500M IDR | Minimum daily value |
| Alert cooldown | 4 hours | Antara alert yang sama |

---

## 16. **CRYPTO TRADING SYSTEM** 🆕

### 16.1 Configuration

```env
# Real Trading
CRYPTO_REAL_TRADING_ENABLED=true
CRYPTO_REAL_ENTRY_SCORE=75
CRYPTO_REAL_ALLOCATION_PERCENT=10
CRYPTO_REAL_MAX_POSITIONS=3

# Paper Trading
CRYPTO_PAPER_TRADING_ENABLED=false

# TP/SL Settings
CRYPTO_TP1_ATR_MULT=2.5
CRYPTO_TP2_ATR_MULT=4.0
CRYPTO_SL_ATR_MULT=2.0
```

### 16.2 Trading Flow

```
1. Scanner picks candidates (score ≥ 75)
2. Entry gate checks:
   - Volume ≥ 1.2x average
   - 24h change > -5%
   - Uptrend confirmed (EMA20 > SMA50)
   - R:R ≥ 1.5
   - ATR < 5% (not too volatile)
   - AI verdict = STRONG_WATCH
   - 24h volume ≥ 500K USDT
3. Execute BUY (market order)
4. Set TP1 (2.5x ATR) and TP2 (4x ATR)
5. Set SL (2x ATR below entry)
6. Monitor with trailing stop
7. Exit via:
   - TP1/TP2 (limit order at TP level)
   - Trailing stop (1.2x ATR or 2% of entry)
   - SL (2x ATR below entry)
```

### 16.3 Exit Logic

```python
# Priority order:
1. Stop Loss (including trailing)
2. Take Profit 2 (limit order)
3. Take Profit 1 (limit order)

# Slippage Guard:
if price dropped > 1% from TP level:
    skip sell (wait for recovery or SL)

# Trailing Stop:
trailing_distance = max(atr * 1.2, entry_price * 0.02)
trailing_stop = highest_price - trailing_distance
effective_sl = max(original_sl, trailing_stop)
```

### 16.4 Position Management

| Setting | Value | Description |
|---------|-------|-------------|
| Max positions | 3 | Concurrent open positions |
| Allocation | 10% | Per position of balance |
| Min order | 5 USDT | Tokocrypto minimum |
| SL cooldown | 3 hours | After SL exit |
| TP check | 5 seconds | Quick check interval |

### 16.5 Dashboard

- URL: `http://76.13.19.250:8000/crypto-dashboard`
- API: `http://76.13.19.250:8000/api/v1/crypto/dashboard/positions`
- Shows: Open positions, PnL, trade history

---

**Documentation Version:** 2.0.0  
**Last Updated:** 2026-08-20  
**Status:** Production Ready ✅

**IDX AI Stock Assistant - AI-powered Indonesian stock analysis** 🚀
