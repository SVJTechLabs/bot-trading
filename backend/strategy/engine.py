"""
STRATEGY ENGINE
Core trading logic used by experienced XAUUSD traders.
Combines: Trend + Liquidity Sweep + Momentum + Session Filter
"""

import pandas as pd
import numpy as np
import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger("Strategy")


@dataclass
class Signal:
    direction:  str             # "BUY" | "SELL" | "WAIT"
    entry:      float
    sl:         float
    tp1:        float
    tp2:        float
    lot:        float
    rr:         float
    confidence: float           # 0.0 – 1.0
    reason:     str
    timestamp:  str = ""


# ─────────────────────────────────────────────
#  MAIN STRATEGY FUNCTION
# ─────────────────────────────────────────────
def analyze(df: pd.DataFrame, account_balance: float, pdh: float = None, pdl: float = None) -> Signal:
    """
    Full market analysis.
    Returns a Signal object with complete trade plan or WAIT.
    """
    if len(df) < 10:
        return _wait("Not enough data")

    last     = df.iloc[-1]
    prev     = df.iloc[-2]

    # ── 1. Trend Filter ──────────────────────
    trend = _get_trend(last)

    # ── 2. Session Filter ────────────────────
    if not last.get("in_session", True):
        return _wait("Outside trading session")

    # ── 3. Liquidity Sweep ───────────────────
    sweep = _detect_liquidity_sweep(df, pdh, pdl)

    # ── 4. Momentum Confirmation ─────────────
    rsi = last["rsi"]
    atr = last["atr"]

    # ── 5. Rejection Candle ──────────────────
    rejection = _check_rejection_candle(last)

    # ── 6. Confidence Scoring ────────────────
    score, reasons = _score_setup(trend, sweep, rsi, rejection, last)

    if score < 0.50:
        return _wait(f"Low confidence: {score:.0%} — {reasons}")

    # ── 7. Build Trade Plan ──────────────────
    direction = _get_direction(trend, sweep)

    entry = float(last["close"])
    sl, tp1, tp2 = _calculate_levels(direction, entry, atr)
    lot = _calculate_lot(account_balance, entry, sl)
    rr  = abs(tp1 - entry) / abs(entry - sl) if abs(entry - sl) > 0 else 0

    log.info(f"SIGNAL {direction} | conf={score:.0%} | {reasons}")

    return Signal(
        direction  = direction,
        entry      = round(entry, 2),
        sl         = round(sl, 2),
        tp1        = round(tp1, 2),
        tp2        = round(tp2, 2),
        lot        = lot,
        rr         = round(rr, 2),
        confidence = round(score, 2),
        reason     = reasons,
        timestamp  = str(pd.Timestamp.now()),
    )


# ─────────────────────────────────────────────
#  ANALYSIS HELPERS
# ─────────────────────────────────────────────
def _get_trend(row) -> int:
    """
    1 = Bullish, -1 = Bearish, 0 = Neutral
    Based on EMA fast/slow relationship
    """
    fast = row.get("ema_fast", 0)
    slow = row.get("ema_slow", 0)
    if fast > slow * 1.0005:
        return 1
    if fast < slow * 0.9995:
        return -1
    return 0


def _detect_liquidity_sweep(df: pd.DataFrame, pdh: float, pdl: float) -> str:
    """
    Detects institutional liquidity grabs.
    Pattern: Price pokes above/below key level then closes back.
    Returns: 'bullish_sweep' | 'bearish_sweep' | None
    """
    last  = df.iloc[-1]
    prev  = df.iloc[-2]
    close = float(last["close"])
    high  = float(last["high"])
    low   = float(last["low"])

    # Check previous day levels
    if pdh and pdl:
        # Bearish sweep: wick above PDH then closed below = sell setup
        if high > pdh and close < pdh:
            return "bearish_sweep"
        # Bullish sweep: wick below PDL then closed above = buy setup
        if low < pdl and close > pdl:
            return "bullish_sweep"

    # Check recent swing highs/lows (last 20 bars)
    recent = df.iloc[-20:]
    swing_high = float(recent["high"].max())
    swing_low  = float(recent["low"].min())

    if high > swing_high * 1.0002 and close < swing_high:
        return "bearish_sweep"
    if low < swing_low * 0.9998 and close > swing_low:
        return "bullish_sweep"

    return None


def _check_rejection_candle(row) -> bool:
    """
    Checks for strong rejection wicks — key confirmation.
    """
    body     = float(row.get("body", 0))
    wick_up  = float(row.get("wick_up", 0))
    wick_dn  = float(row.get("wick_down", 0))
    atr      = float(row.get("atr", 1))

    # Strong wick = wick is at least 1.5x body
    if wick_up > body * 1.5 and wick_up > atr * 0.3:
        return True
    if wick_dn > body * 1.5 and wick_dn > atr * 0.3:
        return True
    return False


def _score_setup(trend, sweep, rsi, rejection, row) -> tuple:
    """
    Scores the trade setup from 0.0 to 1.0
    Each condition adds weight.
    """
    score   = 0.0
    reasons = []

    # Trend (required base)
    if trend != 0:
        score += 0.20
        reasons.append(f"Trend:{'bullish' if trend==1 else 'bearish'}")

    # Liquidity sweep (strong signal)
    if sweep:
        score += 0.30
        reasons.append(f"Sweep:{sweep}")

    # RSI confirmation
    if sweep == "bullish_sweep" and rsi < 45:
        score += 0.20
        reasons.append(f"RSI:{rsi:.1f}(oversold)")
    elif sweep == "bearish_sweep" and rsi > 55:
        score += 0.20
        reasons.append(f"RSI:{rsi:.1f}(overbought)")
    elif 35 < rsi < 65:
        score += 0.10
        reasons.append(f"RSI:{rsi:.1f}(neutral)")

    # Rejection candle
    if rejection:
        score += 0.15
        reasons.append("Rejection:candle")

    # Session bonus
    if row.get("in_session", False):
        score += 0.15
        reasons.append("Session:active")

    return score, " | ".join(reasons)


def _get_direction(trend: int, sweep: str) -> str:
    if sweep == "bullish_sweep":
        return "BUY"
    if sweep == "bearish_sweep":
        return "SELL"
    if trend == 1:
        return "BUY"
    if trend == -1:
        return "SELL"
    return "WAIT"


def _calculate_levels(direction: str, entry: float, atr: float) -> tuple:
    from config.settings import ATR_SL_MULTIPLIER, RR_RATIO

    sl_dist  = atr * ATR_SL_MULTIPLIER
    tp1_dist = sl_dist * RR_RATIO
    tp2_dist = sl_dist * (RR_RATIO * 2)

    if direction == "BUY":
        return (
            entry - sl_dist,
            entry + tp1_dist,
            entry + tp2_dist,
        )
    else:
        return (
            entry + sl_dist,
            entry - tp1_dist,
            entry - tp2_dist,
        )


def _calculate_lot(balance: float, entry: float, sl: float) -> float:
    from config.settings import MAX_RISK_PER_TRADE, MAX_LOT_SIZE, MIN_LOT_SIZE

    risk_usd = balance * MAX_RISK_PER_TRADE
    sl_dist  = abs(entry - sl)

    if sl_dist == 0:
        return MIN_LOT_SIZE

    # Gold: 1 lot = 100oz = ~$10 per pip
    pip_value = 10.0
    lot = risk_usd / (sl_dist * pip_value * 10)
    lot = max(MIN_LOT_SIZE, min(lot, MAX_LOT_SIZE))
    return round(lot, 2)


def _wait(reason: str) -> Signal:
    return Signal(
        direction="WAIT", entry=0, sl=0, tp1=0, tp2=0,
        lot=0, rr=0, confidence=0, reason=reason,
    )
