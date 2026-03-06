"""
DATA ENGINE
Fetches and prepares XAUUSD market data.
Works with MT5 (live) or yfinance (free demo).
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone
import logging

log = logging.getLogger("DataEngine")


# ─────────────────────────────────────────────
#  Try MT5 first, fall back to yfinance
# ─────────────────────────────────────────────
def get_data(bars: int = 300, source: str = "auto") -> pd.DataFrame:
    """
    Fetch XAUUSD candles.
    Returns a clean DataFrame with OHLCV + indicators.
    """
    # Force yfinance because MT5 terminal is stuck on 3312
    if source == "auto":
        return _fetch_yfinance(bars)

    if source == "mt5":
        return _fetch_mt5(bars)

    return _fetch_yfinance(bars)


def _fetch_mt5(bars: int) -> pd.DataFrame:
    import MetaTrader5 as mt5
    from config.settings import SYMBOL, TIMEFRAME

    tf_map = {
        "M1":  mt5.TIMEFRAME_M1,  "M5":  mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15, "H1":  mt5.TIMEFRAME_H1,
        "H4":  mt5.TIMEFRAME_H4,  "D1":  mt5.TIMEFRAME_D1,
    }
    tf = tf_map.get(TIMEFRAME, mt5.TIMEFRAME_M15)

    if not mt5.initialize():
        raise ConnectionError("MT5 init failed")

    rates = mt5.copy_rates_from_pos(SYMBOL, tf, 0, bars)
    if rates is None or len(rates) == 0:
        raise ValueError("No data returned from MT5")

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.rename(columns={"tick_volume": "volume"}, inplace=True)
    df = df[["time", "open", "high", "low", "close", "volume"]]
    log.info(f"MT5: fetched {len(df)} candles")
    return _add_indicators(df)


import time
_cache = {"df": None, "time": 0}

def _fetch_yfinance(bars: int) -> pd.DataFrame:
    import yfinance as yf
    
    # Cache for 60 seconds to prevent dashboard timeouts & rate limits
    if _cache["df"] is not None and time.time() - _cache["time"] < 60:
        return _cache["df"]

    raw = yf.download("GC=F", period="60d", interval="15m", progress=False)
    if raw.empty:
        raise ValueError("yfinance returned empty data")

    df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = ["open", "high", "low", "close", "volume"]
    df.index.name = "time"
    df.reset_index(inplace=True)
    df = df.tail(bars).reset_index(drop=True)
    
    result = _add_indicators(df)
    _cache["df"] = result
    _cache["time"] = time.time()
    log.info(f"yfinance: fetched and cached {len(result)} candles")
    return result


# ─────────────────────────────────────────────
#  Indicator Engine
# ─────────────────────────────────────────────
def _add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    from config.settings import EMA_FAST, EMA_SLOW, RSI_PERIOD, ATR_PERIOD

    c = df["close"]
    h = df["high"]
    l = df["low"]

    # Trend
    df["ema_fast"]  = c.ewm(span=EMA_FAST,  adjust=False).mean()
    df["ema_slow"]  = c.ewm(span=EMA_SLOW,  adjust=False).mean()
    df["trend"]     = np.where(df["ema_fast"] > df["ema_slow"], 1, -1)

    # Momentum
    df["rsi"]       = _rsi(c, RSI_PERIOD)

    # Volatility
    df["atr"]       = _atr(h, l, c, ATR_PERIOD)

    # Liquidity zones
    df["prev_high"] = h.shift(1).rolling(5).max()
    df["prev_low"]  = l.shift(1).rolling(5).min()

    # Candle body
    df["body"]      = abs(c - df["open"])
    df["wick_up"]   = h - df[["open", "close"]].max(axis=1)
    df["wick_down"] = df[["open", "close"]].min(axis=1) - l

    # Session flag
    df["in_session"] = df["time"].apply(_in_session) if "time" in df.columns else True

    df.dropna(inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / (loss + 1e-10)
    return 100 - (100 / (1 + rs))


def _atr(high, low, close, period):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _in_session(dt) -> bool:
    from config.settings import SESSIONS
    try:
        t = dt.strftime("%H:%M") if hasattr(dt, "strftime") else "08:00"
        for s in SESSIONS.values():
            if s["start"] <= t <= s["end"]:
                return True
    except Exception:
        pass
    return False


def get_prev_day_levels(df: pd.DataFrame) -> dict:
    """Returns previous day high/low for liquidity detection."""
    df["date"] = pd.to_datetime(df["time"]).dt.date
    today      = df["date"].iloc[-1]
    yesterday  = df[df["date"] < today]
    if yesterday.empty:
        return {"pdh": None, "pdl": None}
    return {
        "pdh": yesterday["high"].max(),
        "pdl": yesterday["low"].min(),
    }
