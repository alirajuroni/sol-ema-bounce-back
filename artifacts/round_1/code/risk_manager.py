"""Position sizing and loss limits. Paper-first posture, tiny notional.

The default notional is $1, matching the owner's standing ceiling for
speculative Solana trades. This module owns ALL risk arithmetic so the
reviewer has exactly one place to audit.
"""
from __future__ import annotations

MAX_NOTIONAL_USD = 1.0
STOP_LOSS_PCT = 0.05
MAX_HOLD_BARS = 30


class RiskManager:
    def __init__(self, max_notional_usd: float = MAX_NOTIONAL_USD,
                 stop_loss_pct: float = STOP_LOSS_PCT,
                 max_hold_bars: int = MAX_HOLD_BARS):
        if max_notional_usd <= 0:
            raise ValueError("max_notional_usd must be positive")
        if not 0 < stop_loss_pct < 1:
            raise ValueError("stop_loss_pct must be in (0, 1)")
        if max_hold_bars < 1:
            raise ValueError("max_hold_bars must be >= 1")
        self.max_notional_usd = max_notional_usd
        self.stop_loss_pct = stop_loss_pct
        self.max_hold_bars = max_hold_bars

    def size_position(self, equity_usd: float) -> float:
        """Fixed notional clamped to available equity; 0 when equity <= 0."""
        if equity_usd <= 0:
            return 0.0
        return min(self.max_notional_usd, equity_usd)

    def stop_price(self, entry_price: float) -> float:
        if entry_price <= 0:
            raise ValueError("entry_price must be positive")
        return entry_price * (1.0 - self.stop_loss_pct)

    def exit_reason(self, entry_price: float, bar_low: float, bars_held: int) -> str | None:
        """Return 'stop_loss' or 'max_hold' when an open position must be closed."""
        if bar_low <= self.stop_price(entry_price):
            return "stop_loss"
        if bars_held >= self.max_hold_bars:
            return "max_hold"
        return None
