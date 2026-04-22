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
- 📈 **Technical Indicators** — RSI, MACD, SMA calculated automatically
- 💬 **Natural Language** — Ask questions in Indonesian or English
- ⚡ **Redis Caching** — Fast responses with 5-minute cache
- 🔒 **Rate Limiting** — Protection against abuse

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

## 🤖 Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome & instructions |
| `/help` | Full help guide |
| `/stock BBCA` | Quick price check |
| `/s BBCA` | Shortcut for /stock |
| `/analyze BBCA` | Full AI analysis |
| `/a BBCA` | Shortcut for /analyze |

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
