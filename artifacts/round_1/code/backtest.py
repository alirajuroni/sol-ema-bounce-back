"""Event-loop backtest. Long-only, one position, next-bar-open fills.

Fill rules (per spec):
  - Signal entries/exits fill at the NEXT bar's open (no lookahead).
  - Stop-loss fills intrabar at min(open, stop) — gap-down opens fill at the
    (worse) open, never better than the stop.
  - Max-hold exits queue a sell and fill at the next bar's open.

Accounting: both entry and exit fees are folded into the trade's PnL, so
final equity == initial equity + sum(trade PnL) exactly.
"""
from __future__ import annotations

import pandas as pd

from risk_manager import RiskManager
from strategy import generate_signals

FEE_PCT = 0.0026  # taker fee approximation per fill


def run_backtest(df: pd.DataFrame, initial_equity_usd: float = 100.0,
                 risk: RiskManager | None = None, ema_period: int = 50,
                 sma_period: int = 200, touch_pct: float = 0.03) -> dict:
    if initial_equity_usd <= 0:
        raise ValueError("initial_equity_usd must be positive")
    if len(df) < sma_period + 2:
        raise ValueError(f"insufficient history: {len(df)} bars < sma_period {sma_period} + 2")
    risk = risk or RiskManager()

    sig_df = generate_signals(df, ema_period, sma_period, touch_pct)
    opens = sig_df["open"].to_numpy()
    lows = sig_df["low"].to_numpy()
    closes = sig_df["close"].to_numpy()
    signals = sig_df["signal"].to_numpy()
    times = sig_df.index

    equity = initial_equity_usd
    trades: list[dict] = []
    equity_curve: list[float] = [equity]

    position: dict | None = None      # {"qty","entry_price","entry_time","entry_i","entry_fee"}
    pending: tuple | None = None      # ("buy", None) | ("sell", reason)

    for i in range(len(sig_df)):
        # 1. Execute the pending order at this bar's open.
        if pending is not None and pending[0] == "buy" and position is None:
            notional = risk.size_position(equity)
            if notional > 0 and opens[i] > 0:
                position = {"qty": notional / opens[i], "entry_price": opens[i],
                            "entry_time": times[i], "entry_i": i,
                            "entry_fee": notional * FEE_PCT}
        elif pending is not None and pending[0] == "sell" and position is not None:
            equity += _close_position(position, opens[i], trades, pending[1], times[i])
            position = None
        pending = None

        # 2. Manage the open position (stop enforced INSIDE the execution path).
        if position is not None:
            bars_held = i - position["entry_i"]
            reason = risk.exit_reason(position["entry_price"], lows[i], bars_held)
            if reason == "stop_loss":
                stop = risk.stop_price(position["entry_price"])
                fill = min(opens[i], stop)  # gap-down opens fill worse than stop
                equity += _close_position(position, fill, trades, "stop_loss", times[i])
                position = None
            elif reason == "max_hold" and pending is None:
                pending = ("sell", "max_hold")  # spec: fills at next bar open

        # 3. Look at this bar's close and queue an order for the next open.
        if position is None:
            if signals[i] == 1:
                pending = ("buy", None)
        elif signals[i] == -1 and pending is None:
            pending = ("sell", "signal")

        equity_curve.append(equity)

    # An open position at data end is force-closed at the last close for reporting.
    if position is not None:
        equity += _close_position(position, closes[-1], trades, "end_of_data", times[-1])

    return _metrics(trades, equity_curve, initial_equity_usd, closes)


def _close_position(position: dict, fill_price: float, trades: list,
                    reason: str, exit_time) -> float:
    """Realized PnL net of BOTH fills' fees; returns the delta to apply to equity."""
    gross = position["qty"] * (fill_price - position["entry_price"])
    exit_fee = position["qty"] * fill_price * FEE_PCT
    pnl = gross - position["entry_fee"] - exit_fee
    trades.append({
        "entry_time": position["entry_time"], "exit_time": exit_time,
        "entry_price": round(position["entry_price"], 6), "exit_price": round(fill_price, 6),
        "qty": position["qty"], "pnl_usd": round(pnl, 6), "reason": reason,
    })
    return pnl


def _metrics(trades: list, equity_curve: list, initial: float, closes) -> dict:
    curve = pd.Series(equity_curve)
    running_max = curve.cummax()
    drawdown = (curve - running_max) / running_max
    wins = [t for t in trades if t["pnl_usd"] > 0]
    losses = [t for t in trades if t["pnl_usd"] <= 0]
    gross_win = sum(t["pnl_usd"] for t in wins)
    gross_loss = abs(sum(t["pnl_usd"] for t in losses))
    buy_hold = (closes[-1] / closes[0] - 1) * 100 if len(closes) and closes[0] > 0 else None
    return {
        "n_trades": len(trades),
        "n_stop_loss": sum(1 for t in trades if t["reason"] == "stop_loss"),
        "n_signal_exits": sum(1 for t in trades if t["reason"] == "signal"),
        "n_max_hold": sum(1 for t in trades if t["reason"] == "max_hold"),
        "n_end_of_data": sum(1 for t in trades if t["reason"] == "end_of_data"),
        "win_rate": round(len(wins) / len(trades), 4) if trades else None,
        "avg_win_usd": round(gross_win / len(wins), 6) if wins else None,
        "avg_loss_usd": round(-gross_loss / len(losses), 6) if losses else None,
        "expectancy_usd": round((gross_win - gross_loss) / len(trades), 6) if trades else None,
        "profit_factor": round(gross_win / gross_loss, 4) if gross_loss > 0 else None,
        "total_pnl_usd": round(curve.iloc[-1] - initial, 6),
        "return_pct": round((curve.iloc[-1] / initial - 1) * 100, 4),
        "max_drawdown_pct": round(drawdown.min() * 100, 4),
        "buy_hold_return_pct": round(buy_hold, 4) if buy_hold is not None else None,
        "final_equity_usd": round(curve.iloc[-1], 6),
        "trades": trades,
    }
