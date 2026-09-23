"""Mean reversion: buy dips, sell rips, using a z-score of price vs its average.

Buys when price falls far enough below its recent mean, exits when it snaps back.
"""

from __future__ import annotations

import math

from ..broker import Order
from ..strategy import Context, Strategy


class MeanReversion(Strategy):
    """Buy dips, sell rips: enter when price is a z-score below its mean, exit on snap-back."""

    name = "mean_reversion"

    def __init__(
        self,
        window: int = 20,
        entry_z: float = -1.0,
        exit_z: float = 0.0,
        allocation: float = 0.95,
    ) -> None:
        self.window = window
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.allocation = allocation

    def _zscore(self, context: Context, symbol: str) -> float | None:
        closes = context.closes(symbol, self.window)
        if len(closes) < self.window:
            return None
        mean = sum(closes) / len(closes)
        var = sum((c - mean) ** 2 for c in closes) / len(closes)
        std = math.sqrt(var)
        if std == 0:
            return None
        return (closes[-1] - mean) / std

    def decide(self, context: Context) -> list[Order]:
        orders: list[Order] = []
        symbols = list(context.bars)
        per_symbol = self.allocation / len(symbols) if symbols else 0.0

        for symbol in symbols:
            z = self._zscore(context, symbol)
            if z is None:
                continue
            holding = context.position(symbol) > 0
            if not holding and z <= self.entry_z:
                orders += context.order_target_percent(symbol, per_symbol)  # buy the dip
            elif holding and z >= self.exit_z:
                orders += context.order_target_percent(symbol, 0.0)  # take profit
        return orders
