# XAUUSD AI Trading Bot

A 24/7 gold (XAUUSD) trading bot deployed on Google Cloud with a live Vercel dashboard.

## Architecture

| Layer | Tech | Location |
|-------|------|----------|
| 🤖 Bot + API | Python / FastAPI | Google Cloud `34.24.44.51:8000` |
| 🖥️ Dashboard | React / Vite | Vercel |

## Folders

### `/backend` — Trading Bot (Google Cloud)
- `main.py` — Bot entry point (`python3 main.py paper`)
- `api.py` — FastAPI REST + WebSocket server (port 8000)
- `requirements.txt` — Python dependencies
- `strategy/` — Trading logic (EMA, RSI, ATR, liquidity)
- `risk/` — Risk manager (1% per trade, max drawdown)
- `execution/` — Order executor (MT5 / paper)
- `data/` — Market data engine (yfinance / MT5)
- `ai/` — ML signal model

### `/frontend` — Live Dashboard (Vercel)
- `src/App.jsx` — Main dashboard component
- `src/main.jsx` — React entry point
- `index.html` — HTML shell
- `vite.config.js` — Vite config
- `package.json` — Dependencies

## Deploy

### Backend (GCP — already running)
```bash
sudo systemctl status xauusd-api   # API server
sudo systemctl status xauusd-bot   # Trading bot
```

### Frontend (Vercel)
1. Push `frontend/` to GitHub
2. Import repo in vercel.com
3. Deploy — Vite auto-detected ✅
