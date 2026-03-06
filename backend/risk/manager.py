"""
RISK MANAGER
Protects your $10,000 account.
No trade passes without risk approval.
"""

import logging
import json
import os
from datetime import date
from dataclasses import dataclass, field
from typing import List

log = logging.getLogger("RiskManager")
STATE_FILE = "logs/risk_state.json"


@dataclass
class RiskState:
    date:              str   = ""
    trades_today:      int   = 0
    daily_pnl:         float = 0.0
    consecutive_losses: int  = 0
    account_balance:   float = 10_000.0
    peak_balance:      float = 10_000.0
    total_trades:      int   = 0
    wins:              int   = 0
    losses:            int   = 0


class RiskManager:
    """
    Gate-keeper for every trade.
    Enforces all account protection rules.
    """

    def __init__(self):
        self.state = self._load_state()
        self._reset_if_new_day()

    # ─────────────────────────────────────────
    #  MAIN GATE — called before every trade
    # ─────────────────────────────────────────
    def approve_trade(self, signal) -> tuple[bool, str]:
        """
        Returns (approved: bool, reason: str)
        """
        from config.settings import (
            MAX_DAILY_TRADES, MAX_DAILY_LOSS,
            MAX_DRAWDOWN, MIN_CONFIDENCE
        )

        s = self.state

        # 1. Check bot was stopped after losses
        if s.consecutive_losses >= 3:
            return False, "Bot paused: 3 consecutive losses. Review strategy."

        # 2. Daily trade limit
        if s.trades_today >= MAX_DAILY_TRADES:
            return False, f"Daily trade limit reached ({MAX_DAILY_TRADES})"

        # 3. Daily loss limit
        daily_loss_pct = abs(s.daily_pnl) / s.account_balance if s.daily_pnl < 0 else 0
        if daily_loss_pct >= MAX_DAILY_LOSS:
            return False, f"Daily loss limit hit ({daily_loss_pct:.1%}). Stopping for today."

        # 4. Max drawdown
        drawdown = (s.peak_balance - s.account_balance) / s.peak_balance
        if drawdown >= MAX_DRAWDOWN:
            return False, f"Max drawdown hit ({drawdown:.1%}). Bot stopped."

        # 5. AI confidence
        if signal.confidence < MIN_CONFIDENCE:
            return False, f"Low confidence: {signal.confidence:.0%} < {MIN_CONFIDENCE:.0%}"

        # 6. No trade on WAIT signal
        if signal.direction == "WAIT":
            return False, f"No signal: {signal.reason}"

        log.info(f"Trade APPROVED: {signal.direction} | conf={signal.confidence:.0%}")
        return True, "Approved"

    # ─────────────────────────────────────────
    #  Called after each trade closes
    # ─────────────────────────────────────────
    def record_trade(self, pnl: float):
        s = self.state
        s.trades_today      += 1
        s.total_trades      += 1
        s.daily_pnl         += pnl
        s.account_balance   += pnl

        if pnl > 0:
            s.wins              += 1
            s.consecutive_losses = 0
            if s.account_balance > s.peak_balance:
                s.peak_balance = s.account_balance
        else:
            s.losses             += 1
            s.consecutive_losses += 1

        self._save_state()
        log.info(
            f"Trade recorded | PnL: {'+'if pnl>0 else ''}{pnl:.2f} | "
            f"Balance: {s.account_balance:.2f} | "
            f"Streak: {s.consecutive_losses} losses"
        )

    # ─────────────────────────────────────────
    #  Status Report
    # ─────────────────────────────────────────
    def get_status(self) -> dict:
        s = self.state
        win_rate = s.wins / s.total_trades if s.total_trades > 0 else 0
        drawdown = (s.peak_balance - s.account_balance) / s.peak_balance

        return {
            "account_balance":    round(s.account_balance, 2),
            "daily_pnl":          round(s.daily_pnl, 2),
            "trades_today":       s.trades_today,
            "consecutive_losses": s.consecutive_losses,
            "drawdown":           round(drawdown, 4),
            "win_rate":           round(win_rate, 4),
            "total_trades":       s.total_trades,
        }

    def reset_daily(self):
        self.state.trades_today = 0
        self.state.daily_pnl    = 0.0
        self.state.date         = str(date.today())
        self._save_state()
        log.info("Daily risk counters reset")

    # ─────────────────────────────────────────
    #  State persistence
    # ─────────────────────────────────────────
    def _reset_if_new_day(self):
        today = str(date.today())
        if self.state.date != today:
            self.reset_daily()

    def _save_state(self):
        os.makedirs("logs", exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(self.state.__dict__, f, indent=2)

    def _load_state(self) -> RiskState:
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE) as f:
                    data = json.load(f)
                return RiskState(**data)
            except Exception:
                pass
        return RiskState(date=str(date.today()))
