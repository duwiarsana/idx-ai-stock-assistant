#!/bin/bash
# VPS Setup Script - Run this ONCE on fresh VPS
# Usage: ssh root@76.13.19.250 'bash -s' < setup_vps.sh

set -e

echo "╔══════════════════════════════════════════════════════════╗"
echo "║        IDX AI Stock Assistant - VPS Initial Setup        ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Update system
echo "📦 Updating system packages..."
apt update && apt upgrade -y

# Install Docker
echo "🐳 Installing Docker..."
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
rm get-docker.sh

# Install Docker Compose Plugin
echo "📦 Installing Docker Compose..."
apt install -y docker-compose-plugin

# Install Git
echo "📦 Installing Git..."
apt install -y git

# Install Python dependencies
echo "🐍 Installing Python build dependencies..."
apt install -y python3-pip python3-venv python3-dev build-essential libpq-dev

# Verify installations
echo ""
echo "✅ Verifying installations..."
docker --version
docker compose version
git --version
python3 --version

# Clone repository (if not exists)
if [ ! -d "/opt/idx-ai-stock-assistant" ]; then
    echo ""
    echo "📁 Creating application directory..."
    mkdir -p /opt/idx-ai-stock-assistant
    cd /opt/idx-ai-stock-assistant
    
    echo "📥 Clone your repository here (or upload files manually)"
    echo "   git clone <YOUR_REPO_URL> ."
else
    echo ""
    echo "✅ Application directory already exists at /opt/idx-ai-stock-assistant"
fi

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║           ✅ VPS SETUP COMPLETE!                         ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "  1. Clone/pull your code to /opt/idx-ai-stock-assistant"
echo "  2. Copy .env file: nano /opt/idx-ai-stock-assistant/.env"
echo "  3. Run: docker-compose up -d --build"
echo "  4. Run migrations: docker-compose exec app alembic upgrade head"
echo "  5. Seed tickers: docker-compose exec app python scripts/seed_tickers.py"
echo ""
