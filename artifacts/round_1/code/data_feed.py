"""Data ingestion: public Kraken OHLCV. Read-only, keyless, HTTPS.

Parsing is separated from HTTP so the tester can exercise payload edge cases
(empty candles, API error arrays, forming-candle drop) without network access.
"""
from __future__ import annotations

import time

import pandas as pd
import requests

KRAKEN_OHLC_URL = "https://api.kraken.com/0/public/OHLC"
COLUMNS = ["time", "open", "high", "low", "close", "vwap", "volume", "count"]


def parse_kraken_payload(payload: dict, now: float | None = None) -> pd.DataFrame:
    """Convert a Kraken OHLC JSON payload into a clean OHLCV DataFrame.

    Drops the still-forming current candle: any candle whose timestamp is within
    one interval of `now` cannot be trusted for backtests.
    Raises ValueError/RuntimeError on empty or error payloads — never silently
    returns an empty frame.
    """
    if not isinstance(payload, dict) or "result" not in payload:
        raise ValueError("Malformed Kraken payload: missing 'result'")
    if payload.get("error"):
        raise RuntimeError(f"Kraken API error: {payload['error']}")

    result = payload["result"]
    series_key = next((k for k in result if k != "last"), None)
    if series_key is None or not result[series_key]:
        raise ValueError("No candles returned")

    df = pd.DataFrame(result[series_key], columns=COLUMNS)
    df = df[["time", "open", "high", "low", "close", "volume"]].astype(float)
    if (df["close"] <= 0).any() or df["volume"].isna().any():
        raise ValueError("Malformed candles: non-positive close or NaN volume")

    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df.set_index("time").sort_index()

    # Drop the forming candle: timestamp within one interval of now.
    now = time.time() if now is None else now
    interval = df.index.to_series().diff().dropna().min()
    if pd.notna(interval):
        df = df[df.index <= pd.Timestamp(now, unit="s") - interval]
    return df


def fetch_ohlcv(pair: str = "SOLUSD", interval: int = 60, timeout: int = 15) -> pd.DataFrame:
    """Fetch OHLCV candles for `pair` at `interval` minutes from Kraken."""
    resp = requests.get(KRAKEN_OHLC_URL, params={"pair": pair, "interval": interval},
                        timeout=timeout)
    resp.raise_for_status()
    return parse_kraken_payload(resp.json())
