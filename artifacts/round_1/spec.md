# Spec: 50 EMA Bounce-Back Strategy (SOL/USD, daily) — Round 1

## Goal
Test whether buying pullbacks to the 50 EMA inside a confirmed macro uptrend has a
real historical edge on SOL/USD daily data. Paper-only. Honest statistics either way.

## Universe & Data Pipeline
- Pair: SOLUSD, Kraken public OHLC, interval 1440 (daily), HTTPS, no API key.
- The forming candle is dropped (data_feed enforces this already).
- Long-only. One position at a time. No leverage. No live orders, ever.

## Indicators (indicators.py)
- EMA(close, 50) — exponential, span=50, adjust=False; values before bar 50 are NaN.
- SMA(close, 200) — simple rolling mean; values before bar 200 are NaN.

## Entry rule (evaluated on bar close, fills NEXT bar open)
All four conditions must hold on the same bar:
1. Macro uptrend filter: close > SMA200 (and SMA200 is not NaN).
2. Pullback touch: bar low <= EMA50 * 1.03 (within 3% of the EMA).
3. Bounce confirmation: close > EMA50.
4. Bullish close: close > open.

Signal +1 on that bar; the fill happens at the next bar's open (no look-ahead).

## Exit rules
- Trend/EMA break: close < EMA50 → signal -1, fills at next bar open.
- Stop-loss: intrabar fill at min(bar_open, stop_price) where
  stop_price = entry_price * 0.95 (5%).
- Max hold: 30 bars; exit queues a sell at next bar open.
- End of data: force-close at last close for reporting only.

## Risk parameters (risk_manager.py)
- Notional per trade: $1.00 max (paper ceiling; owner's standing speculative cap).
- Stop-loss: 5% below entry.
- Max hold: 30 daily bars.
- Fee model: 0.26% taker per fill, entry and exit both charged.

## Metrics the backtest must report
n_trades, n_stop_loss, n_signal_exits, n_max_hold, n_end_of_data, win_rate,
avg win, avg loss, expectancy per trade, profit factor, total PnL, return %,
max drawdown %, and buy & hold return % over the same window for comparison.

## Acceptance criteria
- AC1: EMA50 matches pandas ewm(span=50, adjust=False) reference post-warmup;
       pre-warmup values are NaN.
- AC2: SMA200 matches pandas rolling(200).mean(); pre-warmup NaN.
- AC3: No signal of any kind before both indicators are valid (warmup safety).
- AC4: Signal +1 fires exactly on bars meeting all four entry conditions
       (property test on synthetic data), never elsewhere.
- AC5: Macro filter blocks entries: a touch+bounce+bullish bar with close <= SMA200
       must NOT fire +1.
- AC6: Signal -1 fires exactly where indicators are valid and close < EMA50.
- AC7: No look-ahead: signals on data truncated at bar i are identical to the
       first i signals computed on the full dataset.
- AC8: Risk manager arithmetic: stop = entry*0.95; max_hold triggers at 30 bars;
       notional clamped to min($1, equity); equity <= 0 → size 0.
- AC9: Backtest accounting: final equity == initial + sum(trade PnL) to 1e-6;
       entries fill at the bar AFTER the signal bar; stop fills at min(open, stop).
- AC10: `--live` CLI flag always raises NotImplementedError; backtest on live
       Kraken daily data completes and prints the full metric set.

## Audit criteria (Reviewer)
No secrets, no live order path, no unbounded loops, stop-loss and sizing enforced
inside the execution loop (not just declared), fills strictly next-bar,
fees included in trade PnL.
