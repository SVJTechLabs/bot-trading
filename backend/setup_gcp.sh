#!/bin/bash
# ============================================================
#  XAUUSD AI BOT — GOOGLE CLOUD SETUP SCRIPT
#  Run once after SSH into your GCP server:
#    bash setup_gcp.sh
# ============================================================
set -e

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════╗"
echo "║   XAUUSD BOT — GOOGLE CLOUD SETUP        ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "${YELLOW}[1/6] Updating system...${NC}"
sudo apt-get update -qq && sudo apt-get upgrade -y -qq
echo -e "${GREEN}✓ System updated${NC}"

echo -e "${YELLOW}[2/6] Installing Python 3.11...${NC}"
sudo apt-get install -y -qq python3 python3-pip python3-venv python3-dev build-essential
echo -e "${GREEN}✓ Python $(python3 --version) ready${NC}"

echo -e "${YELLOW}[3/6] Installing tools...${NC}"
sudo apt-get install -y -qq curl wget unzip git
echo -e "${GREEN}✓ Tools ready${NC}"

echo -e "${YELLOW}[4/6] Creating virtual environment...${NC}"
python3 -m venv ~/bot_env
source ~/bot_env/bin/activate
pip install --quiet --upgrade pip
echo -e "${GREEN}✓ Virtual environment ready${NC}"

echo -e "${YELLOW}[5/6] Installing Python packages...${NC}"
pip install --quiet \
  pandas numpy ta yfinance scikit-learn \
  fastapi uvicorn python-dotenv requests websockets schedule
echo -e "${GREEN}✓ All packages installed${NC}"

echo -e "${YELLOW}[6/6] Setting up firewall...${NC}"
sudo ufw allow 22 && sudo ufw allow 8000 && sudo ufw --force enable
echo -e "${GREEN}✓ Firewall ready (port 22 SSH, 8000 API)${NC}"

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   SETUP COMPLETE ✓                        ║${NC}"
echo -e "${GREEN}║   Run next: bash deploy.sh                ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
