# 🚀 VPS Deployment Guide

## Quick Deploy to 76.13.19.250

### Option 1: Automated Deploy (Recommended)

```bash
# From your local machine
cd /Users/duwiarsana/.gemini/antigravity-ide/scratch/idx-ai-stock-assistant

# Make script executable
chmod +x scripts/deploy_to_vps.sh

# Run deployment
./scripts/deploy_to_vps.sh
```

### Option 2: Manual Deploy

#### Step 1: SSH to VPS
```bash
ssh root@76.13.19.250
```

#### Step 2: Check Current Status
```bash
# Check Docker containers
docker ps

# Check existing deployment
cd /opt/idx-ai-stock-assistant
docker-compose ps
```

#### Step 3: Update Code
```bash
cd /opt/idx-ai-stock-assistant

# If using Git
git pull origin main

# Or upload files via SCP from local machine:
# Exit SSH first, then run these locally:
scp -r app/ root@76.13.19.250:/opt/idx-ai-stock-assistant/
scp -r scripts/ root@76.13.19.250:/opt/idx-ai-stock-assistant/
scp requirements.txt root@76.13.19.250:/opt/idx-ai-stock-assistant/
```

#### Step 4: Install ML Dependencies
```bash
cd /opt/idx-ai-stock-assistant

# Activate venv
source venv/bin/activate

# Install ML packages
pip install xgboost>=2.0.0 lightgbm>=4.0.0 shap>=0.43.0

# Update requirements.txt (optional)
pip freeze > requirements.txt
```

#### Step 5: Rebuild & Restart
```bash
cd /opt/idx-ai-stock-assistant

# Stop containers
docker-compose down

# Rebuild with new dependencies
docker-compose build --no-cache

# Start services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f app
docker-compose logs -f bot
```

#### Step 6: Verify Deployment
```bash
# Test API
curl http://localhost:8000/api/v1/health

# Test stock endpoint
curl http://localhost:8000/api/v1/stocks/BBCA/quote

# Check bot
docker-compose logs --tail=20 bot
```

---

## 📦 Required Files to Upload

Minimum files needed:

```
/opt/idx-ai-stock-assistant/
├── app/                      # ← Upload entire folder
├── scripts/                  # ← Upload entire folder
├── alembic/                  # ← Upload entire folder
├── alembic.ini               # ← Upload
├── docker-compose.yml        # ← Upload
├── Dockerfile                # ← Upload
├── requirements.txt          # ← Upload (updated with ML deps)
├── .env                      # ← Create manually (don't upload!)
└── venv/                     # ← Already on VPS
```

---

## 🔧 Update .env on VPS

```bash
ssh root@76.13.19.250

# Edit .env file
nano /opt/idx-ai-stock-assistant/.env

# Make sure these are set:
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN_HERE
TELEGRAM_ADMIN_ID=YOUR_TELEGRAM_ADMIN_ID_HERE

# LLM Provider (Qwen via opencode)
LLM_PROVIDER=qwen
QWEN_BASE_URL=http://localhost:8000/v1
QWEN_MODEL=qwen3.5-397b

# Fallback to Groq
GROQ_API_KEY=your_groq_key_here
```

---

## 🐛 Troubleshooting

### Container Won't Start
```bash
# Check logs
docker-compose logs app

# Rebuild
docker-compose build --no-cache

# Check disk space
df -h
```

### Port Already in Use
```bash
# Check what's using port 8000
netstat -tulpn | grep 8000

# Kill process or change port in docker-compose.yml
```

### Database Migration Error
```bash
# Run migrations
docker-compose exec app alembic upgrade head

# Reset database (CAUTION: loses data)
docker-compose exec postgres psql -U idx_ai_user -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
docker-compose exec app alembic upgrade head
```

### Bot Not Responding
```bash
# Check bot token in .env
docker-compose exec app cat .env | grep TELEGRAM

# Restart bot only
docker-compose restart bot

# Check bot logs
docker-compose logs -f bot
```

---

## 📊 Post-Deployment Checklist

- [ ] API responds: `curl http://76.13.19.250:8000/api/v1/health`
- [ ] Bot responds: Send `/start` to Telegram bot
- [ ] Database migrated: `docker-compose exec app alembic current`
- [ ] ML dependencies installed: `docker-compose exec app python -c "import xgboost; print('✅')"`
- [ ] Logs are clean: `docker-compose logs --tail=50`
- [ ] Auto-restart enabled: `docker-compose ps` shows "Restarting" count = 0

---

## 🚀 After Deployment: Test ML Features

```bash
ssh root@76.13.19.250

cd /opt/idx-ai-stock-assistant
source venv/bin/activate

# Test ML Ensemble
python -c "
from app.services.ml_ensemble import MLEnsemble
ensemble = MLEnsemble()
print('✅ ML Ensemble loaded')
print(f'Models: {ensemble.get_models()}')
"

# Test Foreign Flow
python -c "
from app.services.foreign_flow import ForeignFlowAnalyzer
analyzer = ForeignFlowAnalyzer()
print('✅ Foreign Flow Analyzer loaded')
"

# Test Walk-Forward
python -c "
from app.services.walk_forward import WalkForwardValidator
validator = WalkForwardValidator()
print('✅ Walk-Forward Validator loaded')
"
```

---

## 📞 Quick Commands Reference

```bash
# View all containers
docker ps -a

# View logs
docker-compose logs -f

# Restart all services
docker-compose restart

# Stop all services
docker-compose down

# Start all services
docker-compose up -d

# Rebuild app
docker-compose build app

# Run command in container
docker-compose exec app <command>

# View disk usage
df -h

# View memory usage
free -h

# View CPU usage
top
```

---

## ✅ Deployment Complete!

After successful deployment:

1. **Test API**: http://76.13.19.250:8000/docs
2. **Test Bot**: Send `/start` on Telegram
3. **Monitor**: `docker-compose logs -f`
4. **Continue ML Implementation**: See next section

---

**Ready to deploy? Run:** `./scripts/deploy_to_vps.sh` 🚀
