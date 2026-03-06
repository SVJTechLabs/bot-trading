# XAUUSD AI Trading Bot

Autonomous gold trading system built with Python.
Intraday strategy · Liquidity sweep logic · AI self-improvement.

---

## Project Structure

```
xauusd_bot/
├── main.py                  ← Start the bot here
├── requirements.txt
├── config/
│   └── settings.py          ← All parameters (risk, strategy, account)
├── data/
│   └── market_data.py       ← Fetches XAUUSD candles + indicators
├── strategy/
│   └── engine.py            ← Core trading logic (trend + liquidity + momentum)
├── risk/
│   └── manager.py           ← Account protection (SL, drawdown, daily limits)
├── execution/
│   └── executor.py          ← Places trades via MT5 or paper mode
├── ai/
│   └── model.py             ← AI model that learns from trade history
└── logs/
    ├── bot.log              ← Full system log
    └── trades.csv           ← Every trade recorded
```

---

## Setup

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Run in paper mode (safe — no real money)

```bash
python main.py paper
```

### 3. Run in live mode (real trades via MT5)

Edit `config/settings.py` and fill in your broker credentials:

```python
MT5_LOGIN    = 12345678
MT5_PASSWORD = "your_password"
MT5_SERVER   = "YourBroker-Server"
```

Then run:

```bash
python main.py live
```

---

## Strategy Logic

1. **Trend filter** — EMA 50/200 determines market bias
2. **Liquidity sweep** — detects institutional stop hunts
3. **RSI confirmation** — momentum alignment
4. **Session filter** — only trades London & New York
5. **Rejection candle** — wick confirmation

---

## Risk Rules (built-in, non-negotiable)

| Rule | Value |
|------|-------|
| Risk per trade | 1% ($100) |
| Max lot size | 0.50 |
| Max trades/day | 5 |
| Max daily loss | 5% |
| Max drawdown | 20% |
| Stop after losses | 3 consecutive |

---

## AI Self-Improvement

- Starts as a rule-based system
- Records every trade outcome
- After 50 trades → trains Random Forest model
- Every 50 trades after that → retrains with new data
- Confidence improves over time

---

## Cloud Deployment (24/7)

Deploy on Oracle Cloud free tier:

```bash
# On your cloud server
git clone <your-repo>
pip install -r requirements.txt
nohup python main.py paper > logs/output.log 2>&1 &
```

---

## Dashboard

The React dashboard (`xauusd_dashboard.jsx`) connects to this backend.
Start the API server:

```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

---

## Important

- Always test on paper/demo first
- Never risk money you cannot afford to lose
- Past performance does not guarantee future results
