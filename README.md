# 🤖 IDX AI Stock Assistant

AI-powered Indonesian stock market analysis assistant. Provides data-driven insights and analysis for IDX (Bursa Efek Indonesia) stocks via Telegram.

## ⚠️ Disclaimer

**This system is NOT financial advice.** It provides educational analysis and data-driven insights. Always conduct your own research before making investment decisions.

---

## 🏗️ Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Telegram    │────▶│  FastAPI      │────▶│  AI Engine   │
│  Bot         │     │  Server       │     │  (Gemini)    │
└──────────────┘     └──────────────┘     └──────────────┘
                           │
                     ┌─────┴─────┐
                     │           │
              ┌──────▼──┐  ┌────▼────┐
              │PostgreSQL│  │  Redis  │
              │  (Data)  │  │ (Cache) │
              └─────────┘  └─────────┘
```

## ✨ Features

- 📊 **Stock Lookup** — Real-time IDX stock prices via `/stock BBCA`
- 🔍 **AI Analysis** — Full technical analysis via `/analyze BBCA`
- 🎯 **Advanced Scoring Engine** — Deterministic weighted scoring (MA, RSI, MACD, Volume, Breakout)
- 📰 **Smart News Search** — Local & International news (Tech, Economy, etc.) with trending topic detection
- 🧠 **Conversation Memory** — Remembers context across messages for natural chat (powered by Redis)
- 📈 **Technical Indicators** — RSI, MACD, SMA, ATR, Bollinger Bands, Support/Resistance
- 💬 **Natural Language** — Ask questions in Indonesian or English
- ⚡ **Redis Caching** — Fast responses with multi-layer caching
- 🔒 **Robust Deployment** — Bypasses yfinance 429 errors with modern history fetching

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- Google AI Studio API Key (from [aistudio.google.com](https://aistudio.google.com/))
- DeepSeek API Key (Optional fallback)
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))

### 1. Clone & Configure

```bash
git clone <your-repo-url>
cd idx-ai-stock-assistant

# Copy and edit environment file
cp .env.example .env
nano .env
```

**Required `.env` values:**
```
TELEGRAM_BOT_TOKEN=your_token_here
GEMINI_API_KEY=your_key_here
```

### 2. Run with Docker

```bash
# Start all services
docker-compose up -d

# Check logs
docker-compose logs -f app
docker-compose logs -f bot

# Run database migrations
docker-compose exec app alembic upgrade head

# Seed stock tickers
docker-compose exec app python scripts/seed_tickers.py
```

### 3. Test the Bot

Open Telegram and search for your bot. Send:
- `/start` — Welcome message
- `/stock BBCA` — Check BCA stock
- `/analyze TLKM` — Full AI analysis of Telkom

---

## 📁 Project Structure

```
idx-ai-stock-assistant/
├── app/
│   ├── main.py              # FastAPI entry
│   ├── config.py             # Settings from env
│   ├── api/endpoints/        # REST endpoints
│   ├── ai/                   # LLM client & prompts
│   ├── bot/handlers/         # Telegram handlers
│   ├── data/                 # Data ingestion (yfinance)
│   ├── models/               # SQLAlchemy models
│   ├── schemas/              # Pydantic schemas
│   ├── services/             # Business logic
│   └── scheduler/            # Background jobs
├── alembic/                  # DB migrations
├── scripts/                  # Utility scripts
├── tests/                    # Test suite
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

**Crypto scanner files:**
```
app/data/tokocrypto_client.py       # Tokocrypto public API adapter (no auth)
app/services/crypto_indicators.py   # deterministic technical indicators
app/services/crypto_scoring.py      # momentum score 0-100 + breakdown
app/services/crypto_ai.py           # AI verdict layer (failover-safe)
app/services/crypto_alert.py        # Telegram alerts + anti-spam cooldown
app/services/crypto_scanner.py      # scan orchestrator pipeline
app/models/crypto.py                # DB models (crypto_scans, crypto_alerts)
app/api/endpoints/crypto.py         # scanner API endpoints
scripts/crypto_scan.py              # manual scan trigger
alembic/versions/2c9f1a3b5d7e_*.py  # migration (crypto tables)
```

## 🔧 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/health` | Health check |
| GET | `/api/v1/stocks/{ticker}` | Full stock data |
| GET | `/api/v1/stocks/{ticker}/quote` | Quick quote |
| GET | `/api/v1/stocks/{ticker}/technicals` | Technical indicators |
| GET | `/api/v1/analysis/{ticker}` | AI analysis |
| POST | `/api/v1/analysis/{ticker}` | AI analysis with question |
| GET | `/api/v1/analysis/{ticker}/quick` | Quick lookup |
| GET | `/api/v1/crypto/scanner/status` | Crypto scanner runtime status |
| GET | `/api/v1/crypto/scanner/latest` | Latest scored candidates |
| GET | `/api/v1/crypto/scanner/config` | Scanner configuration |
| GET | `/api/v1/crypto/alerts` | Recent sent crypto alerts |
| GET | `/api/v1/crypto/cooldowns` | Currently cooling-down pairs |

## 🪙 Crypto Scanner (Tokocrypto)

A momentum scanner for Tokocrypto pairs — **market data + analysis only, no trading**.

It fetches **public** Tokocrypto data (no API key/secret required), computes deterministic
technical indicators, scores every pair 0–100 with a transparent breakdown, asks the AI for
a verdict on the top candidates, and sends Telegram alerts with anti-spam.

### Pipeline

```
symbols ──▶ filter (quote asset, liquidity, stablecoin) ──▶ 24h tickers
     ──▶ klines 5m/15m/1h ──▶ deterministic indicators ──▶ momentum score 0-100
     ──▶ AI verdict (STRONG_WATCH/WATCH/NEUTRAL/AVOID) ──▶ anti-spam cooldown
     ──▶ Telegram alert ──▶ persist history (crypto_scans, crypto_alerts)
```

* **Indicators**: EMA9/20/50, RSI(14, Wilder), MACD, ATR%, relative volume, distance from high.
* **Scoring**: weighted trend + momentum + volume + breakout, minus risk penalty
  (overbought RSI, pump >15/25%, extended from EMA50, high ATR, thin volume).
* **Multi-timeframe**: 5m (momentum) + 15m (confirmation) + 1h (trend).
* **AI is not a single point of failure**: if the LLM fails, a deterministic fallback
  verdict (score-derived) is used so the scanner keeps running.
* **Anti-spam**: Redis cooldown (`crypto:alert:<symbol>`); a pair is re-alerted only after
  the cooldown expires, its score improves by ≥10 pts, or a new breakout appears.
* **Dry-run**: `CRYPTO_SCANNER_DRY_RUN=true` logs alerts without sending and skips the AI.

### Run manually

```bash
python scripts/crypto_scan.py             # one full scan (sends real alerts)
python scripts/crypto_scan.py --dry-run   # simulate, log only
python scripts/crypto_scan.py --top 10    # show top 10 candidates after scan
```

### Database

```bash
alembic upgrade head
```

### Configuration (see `.env.example`)

| Variable | Default | Description |
|----------|---------|-------------|
| `CRYPTO_SCANNER_ENABLED` | `true` | Enable the scheduler job |
| `CRYPTO_SCAN_INTERVAL_MINUTES` | `5` | Scan interval |
| `CRYPTO_SCANNER_DRY_RUN` | `false` | Simulate alerts (no Telegram, no AI) |
| `CRYPTO_QUOTE_ASSETS` | `USDT,IDR` | Quote assets to scan |
| `CRYPTO_MIN_QUOTE_VOLUME` | *(empty)* | Min 24h quote volume (default ~1M) |
| `CRYPTO_MIN_SCORE_ALERT` | `75` | Minimum score to be a candidate |
| `CRYPTO_MAX_CANDIDATES_AI` | `10` | Top N candidates sent to the AI |
| `CRYPTO_MAX_ALERTS_PER_SCAN` | `3` | Max alerts per scan cycle |
| `CRYPTO_ALERT_COOLDOWN_MINUTES` | `60` | Anti-spam cooldown |
| `TELEGRAM_CHAT_ID` | *(admin)* | Alert delivery target |

**Important**: only public market-data endpoints are used, so the Tokocrypto API
key/secret are **not** needed and must not be added to the codebase.

## 📝 Paper Trading (Simulasi)

Simulates a virtual spot account driven by the crypto scanner. **No real orders are
ever placed** — this is a simulator for backtesting the entry/exit strategy with
virtual balance.

* **Entry**: on every scan, candidates with score ≥ `CRYPTO_PAPER_ENTRY_SCORE` and
  a fresh breakout (`at_high`) get a simulated BUY using `CRYPTO_PAPER_ALLOCATION_PERCENT`
  of the available cash (max `CRYPTO_PAPER_MAX_POSITIONS` concurrent positions).
* **Exit** (checked every scan): price hits TP1 → SELL 50%, TP2 → SELL the rest,
  SL → cut loss. Realized PnL is credited to the virtual account.
* **Persistence**: tables `crypto_paper_accounts`, `crypto_paper_positions`,
  `crypto_paper_trades`.
* **Telegram**: a 📝 notification is sent on every simulated open/close.

Commands: `/crypto paper`, `/crypto paper positions`, `/crypto paper history`.
API: `GET /api/crypto/paper/status`, `/paper/positions`, `/paper/history`.

### Configuration (see `.env.example`)

| Variable | Default | Description |
|----------|---------|-------------|
| `CRYPTO_PAPER_TRADING_ENABLED` | `true` | Enable the simulator |
| `CRYPTO_PAPER_INITIAL_BALANCE` | `1000000` | Virtual starting cash |
| `CRYPTO_PAPER_QUOTE_ASSET` | `USDT` | Quote asset for the account |
| `CRYPTO_PAPER_ALLOCATION_PERCENT` | `10` | % of cash per position |
| `CRYPTO_PAPER_MAX_POSITIONS` | `5` | Max concurrent positions |
| `CRYPTO_PAPER_ENTRY_SCORE` | `80` | Min score to enter |
| `CRYPTO_PAPER_ENTRY_REQUIRE_BREAKOUT` | `true` | Require breakout before entering |
| `CRYPTO_PAPER_NOTIFY` | `true` | Telegram notifications on open/close |

## 📡 MQTT (ESP32 sound/display alerts)

The bot publishes paper-trading events to a Mosquitto MQTT broker so a physical
ESP32 device (buzzer + OLED) can alert you with sound.

Topics (prefix configurable via `MQTT_TOPIC_PREFIX`):

| Topic | Event | Payload (JSON) |
|-------|-------|----------------|
| `crypto/trade/buy` | Position opened | `event, symbol, display, base, quote, entry_price, quantity, invested, ts` |
| `crypto/trade/profit` | TP1 / TP2 reached | `... + exit_price, exit_reason, pnl, pnl_percent` |
| `crypto/trade/loss` | SL reached | `... + exit_price, exit_reason, pnl, pnl_percent` |
| `crypto/trade/heartbeat` | Bot alive (60s) | `{"status": "alive"}` |

### Configuration (see `.env.example`)

| Variable | Default | Description |
|----------|---------|-------------|
| `MQTT_ENABLED` | `false` | Enable MQTT publishing |
| `MQTT_HOST` | `localhost` | Broker host (`host.docker.internal` from docker) |
| `MQTT_PORT` | `1883` | Broker port |
| `MQTT_USERNAME` / `MQTT_PASSWORD` | *(empty)* | Broker credentials |
| `MQTT_TOPIC_PREFIX` | `crypto/trade` | Topic prefix |
| `MQTT_HEARTBEAT_SECONDS` | `60` | Heartbeat interval |

> **Note**: publishing is best-effort — a broker outage never breaks the scanner.
> See `esp32/README.md` for the ESP32-C3 sketch (OLED + buzzer).

## 🤖 Telegram Commands & NLP

The bot understands both direct commands and natural language:

| Command | Description |
|---------|-------------|
| `/stock BBCA` | Quick price check |
| `/analyze BBCA` | Full AI analysis |
| `/news` | Latest market news |

**Natural Language Examples:**
- *"Gimana kondisi BBRI sekarang?"*
- *"Apa berita terbaru tentang teknologi di luar negeri?"*
- *"Bandingkan dengan TLKM"* (Uses memory of previous stock)
- *"Kasih info ekonomi global yang lagi viral"*

## 📊 Supported Stocks

30+ major IDX stocks including:
**Banking:** BBCA, BBRI, BMRI, BBNI, BRIS
**Telco:** TLKM, EXCL, ISAT
**Consumer:** UNVR, ICBP, INDF, KLBF
**Mining:** ADRO, PTBA, ANTM, INCO
**Tech:** GOTO, BUKA, EMTK
*Any valid IDX ticker works — data fetched via Yahoo Finance.*

## 🛠️ Development

### Run Locally (without Docker)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start PostgreSQL and Redis separately, then:
cp .env.example .env
# Edit .env with local DB/Redis URLs

# Run API server
uvicorn app.main:app --reload --port 8000

# Run bot (separate terminal)
python -m app.bot.telegram_bot
```

### Run Tests

```bash
pytest tests/ -v
```

## 📦 Deployment (VPS)

See [DEPLOYMENT.md](./DEPLOYMENT.md) for full VPS deployment guide.

---

## 📄 License

MIT License

## 🙏 Credits

- Stock data: [Yahoo Finance](https://finance.yahoo.com/) via [yfinance](https://github.com/ranaroussi/yfinance)
- AI: [Google Gemini](https://aistudio.google.com/) (Primary), [DeepSeek](https://www.deepseek.com/)
- Bot: [python-telegram-bot](https://python-telegram-bot.org/)
