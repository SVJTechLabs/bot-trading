# ============================================================
#  XAUUSD AI TRADING BOT — CONFIGURATION
#  Do NOT change these unless you understand the risk impact
# ============================================================

# --- Account ---
ACCOUNT_BALANCE     = 10_000        # USD
LEVERAGE            = 75
MAX_RISK_PER_TRADE  = 0.01          # 1% per trade = $100
MAX_DAILY_TRADES    = 5
MAX_DAILY_LOSS      = 0.05          # Stop bot if daily loss > 5%
MAX_DRAWDOWN        = 0.20          # Hard stop at 20% drawdown
MAX_LOT_SIZE        = 0.50
MIN_LOT_SIZE        = 0.01

# --- Symbol ---
SYMBOL              = "XAUUSD"
TIMEFRAME           = "M15"         # M5, M15, H1
SPREAD_LIMIT        = 30            # Don't trade if spread > 30 points

# --- Strategy ---
EMA_FAST            = 50
EMA_SLOW            = 200
RSI_PERIOD          = 14
RSI_OVERSOLD        = 38
RSI_OVERBOUGHT      = 62
ATR_PERIOD          = 14
ATR_SL_MULTIPLIER   = 1.5           # SL = ATR * 1.5
RR_RATIO            = 2.0           # Risk:Reward = 1:2

# --- AI Model ---
MIN_CONFIDENCE      = 0.65          # Only trade if AI confidence > 65%
MODEL_PATH          = "ai/model.pkl"
RETRAIN_EVERY       = 50            # Retrain after every 50 closed trades

# --- Sessions (UTC) ---
SESSIONS = {
    "london":   {"start": "07:00", "end": "11:00"},
    "new_york": {"start": "13:00", "end": "17:00"},
}

# --- Broker / MT5 ---
MT5_LOGIN           = None          # Your MT5 account number
MT5_PASSWORD        = None          # Your MT5 password
MT5_SERVER          = None          # Your broker server name

# --- Logging ---
LOG_FILE            = "logs/bot.log"
TRADE_LOG           = "logs/trades.csv"
