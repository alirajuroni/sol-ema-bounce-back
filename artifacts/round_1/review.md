# Review — Round 1 (independent audit)

## Secrets scan
No API keys, tokens, or credentials anywhere. Kraken public endpoint, keyless HTTPS. PASS.

## Look-ahead bias
- Signals use only data up to and including the current bar's close.
- Fills execute at the NEXT bar's open (`pending` order pattern in backtest.py).
- Truncation-invariance test (AC7) proves signals are unaffected by future data.
- EMA/SMA warmup NaN handling verified. PASS.

## Risk enforcement in the execution path
- Stop-loss is checked INSIDE the position-management step of the loop via
  `risk.exit_reason(entry_price, bar_low, bars_held)`, with gap-down fills at
  min(open, stop) — verified by unit test.
- Notional clamped to min($1, equity) at fill time; equity <= 0 → size 0.
- Max-hold queues an exit that fills at next bar open (no same-bar peeking).
PASS.

## Unbounded loops / live path
- Single finite for-loop over the dataframe; no while loops without counters.
- `--live` raises NotImplementedError; no order-execution code exists at all.
PASS.

## Error handling
- Kraken payload parser raises on error payloads, empty candles, malformed data;
  drops the forming candle. Network failures raise, never silently empty.
PASS.

## Findings
None blocking. Minor observation: buy-and-hold comparison starts at bar 0
(includes warmup period) — acceptable since both legs use the full window.

## Verdict: approved
Paper-only, risk-capped, no look-ahead, contract artifacts complete.
