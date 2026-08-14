#!/bin/bash
# VPS Deployment Script for IDX AI Stock Assistant
# Usage: ./deploy_to_vps.sh

set -e

# Configuration
VPS_HOST="76.13.19.250"
VPS_USER="root"
VPS_PATH="/opt/idx-ai-stock-assistant"
LOCAL_PATH="$(pwd)"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║     IDX AI Stock Assistant - VPS Deployment Script       ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "📍 Target VPS: ${VPS_USER}@${VPS_HOST}"
echo "📁 Deploy Path: ${VPS_PATH}"
echo ""

# Step 1: Test SSH Connection
echo "🔍 Step 1: Testing SSH connection..."
if ssh -o ConnectTimeout=10 ${VPS_USER}@${VPS_HOST} "echo '✅ SSH connection successful'" 2>/dev/null; then
    echo "✅ SSH connection OK"
else
    echo "❌ SSH connection failed!"
    echo "Please check:"
    echo "  1. VPS is reachable: ping ${VPS_HOST}"
    echo "  2. SSH key is configured"
    echo "  3. Firewall allows port 22"
    exit 1
fi

# Step 2: Sync Files to VPS
echo ""
echo "📤 Step 2: Syncing files to VPS..."
rsync -avz --exclude 'venv' --exclude '.git' --exclude '__pycache__' \
    --exclude '*.pyc' --exclude '.env' \
    ${LOCAL_PATH}/ ${VPS_USER}@${VPS_HOST}:${VPS_PATH}/

echo "✅ Files synced successfully"

# Step 3: SSH to VPS and Deploy
echo ""
echo "🚀 Step 3: Deploying on VPS..."
ssh ${VPS_USER}@${VPS_HOST} << 'ENDSSH'
cd /opt/idx-ai-stock-assistant

echo "📦 Installing Python dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Install ML dependencies
echo "🤖 Installing ML dependencies (xgboost, lightgbm, shap)..."
pip install xgboost>=2.0.0 lightgbm>=4.0.0 shap>=0.43.0

echo "🔧 Stopping existing containers..."
docker-compose down

echo "🏗️  Building new images..."
docker-compose build --no-cache

echo "🚀 Starting services..."
docker-compose up -d

echo "⏳ Waiting for services to start..."
sleep 10

echo "📊 Checking container status..."
docker-compose ps

echo "📋 Checking app logs..."
docker-compose logs --tail=20 app

echo "✅ Deployment complete!"
ENDSSH

# Step 4: Verify Deployment
echo ""
echo "🔍 Step 4: Verifying deployment..."
ssh ${VPS_USER}@${VPS_HOST} << 'ENDSSH'
cd /opt/idx-ai-stock-assistant

# Check if app is responding
echo "🌐 Testing API health endpoint..."
curl -s http://localhost:8000/api/v1/health | head -20

# Check bot status
echo ""
echo "🤖 Checking bot status..."
docker-compose logs --tail=10 bot

# Show running containers
echo ""
echo "📦 Running containers:"
docker ps --filter "name=idx-ai"
ENDSSH

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║              ✅ DEPLOYMENT SUCCESSFUL!                   ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "📍 VPS: ${VPS_HOST}"
echo "🌐 API: http://${VPS_HOST}:8000"
echo "📊 Swagger: http://${VPS_HOST}:8000/docs"
echo "🤖 Bot: Check Telegram"
echo ""
echo "Next steps:"
echo "  1. Test API: curl http://${VPS_HOST}:8000/api/v1/health"
echo "  2. Test bot: Send /start to your Telegram bot"
echo "  3. Monitor: ssh root@${VPS_HOST} 'docker-compose logs -f'"
echo ""
