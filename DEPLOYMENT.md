# 🚀 Deployment Guide — VPS

Complete guide to deploy IDX AI Stock Assistant on a VPS (Ubuntu 22.04 LTS).

---

## 📋 Prerequisites

| Requirement | Minimum |
|---|---|
| **OS** | Ubuntu 22.04 LTS |
| **CPU** | 2 vCPU |
| **RAM** | 4 GB |
| **Storage** | 40 GB SSD |
| **Network** | Public IP, ports 80/443 open |

## 1. Server Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo apt install -y docker-compose-plugin

# Verify
docker --version
docker compose version

# Install git
sudo apt install -y git
```

## 2. Deploy the Application

```bash
# Clone the repository
cd /opt
sudo mkdir idx-ai && sudo chown $USER:$USER idx-ai
git clone <YOUR_REPO_URL> /opt/idx-ai
cd /opt/idx-ai

# Create production environment file
cp .env.example .env
nano .env
```

### Production `.env` Configuration

```bash
# ── Application ──
APP_ENV=production
DEBUG=false
LOG_LEVEL=WARNING

# ── Database ──
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=idx_ai
POSTGRES_USER=idx_ai_user
POSTGRES_PASSWORD=<GENERATE_STRONG_PASSWORD>

# ── Redis ──
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# ── Telegram ──
TELEGRAM_BOT_TOKEN=<YOUR_BOT_TOKEN>
TELEGRAM_USE_WEBHOOK=false

# ── AI / LLM ──
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=<YOUR_DEEPSEEK_API_KEY>
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# ── Rate Limiting ──
RATE_LIMIT_PER_USER=20
RATE_LIMIT_WINDOW=60
```

## 3. Start Services

```bash
# Build and start all containers
docker compose up -d --build

# Check status
docker compose ps

# View logs
docker compose logs -f

# Run database migrations
docker compose exec app alembic upgrade head

# Seed stock tickers
docker compose exec app python scripts/seed_tickers.py
```

## 4. Verify

```bash
# Test health endpoint
curl http://localhost:8000/api/v1/health

# Test stock endpoint
curl http://localhost:8000/api/v1/stocks/BBCA/quote

# Check bot logs
docker compose logs bot

# Then test in Telegram: send /start to your bot
```

## 5. Nginx Reverse Proxy (Optional)

If you want to expose the API publicly:

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

Create `/etc/nginx/sites-available/idx-ai`:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/idx-ai /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# SSL (Let's Encrypt)
sudo certbot --nginx -d your-domain.com
```

## 6. Monitoring & Maintenance

### Auto-restart on Reboot

Docker Compose services have `restart: unless-stopped` — they auto-restart.

To ensure Docker starts on boot:
```bash
sudo systemctl enable docker
```

### Log Management

```bash
# View recent logs
docker compose logs --tail=100 app
docker compose logs --tail=100 bot

# Follow logs in real-time
docker compose logs -f bot
```

### Updates

```bash
cd /opt/idx-ai
git pull
docker compose up -d --build
docker compose exec app alembic upgrade head
```

### Backup Database

```bash
# Backup
docker compose exec postgres pg_dump -U idx_ai_user idx_ai > backup_$(date +%Y%m%d).sql

# Restore
cat backup_YYYYMMDD.sql | docker compose exec -T postgres psql -U idx_ai_user idx_ai
```

---

## 🛡️ Security Checklist

- [ ] Strong PostgreSQL password (not the default)
- [ ] `.env` file has restricted permissions (`chmod 600 .env`)
- [ ] Firewall configured (only 80/443/22 open)
- [ ] API docs disabled in production (`DEBUG=false`)
- [ ] Rate limiting enabled
- [ ] Regular OS updates
- [ ] Database backups scheduled

```bash
# Firewall setup
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```
