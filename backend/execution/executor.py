"""
EXECUTION ENGINE
Connects to MetaTrader 5 and places trades.
Falls back to paper trading mode if MT5 unavailable.
"""

import logging
import csv
import os
from datetime import datetime
from strategy.engine import Signal

log = logging.getLogger("Execution")
TRADE_LOG = "logs/trades.csv"


class ExecutionEngine:
    """
    Handles all trade execution.
    Two modes:
      - live:  connects to MetaTrader 5
      - paper: simulates trades locally (safe for testing)
    """

    def __init__(self, mode: str = "paper"):
        self.mode    = mode
        self.mt5_ok  = False
        self.open_trades = []

        if mode == "live":
            self._connect_mt5()

        os.makedirs("logs", exist_ok=True)
        if not os.path.exists(TRADE_LOG):
            self._init_csv()

    # ─────────────────────────────────────────
    #  PLACE TRADE
    # ─────────────────────────────────────────
    def execute(self, signal: Signal) -> dict:
        if self.mode == "live" and self.mt5_ok:
            return self._execute_mt5(signal)
        return self._execute_paper(signal)

    # ─────────────────────────────────────────
    #  CLOSE TRADE
    # ─────────────────────────────────────────
    def close_trade(self, ticket: int, close_price: float) -> dict:
        if self.mode == "live" and self.mt5_ok:
            return self._close_mt5(ticket, close_price)
        return self._close_paper(ticket, close_price)

    # ─────────────────────────────────────────
    #  MT5 LIVE EXECUTION
    # ─────────────────────────────────────────
    def _connect_mt5(self):
        try:
            import MetaTrader5 as mt5
            from config.settings import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER

            if MT5_LOGIN:
                ok = mt5.initialize(
                    login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER
                )
            else:
                ok = mt5.initialize()

            if ok:
                self.mt5_ok = True
                log.info("MT5 connected ✓")
            else:
                log.warning("MT5 connection failed — using paper mode")

        except ImportError:
            log.warning("MetaTrader5 not installed — using paper mode")

    def _execute_mt5(self, signal: Signal) -> dict:
        import MetaTrader5 as mt5
        from config.settings import SYMBOL

        tick  = mt5.symbol_info_tick(SYMBOL)
        price = tick.ask if signal.direction == "BUY" else tick.bid
        order_type = mt5.ORDER_TYPE_BUY if signal.direction == "BUY" else mt5.ORDER_TYPE_SELL

        request = {
            "action":    mt5.TRADE_ACTION_DEAL,
            "symbol":    SYMBOL,
            "volume":    signal.lot,
            "type":      order_type,
            "price":     price,
            "sl":        signal.sl,
            "tp":        signal.tp1,
            "deviation": 20,
            "magic":     202400,
            "comment":   "XAUUSD AI Bot",
        }

        result = mt5.order_send(request)

        if result.retcode == mt5.TRADE_RETCODE_DONE:
            log.info(f"MT5 order placed ✓ ticket={result.order}")
            trade = {
                "ticket":    result.order,
                "direction": signal.direction,
                "entry":     price,
                "sl":        signal.sl,
                "tp1":       signal.tp1,
                "lot":       signal.lot,
                "time":      str(datetime.now()),
                "status":    "open",
            }
            self.open_trades.append(trade)
            self._log_trade(trade)
            return trade
        else:
            log.error(f"MT5 order failed: retcode={result.retcode}")
            return {"error": result.retcode}

    def _close_mt5(self, ticket: int, close_price: float) -> dict:
        import MetaTrader5 as mt5

        position = mt5.positions_get(ticket=ticket)
        if not position:
            return {"error": "Position not found"}

        pos = position[0]
        close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
        tick  = mt5.symbol_info_tick(pos.symbol)
        price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask

        request = {
            "action":   mt5.TRADE_ACTION_DEAL,
            "symbol":   pos.symbol,
            "volume":   pos.volume,
            "type":     close_type,
            "position": ticket,
            "price":    price,
            "deviation": 20,
            "comment":  "Bot close",
        }

        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            pnl = pos.profit
            log.info(f"MT5 trade closed ✓ PnL: {pnl:.2f}")
            return {"ticket": ticket, "pnl": pnl, "status": "closed"}
        return {"error": result.retcode}

    # ─────────────────────────────────────────
    #  PAPER TRADING (safe testing mode)
    # ─────────────────────────────────────────
    def _execute_paper(self, signal: Signal) -> dict:
        ticket = len(self.open_trades) + 1000
        trade  = {
            "ticket":    ticket,
            "direction": signal.direction,
            "entry":     signal.entry,
            "sl":        signal.sl,
            "tp1":       signal.tp1,
            "tp2":       signal.tp2,
            "lot":       signal.lot,
            "confidence": signal.confidence,
            "reason":    signal.reason,
            "time":      str(datetime.now()),
            "status":    "open",
        }
        self.open_trades.append(trade)
        self._log_trade(trade)
        log.info(f"PAPER trade: {signal.direction} @ {signal.entry} | SL {signal.sl} | TP {signal.tp1}")
        return trade

    def _close_paper(self, ticket: int, close_price: float) -> dict:
        for t in self.open_trades:
            if t["ticket"] == ticket and t["status"] == "open":
                if t["direction"] == "BUY":
                    pnl = (close_price - t["entry"]) * t["lot"] * 100
                else:
                    pnl = (t["entry"] - close_price) * t["lot"] * 100

                t["status"]      = "closed"
                t["close_price"] = close_price
                t["pnl"]         = round(pnl, 2)
                self._log_trade(t)
                log.info(f"PAPER trade closed: PnL {pnl:+.2f}")
                return t
        return {"error": "Trade not found"}

    # ─────────────────────────────────────────
    #  CSV LOGGING
    # ─────────────────────────────────────────
    def _init_csv(self):
        with open(TRADE_LOG, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "ticket", "direction", "entry", "sl", "tp1",
                "lot", "confidence", "reason", "time", "status",
                "close_price", "pnl"
            ])
            writer.writeheader()

    def _log_trade(self, trade: dict):
        with open(TRADE_LOG, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "ticket", "direction", "entry", "sl", "tp1",
                "lot", "confidence", "reason", "time", "status",
                "close_price", "pnl"
            ], extrasaction="ignore")
            writer.writerow(trade)
