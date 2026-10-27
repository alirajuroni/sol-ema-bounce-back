# Test Report — Round 1 (50 EMA bounce-back, SOL/USD daily)

## Unit suite: 24 tests — ALL PASS
| Criterion | Test | Result |
|---|---|---|
| AC1 EMA math | test_ema_matches_reference, test_ema_warmup_is_nan | PASS |
| AC2 SMA math | test_sma_matches_reference_and_warmup | PASS |
| AC3 warmup safety | test_no_signals_during_warmup | PASS |
| AC4 entry mask exact | test_entry_fires_on_crafted_pullback, test_entry_implies_all_four_conditions | PASS |
| AC5 macro filter blocks | test_macro_filter_blocks_bounce_in_downtrend | PASS |
| AC6 exit mask exact | test_exit_mask_exact | PASS |
| AC7 no look-ahead | test_no_lookahead_truncation_invariance | PASS |
| AC8 risk arithmetic | TestRiskManager (4 tests) | PASS |
| AC9 fills + accounting | test_trade_fills_next_bar_open, test_stop_fills_at_worse_of_open_or_stop, test_accounting_identity | PASS |
| AC10 CLI + data edges | TestCLI, TestDataFeed (6 tests) | PASS |

No stack traces. No FAIL/ERROR.

## Live-data backtest (Kraken SOLUSD, daily, 720 bars: 2024-11-06 → 2026-10-26, 520 tradable post-warmup)

| Metric | Value |
|---|---|
| Trades | 8 (5 signal exits, 1 stop-loss, 2 max-hold) |
| Win rate | 25.0% |
| Avg win / avg loss | +0.240 / -0.034 USD |
| Expectancy per trade | +0.0346 USD |
| Profit factor | 2.36 |
| Total PnL / return | +0.277 USD / +0.28% (on $100 equity, $1 notional) |
| Max drawdown | -0.08% |
| Buy & hold same window | -46.08% |

Trade log shape: 6 small losses (stop + quick EMA breaks) and 2 large winners
(2025-08-07→09-07 +18.5%, 2026-08-20→09-20 +30.1%) — classic trend-following
profile: frequent small losses, rare large bounces captured.

## Honest caveats
- 8 trades is a statistically small sample; expectancy positive but wide
  confidence intervals. Not tradeable evidence on its own.
- The +0.28% vs -46.08% comparison reflects the $1 notional cap (capital mostly
  in cash); it is a regime filter result, not alpha proof.
- Single asset, single regime (mostly bearish window). No out-of-sample split.

Verdict: PASS — code correct, results honest.
