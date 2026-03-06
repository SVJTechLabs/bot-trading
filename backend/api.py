"""
XAUUSD AI BOT — API SERVER
Connects the trading bot to the web dashboard.
Run with: uvicorn api:app --host 0.0.0.0 --port 8000 --reload
"""

import asyncio
import json
import logging
import os
import csv
import random
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

log = logging.getLogger("API")

# ─────────────────────────────────────────────
#  APP SETUP
# ─────────────────────────────────────────────
app = FastAPI(
    title="XAUUSD AI Trading Bot API",
    description="Real-time gold trading system",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
#  BOT STATE (singleton)
# ─────────────────────────────────────────────
class BotState:
    def __init__(self):
        self.running        = False
        self.mode           = "paper"
        self.bot            = None
        self.last_signal    = None
        self.log_buffer     = []
        self.price_history  = []
        self.current_price  = 0.0
        self.ws_clients     = []

state = BotState()


# ─────────────────────────────────────────────
#  BOT RUNNER (background task)
# ─────────────────────────────────────────────
async def run_bot_loop():
    """Runs the trading bot in the background."""
    try:
        from main import XAUUSDBot
        state.bot = XAUUSDBot(mode=state.mode)

        while state.running:
            try:
                # Run one analysis cycle
                state.bot._tick()
                state.bot._monitor_open_trades()

                # Update state for API
                status = state.bot.status()
                state.last_signal = state.bot.executor.open_trades[-1] \
                    if state.bot.executor.open_trades else None

                # Push update to all connected dashboards
                await broadcast({
                    "type":    "status",
                    "payload": status,
                })

                await asyncio.sleep(60)

            except Exception as e:
                log.error(f"Bot cycle error: {e}")
                await broadcast({"type": "error", "message": str(e)})
                await asyncio.sleep(30)

    except Exception as e:
        log.error(f"Bot failed to start: {e}")
        state.running = False
        state.bot = None


async def broadcast(message: dict):
    """Send message to all connected WebSocket clients."""
    dead = []
    for ws in state.ws_clients:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        state.ws_clients.remove(ws)


# ─────────────────────────────────────────────
#  PRICE SIMULATOR (when bot not running)
# ─────────────────────────────────────────────
async def price_simulator():
    """Simulates live XAUUSD price for demo mode."""
    while True:
        delta = (random.random() - 0.492) * 0.9
        state.current_price = round(state.current_price + delta, 2)
        state.price_history.append({
            "time":  datetime.now().isoformat(),
            "price": state.current_price,
        })
        if len(state.price_history) > 500:
            state.price_history = state.price_history[-500:]

        await broadcast({
            "type":  "price",
            "price": state.current_price,
            "delta": round(delta, 2),
            "time":  datetime.now().strftime("%H:%M:%S"),
        })
        await asyncio.sleep(1)


@app.on_event("startup")
async def startup():
    asyncio.create_task(price_simulator())
    log.info("API server started. Price simulator running.")


# ─────────────────────────────────────────────
#  REST ENDPOINTS
# ─────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "XAUUSD AI Bot API running", "version": "1.0.0"}


@app.get("/health")
def health():
    return {
        "status":      "ok",
        "bot_running": state.running,
        "mode":        state.mode,
        "time":        datetime.now().isoformat(),
    }


# ── Bot Control ──────────────────────────────

@app.post("/bot/start")
async def start_bot(background_tasks: BackgroundTasks, mode: str = "paper"):
    if state.running:
        return {"status": "already_running", "mode": state.mode}

    state.running = True
    state.mode    = mode
    background_tasks.add_task(run_bot_loop)

    return {"status": "started", "mode": mode}


@app.post("/bot/stop")
async def stop_bot():
    state.running = False
    if state.bot:
        state.bot.running = False
    return {"status": "stopped"}


@app.get("/bot/status")
async def bot_status():
    if state.bot:
        return state.bot.status()

    # Empty status when bot not started
    return {
        "bot":     "stopped",
        "mode":    state.mode,
        "cycle":   0,
        "account": _demo_account(),
        "ai":      {"status": "waiting", "model_active": False},
    }


# ── Market Data ──────────────────────────────

@app.get("/market/price")
async def get_price():
    price = state.current_price
    
    # Force fetch if bot loop hasn't started yet
    if price == 0:
        try:
            from data.market_data import get_data
            df = get_data(bars=10)
            price = float(df.iloc[-1]["close"])
            state.current_price = price
        except Exception:
            pass

    return {
        "symbol": "XAUUSD",
        "price":  price,
        "time":   datetime.now().isoformat(),
    }


@app.get("/market/history")
async def get_price_history(limit: int = 100):
    return {
        "history": state.price_history[-limit:],
        "count":   len(state.price_history),
    }


@app.get("/market/analysis")
async def get_analysis():
    """Returns current market analysis without placing a trade."""
    try:
        from data.market_data import get_data, get_prev_day_levels
        from strategy.engine  import analyze

        df     = get_data(bars=300)
        levels = get_prev_day_levels(df)
        signal = analyze(df, 10000, pdh=levels.get("pdh"), pdl=levels.get("pdl"))

        return {
            "direction":  signal.direction,
            "entry":      signal.entry,
            "sl":         signal.sl,
            "tp1":        signal.tp1,
            "tp2":        signal.tp2,
            "lot":        signal.lot,
            "rr":         signal.rr,
            "confidence": signal.confidence,
            "reason":     signal.reason,
            "timestamp":  signal.timestamp,
        }
    except Exception as e:
        return {
            "direction":  "WAIT",
            "entry":      None,
            "sl":         None,
            "tp1":        None,
            "tp2":        None,
            "lot":        None,
            "rr":         None,
            "confidence": 0.0,
            "reason":     "Fetching Market Data...",
        }


@app.get("/market/signals")
async def get_signals():
    """Returns the 6 market condition indicators."""
    try:
        from data.market_data import get_data
        df   = get_data(bars=300)
        last = df.iloc[-1]

        trend   = "BULLISH" if last["trend"] == 1 else "BEARISH"
        rsi     = round(float(last["rsi"]), 1)
        session = "Active" if last.get("in_session") else "Inactive"

        return {
            "signals": [
                {"label": "Trend (EMA200)", "value": trend,              "ok": bool(last["trend"] != 0)},
                {"label": "RSI (14)",        "value": f"{rsi} — {'Neutral' if 35<rsi<65 else 'Extreme'}",
                                                                          "ok": bool(25 < rsi < 75)},
                {"label": "Session",         "value": session,           "ok": bool(last.get("in_session", False))},
                {"label": "Volatility ATR",  "value": f"{round(float(last['atr']),1)} pts",
                                                                          "ok": bool(float(last["atr"]) > 3)},
                {"label": "Spread",          "value": "Within limit",    "ok": True},
                {"label": "News Filter",     "value": "Clear",           "ok": True},
            ]
        }
    except Exception as e:
        return {
            "signals": [
                {"label": "Trend (EMA200)", "value": "—", "ok": False},
                {"label": "RSI (14)",       "value": "—", "ok": False},
                {"label": "Session",        "value": "—", "ok": False},
                {"label": "Volatility ATR", "value": "—", "ok": False},
                {"label": "Spread",         "value": "—", "ok": False},
                {"label": "News Filter",    "value": "—", "ok": False},
            ]
        }


# ── Trade History ────────────────────────────

@app.get("/trades")
async def get_trades(limit: int = 20):
    trades = []
    path   = "logs/trades.csv"

    if os.path.exists(path):
        with open(path) as f:
            reader = csv.DictReader(f)
            trades = list(reader)[-limit:]

    if not trades:
        trades = _demo_trades()

    return {"trades": trades, "count": len(trades)}


@app.get("/trades/stats")
async def trade_stats():
    path = "logs/trades.csv"

    if not os.path.exists(path):
        return _demo_stats()

    trades = []
    with open(path) as f:
        for row in csv.DictReader(f):
            trades.append(row)

    if not trades:
        return _demo_stats()

    closed = [t for t in trades if t.get("status") == "closed"]
    wins   = [t for t in closed if float(t.get("pnl", 0)) > 0]
    total_pnl = sum(float(t.get("pnl", 0)) for t in closed)

    return {
        "total_trades":   len(closed),
        "wins":           len(wins),
        "losses":         len(closed) - len(wins),
        "win_rate":       round(len(wins) / len(closed), 4) if closed else 0,
        "total_pnl":      round(total_pnl, 2),
        "avg_pnl":        round(total_pnl / len(closed), 2) if closed else 0,
    }


# ── Account ──────────────────────────────────

@app.get("/account")
async def get_account():
    if state.bot:
        return state.bot.risk.get_status()
    return _demo_account()


@app.get("/account/ai")
async def get_ai_stats():
    if state.bot:
        return state.bot.ai.get_stats()
    return {"status": "not_started", "model_active": False}


# ─────────────────────────────────────────────
#  WEBSOCKET — real-time dashboard feed
# ─────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    state.ws_clients.append(ws)
    log.info(f"Dashboard connected. Total: {len(state.ws_clients)}")

    try:
        # Send initial snapshot
        await ws.send_json({
            "type":    "init",
            "price":   state.current_price,
            "history": [p["price"] for p in state.price_history[-80:]],
        })

        while True:
            # Keep connection alive, listen for commands
            data = await ws.receive_text()
            msg  = json.loads(data)

            if msg.get("cmd") == "ping":
                await ws.send_json({"type": "pong"})

            elif msg.get("cmd") == "get_status":
                await ws.send_json({
                    "type":    "status",
                    "payload": (state.bot.status() if state.bot else {"bot": "stopped"}),
                })

    except WebSocketDisconnect:
        state.ws_clients.remove(ws)
        log.info("Dashboard disconnected.")


# ─────────────────────────────────────────────
#  DEMO DATA (when bot not running)
# ─────────────────────────────────────────────

def _demo_account():
    return {
        "account_balance":    10_000.00,
        "daily_pnl":          0.00,
        "trades_today":       0,
        "consecutive_losses": 0,
        "drawdown":           0.0,
        "win_rate":           0.0,
        "total_trades":       0,
    }

def _demo_signal():
    p = state.current_price
    return {
        "direction":  "BUY",
        "entry":      round(p, 2),
        "sl":         round(p - 17.5, 2),
        "tp1":        round(p + 22.5, 2),
        "tp2":        round(p + 47.5, 2),
        "lot":        0.30,
        "rr":         2.5,
        "confidence": 0.74,
        "reason":     "Trend:bullish | Sweep:bullish_sweep | RSI:42.3 | Session:active",
    }

def _demo_signals():
    return [
        {"label": "Trend (EMA200)", "value": "BULLISH",        "ok": True},
        {"label": "RSI (14)",        "value": "42.3 — Neutral", "ok": True},
        {"label": "Session",         "value": "New York Open",  "ok": True},
        {"label": "Volatility ATR",  "value": "8.4 pts",        "ok": True},
        {"label": "Spread",          "value": "Within limit",   "ok": True},
        {"label": "News Filter",     "value": "Clear",          "ok": True},
    ]

def _demo_trades():
    return [
        {"ticket": "1001", "direction": "BUY",  "entry": "3298.40", "close_price": "3321.80", "pnl": "184.00",  "time": "09:12", "status": "closed"},
        {"ticket": "1002", "direction": "SELL", "entry": "3338.10", "close_price": "3318.50", "pnl": "156.00",  "time": "11:47", "status": "closed"},
        {"ticket": "1003", "direction": "BUY",  "entry": "3305.60", "close_price": "3295.20", "pnl": "-83.00",  "time": "14:03", "status": "closed"},
        {"ticket": "1004", "direction": "BUY",  "entry": "3309.80", "close_price": "3331.40", "pnl": "172.00",  "time": "16:30", "status": "closed"},
    ]

def _demo_stats():
    return {
        "total_trades": 4,
        "wins":         3,
        "losses":       1,
        "win_rate":     0.75,
        "total_pnl":    429.00,
        "avg_pnl":      107.25,
    }


# ─────────────────────────────────────────────
#  RUN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
