"""Tester agent: unit tests + edge cases for every acceptance criterion in the spec.

Run:  PYTHONPATH=code python3 -m unittest discover -s tests -v   (from the round dir)
"""
import io
import json
import unittest
from contextlib import redirect_stdout
from unittest import mock

import numpy as np
import pandas as pd

from backtest import FEE_PCT, run_backtest
from data_feed import parse_kraken_payload
from indicators import ema, sma
from main import main as cli_main
from risk_manager import RiskManager, MAX_NOTIONAL_USD
from strategy import generate_signals


def make_ohlcv(closes, opens=None, lows=None, highs=None, start="2024-01-01", freq="1D"):
    closes = list(closes)
    n = len(closes)
    opens = list(opens) if opens is not None else [c - 0.2 for c in closes]
    lows = list(lows) if lows is not None else [min(o, c) - 0.5 for o, c in zip(opens, closes)]
    highs = list(highs) if highs is not None else [max(o, c) + 0.5 for o, c in zip(opens, closes)]
    idx = pd.date_range(start, periods=n, freq=freq)
    return pd.DataFrame({"open": opens, "high": highs, "low": lows,
                         "close": closes, "volume": [100.0] * n}, index=idx)


def uptrend_with_pullback(n_pre=250, crash=True):
    """Deterministic series: clean rise, one pullback bar at index n_pre, then either
    a crash bar (for stop-loss testing) or continued rise."""
    closes, opens, lows = [], [], []
    for i in range(n_pre):
        c = 100 + 0.4 * i
        closes.append(c)
        opens.append(c - 0.2)
        lows.append(c - 0.5)
    # pullback bar: gap-down open, bullish close, deep touch of the EMA zone
    closes.append(191.0)
    opens.append(190.5)
    lows.append(185.0)
    if crash:
        closes.append(191.5)  # normal bar 251: entry fills at its open (191.3)
        opens.append(191.3)
        lows.append(190.5)
        closes.append(172.0)   # crash bar 252: opens far below the stop
        opens.append(175.0)
        lows.append(170.0)
    else:
        for k in range(1, 40):  # continued rise, no exit
            closes.append(191.0 + 0.5 * k)
            opens.append(191.0 + 0.5 * k - 0.2)
            lows.append(191.0 + 0.5 * k - 0.5)
    return make_ohlcv(closes, opens, lows)


class TestIndicators(unittest.TestCase):
    """AC1, AC2: EMA/SMA math vs pandas reference; warmup NaN; empty input."""

    def test_ema_matches_reference(self):
        rng = np.random.default_rng(11)
        close = pd.Series(rng.normal(100, 5, 300))
        got = ema(close, period=50)
        ref = close.ewm(span=50, adjust=False).mean()
        self.assertTrue(np.allclose(got[50:], ref[50:], atol=1e-9))

    def test_ema_warmup_is_nan(self):
        got = ema(pd.Series(np.linspace(1, 100, 100)), period=50)
        self.assertTrue(got[:49].isna().all())
        self.assertFalse(got[49:].isna().any())

    def test_sma_matches_reference_and_warmup(self):
        rng = np.random.default_rng(13)
        close = pd.Series(rng.normal(50, 3, 300))
        got = sma(close, period=200)
        ref = close.rolling(200).mean()
        self.assertTrue(np.allclose(got, ref, equal_nan=True, atol=1e-12))
        self.assertTrue(got[:199].isna().all())
        self.assertFalse(got[199:].isna().any())

    def test_empty_series_raise(self):
        for fn in (ema, sma):
            with self.assertRaises(ValueError):
                fn(pd.Series([], dtype="float64"), period=10)


class TestStrategy(unittest.TestCase):
    """AC3, AC4, AC5, AC6, AC7: signal semantics, filters, no look-ahead."""

    def _rand_df(self, n=400, seed=5):
        rng = np.random.default_rng(seed)
        steps = rng.normal(0.0005, 0.02, n)
        closes = 100 * np.cumprod(1 + steps)
        opens = closes * (1 + rng.normal(-0.001, 0.008, n))
        lows = np.minimum(opens, closes) * (1 - np.abs(rng.normal(0, 0.01, n)))
        return make_ohlcv(closes, opens=opens, lows=lows)

    def test_no_signals_during_warmup(self):
        sig = generate_signals(uptrend_with_pullback(crash=False))
        self.assertTrue((sig["signal"].iloc[:199] == 0).all())  # AC3

    def test_entry_fires_on_crafted_pullback(self):
        df = uptrend_with_pullback(crash=False)
        sig = generate_signals(df)
        self.assertEqual(int(sig["signal"].iloc[250]), 1)   # AC4: the planted bar fires
        self.assertTrue((sig["signal"].iloc[:250] == 0).all())  # nothing before it

    def test_entry_implies_all_four_conditions(self):
        sig = generate_signals(self._rand_df())
        rows = sig[sig["signal"] == 1]                       # AC4 property
        self.assertTrue((rows["close"] > rows["sma200"]).all())
        self.assertTrue((rows["low"] <= rows["ema50"] * 1.03).all())
        self.assertTrue((rows["close"] > rows["ema50"]).all())
        self.assertTrue((rows["close"] > rows["open"]).all())
        # and no entry anywhere outside the mask
        mask = ((sig["close"] > sig["sma200"]) & (sig["low"] <= sig["ema50"] * 1.03)
                & (sig["close"] > sig["ema50"]) & (sig["close"] > sig["open"]))
        self.assertTrue((mask.to_numpy() == (sig["signal"].to_numpy() == 1)).all())

    def test_macro_filter_blocks_bounce_in_downtrend(self):
        # flat -> decline -> rise with varied dip depths: some bar must meet
        # touch+bounce+bullish while close < SMA200 (macro downtrend).
        closes = [100.0] * 190
        for k in range(1, 41):
            closes.append(100.0 - k)                     # decline to 60
        opens, lows = [], []
        for k in range(1, 26):
            closes.append(60.0 + 2 * k)                   # rise back to 110
        for i, c in enumerate(closes):
            if i < 190:
                opens.append(c)
                lows.append(c - 0.5)
            elif i < 230:
                opens.append(c + 0.5)
                lows.append(c - 1.0)
            else:
                opens.append(c - 1.5)
                lows.append(c - (0.5 + (i % 9)))          # varied dip depths
        sig = generate_signals(make_ohlcv(closes, opens, lows))
        blocked = ((sig["low"] <= sig["ema50"] * 1.03) & (sig["close"] > sig["ema50"])
                   & (sig["close"] > sig["open"]) & (sig["close"] < sig["sma200"]))
        blocked = blocked.fillna(False)
        self.assertTrue(blocked.any(), "test fixture must contain a blocked bounce bar")
        self.assertTrue((sig.loc[blocked, "signal"] == 0).all())  # AC5

    def test_exit_mask_exact(self):
        sig = generate_signals(self._rand_df())             # AC6
        ready = sig["ema50"].notna() & sig["sma200"].notna()
        mask = (ready & (sig["close"] < sig["ema50"])).to_numpy()
        self.assertTrue((mask == (sig["signal"].to_numpy() == -1)).all())

    def test_no_lookahead_truncation_invariance(self):
        df = self._rand_df(seed=21, n=360)                   # AC7
        full = generate_signals(df)["signal"].to_numpy()
        for cut in (len(df) // 2, len(df) - 1):
            trunc = generate_signals(df.iloc[:cut].copy())["signal"].to_numpy()
            self.assertTrue((trunc == full[:cut]).all())


class TestRiskManager(unittest.TestCase):
    """AC8: sizing, stop, max-hold arithmetic."""

    def test_stop_price(self):
        rm = RiskManager()
        self.assertAlmostEqual(rm.stop_price(100.0), 95.0)

    def test_exit_reasons(self):
        rm = RiskManager()
        self.assertEqual(rm.exit_reason(100.0, 94.9, 0), "stop_loss")
        self.assertIsNone(rm.exit_reason(100.0, 95.1, 29))
        self.assertEqual(rm.exit_reason(100.0, 99.0, 30), "max_hold")

    def test_sizing_clamped(self):
        rm = RiskManager()
        self.assertEqual(rm.size_position(0.5), 0.5)
        self.assertEqual(rm.size_position(500.0), MAX_NOTIONAL_USD)
        self.assertEqual(rm.size_position(0.0), 0.0)
        self.assertEqual(rm.size_position(-1.0), 0.0)

    def test_invalid_params_raise(self):
        with self.assertRaises(ValueError):
            RiskManager(stop_loss_pct=0)
        with self.assertRaises(ValueError):
            RiskManager(max_hold_bars=0)


class TestBacktest(unittest.TestCase):
    """AC9: fills, accounting identity, stop behavior."""

    def test_trade_fills_next_bar_open(self):
        df = uptrend_with_pullback(crash=False)
        sig = generate_signals(df)
        metrics = run_backtest(df, initial_equity_usd=100.0,
                               risk=RiskManager(max_notional_usd=10.0))
        self.assertGreaterEqual(metrics["n_trades"], 1)
        t = metrics["trades"][0]
        self.assertEqual(t["entry_time"], df.index[251])       # bar AFTER the signal bar
        self.assertAlmostEqual(t["entry_price"], df["open"].iloc[251], places=6)

    def test_stop_fills_at_worse_of_open_or_stop(self):
        df = uptrend_with_pullback(crash=True)                 # crash bar opens at 175
        metrics = run_backtest(df, initial_equity_usd=100.0,
                               risk=RiskManager(max_notional_usd=10.0))
        stops = [t for t in metrics["trades"] if t["reason"] == "stop_loss"]
        self.assertGreaterEqual(len(stops), 1)
        t = stops[0]
        entry = t["entry_price"]
        stop = entry * 0.95
        self.assertAlmostEqual(t["exit_price"], min(175.0, stop), places=6)

    def test_accounting_identity(self):
        df = self._rand_df(420, seed=31)
        metrics = run_backtest(df, initial_equity_usd=100.0,
                               risk=RiskManager(max_notional_usd=5.0))
        s = sum(t["pnl_usd"] for t in metrics["trades"])
        self.assertAlmostEqual(metrics["final_equity_usd"], 100.0 + s, places=4)
        self.assertEqual(metrics["n_trades"],
                         metrics["n_stop_loss"] + metrics["n_signal_exits"]
                         + metrics["n_max_hold"] + metrics["n_end_of_data"])

    def _rand_df(self, n, seed):
        rng = np.random.default_rng(seed)
        steps = rng.normal(0.0008, 0.025, n)
        closes = 100 * np.cumprod(1 + steps)
        opens = closes * (1 + rng.normal(-0.001, 0.01, n))
        lows = np.minimum(opens, closes) * (1 - np.abs(rng.normal(0, 0.015, n)))
        return make_ohlcv(closes, opens=opens, lows=lows)

    def test_insufficient_history_raises(self):
        with self.assertRaises(ValueError):
            run_backtest(make_ohlcv([100.0] * 100))


class TestCLI(unittest.TestCase):
    """AC10: --live refuses; --backtest reports the full metric set (network mocked)."""

    def test_live_raises(self):
        with self.assertRaises(NotImplementedError):
            cli_main(["--live"])

    def test_backtest_output_keys(self):
        df = uptrend_with_pullback(crash=False)
        with mock.patch("main.fetch_ohlcv", return_value=df):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli_main(["--backtest"])
            self.assertEqual(rc, 0)
            out = json.loads(buf.getvalue())
        for key in ("n_trades", "win_rate", "expectancy_usd", "profit_factor",
                    "return_pct", "max_drawdown_pct", "buy_hold_return_pct"):
            self.assertIn(key, out)


class TestDataFeed(unittest.TestCase):
    """Edge cases: malformed payloads never silently return empty frames."""

    def test_error_payload_raises(self):
        with self.assertRaises(RuntimeError):
            parse_kraken_payload({"error": ["EQuery: Unknown asset pair"],
                                  "result": {"X": []}})

    def test_missing_result_raises(self):
        with self.assertRaises(ValueError):
            parse_kraken_payload({"stuff": 1})

    def test_empty_candles_raise(self):
        with self.assertRaises(ValueError):
            parse_kraken_payload({"result": {"X": []}})

    def test_valid_payload_parses_and_drops_forming_candle(self):
        payload = {"result": {"SOLUSD": [
            [1700000000, "1", "2", "0.5", "1.5", "1", "10", "5"],
            [1700008640, "1.5", "2", "1", "2", "1.7", "10", "5"],
        ]}}
        df = parse_kraken_payload(payload, now=1700090000)
        self.assertEqual(len(df), 2)
        self.assertEqual(list(df.columns), ["open", "high", "low", "close", "volume"])


if __name__ == "__main__":
    unittest.main()
