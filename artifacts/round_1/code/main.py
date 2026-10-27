"""CLI entry point. Paper mode only.

`--live` is intentionally unimplemented and raises: per the spec, no live
order execution exists in this codebase. The paper readout prints what the
strategy WOULD do; it never sends anything anywhere.
"""
from __future__ import annotations

import argparse
import json
import sys

from backtest import run_backtest
from data_feed import fetch_ohlcv
from risk_manager import RiskManager
from strategy import generate_signals

LIVE_TRADING_ENABLED = False  # spec: live trading is forbidden


def paper_readout(pair: str, interval: int) -> str:
    df = fetch_ohlcv(pair=pair, interval=interval)
    sig = generate_signals(df)
    last = sig.iloc[-1]

    def _n(v):
        return None if v != v else round(float(v), 4)  # NaN-safe

    return json.dumps({
        "mode": "paper",
        "pair": pair,
        "bar_time": str(sig.index[-1]),
        "close": round(float(last["close"]), 4),
        "ema50": _n(last["ema50"]),
        "sma200": _n(last["sma200"]),
        "uptrend_filter": bool(last["close"] > last["sma200"]) if last["sma200"] == last["sma200"] else None,
        "signal": int(last["signal"]),
        "action": {1: "would enter long (paper)", -1: "would exit (paper)",
                   0: "no action"}[int(last["signal"])],
        "risk": {"notional_usd": RiskManager().max_notional_usd,
                 "stop_loss_pct": RiskManager().stop_loss_pct,
                 "max_hold_bars": RiskManager().max_hold_bars},
    }, indent=2)


def main(argv=None):
    ap = argparse.ArgumentParser(description="SOL/USD 50 EMA bounce-back (paper only)")
    ap.add_argument("--pair", default="SOLUSD")
    ap.add_argument("--interval", type=int, default=1440, help="minutes (1440 = daily)")
    ap.add_argument("--backtest", action="store_true", help="run backtest on fetched history")
    ap.add_argument("--live", action="store_true", help="NOT IMPLEMENTED — always refuses")
    args = ap.parse_args(argv)

    if args.live:
        raise NotImplementedError(
            "Live trading is forbidden by the strategy spec. This codebase is "
            "paper-only; there is no live order path to enable.")

    if args.backtest:
        df = fetch_ohlcv(pair=args.pair, interval=args.interval)
        metrics = run_backtest(df)
        metrics.pop("trades")  # keep CLI output compact
        print(json.dumps(metrics, indent=2))
        return 0

    print(paper_readout(args.pair, args.interval))
    return 0


if __name__ == "__main__":
    sys.exit(main())
