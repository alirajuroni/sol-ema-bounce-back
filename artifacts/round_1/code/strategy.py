"""Signal generation: 50 EMA bounce-back inside a macro uptrend, long-only.

Signal semantics per bar (evaluated on that bar's close):
  +1 -> enter long (fill at NEXT bar open — no lookahead)
   0 -> no action
  -1 -> exit open long (fill at next bar open)

Entry fires on a bar ONLY when all four conditions hold:
  1. close > SMA200          (macro uptrend filter)
  2. low <= EMA50 * 1.03     (pullback touched the EMA zone)
  3. close > EMA50           (bounce confirmation)
  4. close > open            (bullish close)

Exit: close < EMA50 once indicators are valid.
A signal at bar i uses only data up to and including bar i.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from indicators import ema, sma


def generate_signals(df: pd.DataFrame, ema_period: int = 50,
                     sma_period: int = 200, touch_pct: float = 0.03) -> pd.DataFrame:
    """Add ema50/sma200 and `signal` columns to an OHLCV DataFrame."""
    required = {"open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"DataFrame missing required columns: {missing}")
    if not 0 < touch_pct < 1:
        raise ValueError("touch_pct must be in (0, 1)")

    out = df.copy()
    # Positional arrays (indicators reset the index): never re-align masks.
    ema_v = ema(out["close"], ema_period).to_numpy()
    sma_v = sma(out["close"], sma_period).to_numpy()
    out["ema50"], out["sma200"] = ema_v, sma_v

    open_v = out["open"].to_numpy()
    low_v = out["low"].to_numpy()
    close_v = out["close"].to_numpy()
    sig = np.zeros(len(out), dtype="int64")

    ready = np.isfinite(ema_v) & np.isfinite(sma_v)          # AC3: warmup safety
    entry_mask = (
        ready
        & (close_v > sma_v)                                  # 1. macro uptrend
        & (low_v <= ema_v * (1.0 + touch_pct))                # 2. pullback touch
        & (close_v > ema_v)                                  # 3. bounce
        & (close_v > open_v)                                 # 4. bullish close
    )
    exit_mask = ready & (close_v < ema_v)                     # trend/EMA break

    sig[entry_mask] = 1
    sig[exit_mask] = -1
    out["signal"] = sig
    return out
