"""Autonomous trend follower: trades only when its own signal fires.

This is the clearest demonstration of "trade whenever it wants" — most bars it
returns an empty list (hold). It acts only when the fast moving average crosses
the slow one, which can be any day, or many days apart.
"""

from __future__ import annotations

from ..broker import Order
from ..strategy import Context, Strategy


def _sma(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


class SmaCrossover(Strategy):
    """Trend follower: buy on a fast/slow moving-average golden cross, exit on death cross."""

    name = "sma_crossover"

    def __init__(self, fast: int = 20, slow: int = 50, allocation: float = 0.95) -> None:
        if fast >= slow:
            raise ValueError("fast window must be shorter than slow window")
        self.fast = fast
        self.slow = slow
        self.allocation = allocation
        self._above: dict[str, bool] = {}

    def decide(self, context: Context) -> list[Order]:
        orders: list[Order] = []
        symbols = list(context.bars)
        per_symbol = self.allocation / len(symbols) if symbols else 0.0

        for symbol in symbols:
            closes = context.closes(symbol)
            fast = _sma(closes, self.fast)
            slow = _sma(closes, self.slow)
            if fast is None or slow is None:
                continue

            now_above = fast > slow
            was_above = self._above.get(symbol)
            self._above[symbol] = now_above

            if was_above is None:
                continue  # need a prior state to detect a *crossing*
            if now_above and not was_above:
                # Golden cross -> go long.
                orders += context.order_target_percent(symbol, per_symbol)
            elif was_above and not now_above:
                # Death cross -> exit.
                orders += context.order_target_percent(symbol, 0.0)
        return orders
