"""Indicator math only. Pure functions, no I/O, no strategy knowledge."""
from __future__ import annotations

import pandas as pd


def ema(close, period: int = 50):
    """Exponential moving average, span=period, adjust=False.

    Pre-warmup values (first period-1 bars) are forced to NaN so callers can
    treat NaN as 'not ready'. Raises on empty input or period < 2.
    """
    if period < 2:
        raise ValueError("period must be >= 2")
    close = pd.Series(close, dtype="float64").reset_index(drop=True)
    if len(close) == 0:
        raise ValueError("close series is empty")
    out = close.ewm(span=period, adjust=False).mean()
    out[: period - 1] = float("nan")
    return out


def sma(close, period: int = 200):
    """Simple moving average. First period-1 values are NaN. Raises on empty input."""
    if period < 2:
        raise ValueError("period must be >= 2")
    close = pd.Series(close, dtype="float64").reset_index(drop=True)
    if len(close) == 0:
        raise ValueError("close series is empty")
    return close.rolling(period, min_periods=period).mean()
