# sol-ema-bounce-back

A 50 EMA bounce-back trading strategy for SOL/USD (daily bars), built through a
Planner → Coder → Tester → Reviewer pipeline. **Paper-only: there is no live
order path and never will be in this codebase.**

## Strategy

Long entries fire on a bar close only when ALL four conditions hold:

1. **Macro uptrend filter:** close > SMA200
2. **Pullback touch:** bar low <= EMA50 × 1.03 (within 3% of the EMA)
3. **Bounce confirmation:** close > EMA50
4. **Bullish close:** close > open

Fills execute at the **next bar's open** (no look-ahead). Exits: close < EMA50
(trend break), 5% stop-loss (intrabar, gap-down fills at the worse price), or
30-bar max hold. Fees modeled at 0.26% per fill.

## Backtest results (Kraken SOLUSD daily, 720 bars, Nov 2024 – Oct 2026)

| Metric | Strategy | Buy & hold |
|---|---|---|
| Return | +0.28% ($1 notional cap) | -46.08% |
| Trades | 8 | — |
| Win rate | 25% | — |
| Profit factor | 2.36 | — |
| Max drawdown | -0.08% | — |

Classic trend-following profile: frequent small losses, two large wins
(+18.5% and +30.1% bounces). **Honest caveats:** 8 trades is a small sample,
one asset, one mostly-bearish regime. This is a regime filter, not proven alpha.
Do not size up on this evidence alone.

## Layout

```
artifacts/round_1/
  spec.md            # strategy specification + acceptance criteria
  code/              # data_feed, indicators, strategy, risk_manager, backtest, main
  tests/test_suite.py  # 24 unit tests (all passing)
  test_report.md     # Tester report with backtest metrics
  review.md          # independent risk & code audit (verdict: approved)
```

## Usage

```bash
pip install pandas requests
python code/main.py --backtest        # backtest on live Kraken daily data
python code/main.py                   # paper readout: what it WOULD do now
python code/main.py --live            # raises: live trading is forbidden
```

Run the test suite from the round directory:

```bash
PYTHONPATH=code python3 -m unittest discover -s tests -v
```

## Risk rules baked into the code

- $1 max notional per trade (paper ceiling)
- 5% stop-loss enforced inside the execution loop
- 30-bar max hold
- Long-only, one position, no leverage, no live orders

Not financial advice. This repository exists to test whether an idea has a
historical edge — the answer so far is "maybe, but the sample is thin."
