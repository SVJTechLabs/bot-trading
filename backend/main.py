"""
XAUUSD AI TRADING BOT — MAIN LOOP
Runs 24/7, checks market every 60 seconds,
executes trades, manages risk, and learns.
"""

import time
import logging
import os
from datetime import datetime

# ── Setup Logging ────────────────────────────
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-15s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger("MainBot")

# ── Import Modules ───────────────────────────
from data.market_data   import get_data, get_prev_day_levels
from strategy.engine    import analyze
from risk.manager       import RiskManager
from execution.executor import ExecutionEngine
from ai.model           import GoldAIModel
from config.settings    import ACCOUNT_BALANCE, SYMBOL


# ────────────────────────────────────────────
#  BOT CLASS
# ────────────────────────────────────────────
class XAUUSDBot:

    def __init__(self, mode: str = "paper"):
        log.info("=" * 60)
        log.info("  XAUUSD AI TRADING BOT STARTING")
        log.info(f"  Mode: {mode.upper()} | Symbol: {SYMBOL}")
        log.info("=" * 60)

        self.mode      = mode
        self.risk      = RiskManager()
        self.executor  = ExecutionEngine(mode=mode)
        self.ai        = GoldAIModel()
        self.balance   = self.risk.state.account_balance
        self.running   = True
        self.cycle     = 0

    # ─────────────────────────────────────────
    #  MAIN LOOP
    # ─────────────────────────────────────────
    def run(self):
        log.info("Bot started. Ctrl+C to stop.")
        while self.running:
            try:
                self.cycle += 1
                self._tick()
                self._monitor_open_trades()
                time.sleep(60)

            except KeyboardInterrupt:
                log.info("Bot stopped by user.")
                break

            except Exception as e:
                log.error(f"Cycle error: {e}", exc_info=True)
                time.sleep(30)

    # ─────────────────────────────────────────
    #  SINGLE ANALYSIS CYCLE
    # ─────────────────────────────────────────
    def _tick(self):
        log.info(f"--- Cycle {self.cycle} | {datetime.now().strftime('%H:%M:%S')} ---")

        # 1. Fetch market data
        df = get_data(bars=300)
        if df is None or len(df) < 20:
            log.warning("Insufficient data — skipping cycle")
            return

        # 2. Get previous day levels
        levels = get_prev_day_levels(df)
        pdh    = levels.get("pdh")
        pdl    = levels.get("pdl")

        # 3. Strategy analysis
        signal = analyze(df, self.balance, pdh=pdh, pdl=pdl)
        log.info(f"Signal: {signal.direction} | conf={signal.confidence:.0%} | {signal.reason}")

        # 4. AI confidence boost / filter
        last    = df.iloc[-1]
        ai_feat = self._extract_features(last, signal)
        ai_conf = self.ai.predict(ai_feat)
        signal.confidence = (signal.confidence + ai_conf) / 2

        # 5. Risk approval gate
        approved, reason = self.risk.approve_trade(signal)
        if not approved:
            log.info(f"Trade blocked: {reason}")
            return

        # 6. Execute trade
        trade = self.executor.execute(signal)
        if "error" in trade:
            log.error(f"Execution failed: {trade['error']}")
            return

        log.info(
            f"✅ TRADE PLACED: {signal.direction} @ {signal.entry} "
            f"| SL: {signal.sl} | TP: {signal.tp1} | Lot: {signal.lot}"
        )

    # ─────────────────────────────────────────
    #  MONITOR OPEN TRADES (SL/TP check)
    # ─────────────────────────────────────────
    def _monitor_open_trades(self):
        if not self.executor.open_trades:
            return

        df  = get_data(bars=5)
        if df is None or df.empty:
            return

        price = float(df.iloc[-1]["close"])

        for trade in list(self.executor.open_trades):
            if trade["status"] != "open":
                continue

            direction = trade["direction"]
            entry     = trade["entry"]
            sl        = trade["sl"]
            tp1       = trade["tp1"]

            hit_tp = (direction == "BUY"  and price >= tp1) or \
                     (direction == "SELL" and price <= tp1)
            hit_sl = (direction == "BUY"  and price <= sl)  or \
                     (direction == "SELL" and price >= sl)

            if hit_tp or hit_sl:
                result = self.executor.close_trade(trade["ticket"], price)
                pnl    = result.get("pnl", 0)
                self.risk.record_trade(pnl)
                self.balance = self.risk.state.account_balance

                # AI learns from this trade
                ai_feat = self._extract_features_from_trade(trade)
                self.ai.record_outcome(ai_feat, pnl)

                status = "TP HIT ✅" if hit_tp else "SL HIT ❌"
                log.info(f"{status} | PnL: {pnl:+.2f} | Balance: {self.balance:.2f}")

    # ─────────────────────────────────────────
    #  FEATURE EXTRACTION FOR AI
    # ─────────────────────────────────────────
    def _extract_features(self, row, signal) -> dict:
        return {
            "trend":      float(row.get("trend", 0)),
            "rsi":        float(row.get("rsi", 50)),
            "atr":        float(row.get("atr", 0)),
            "in_session": float(row.get("in_session", False)),
            "has_sweep":  1.0 if "sweep" in signal.reason.lower() else 0.0,
            "rejection":  1.0 if "rejection" in signal.reason.lower() else 0.0,
            "confidence": float(signal.confidence),
            "hour":       float(datetime.now().hour),
        }

    def _extract_features_from_trade(self, trade: dict) -> dict:
        return {
            "trend":      0.0,
            "rsi":        50.0,
            "atr":        0.0,
            "in_session": 1.0,
            "has_sweep":  1.0 if "sweep" in trade.get("reason", "") else 0.0,
            "rejection":  0.0,
            "confidence": trade.get("confidence", 0.5),
            "hour":       float(datetime.fromisoformat(trade["time"]).hour),
        }

    def status(self) -> dict:
        return {
            "bot":      "running" if self.running else "stopped",
            "mode":     self.mode,
            "cycle":    self.cycle,
            "account":  self.risk.get_status(),
            "ai":       self.ai.get_stats(),
        }


# ────────────────────────────────────────────
#  ENTRY POINT
# ────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "paper"
    bot  = XAUUSDBot(mode=mode)
    bot.run()
