"""Time-series momentum: ride symbols that have been going up.

Each bar it ranks symbols by trailing return and holds the positive ones,
rebalancing only when the set of "winners" changes — again, self-timed.
"""

from __future__ import annotations

from ..broker import Order
from ..strategy import Context, Strategy


class Momentum(Strategy):
    """Ride winners: hold symbols with positive trailing return, rebalance on change."""

    name = "momentum"

    def __init__(self, lookback: int = 60, allocation: float = 0.95) -> None:
        self.lookback = lookback
        self.allocation = allocation
        self._held: set[str] = set()

    def _trailing_return(self, context: Context, symbol: str) -> float | None:
        closes = context.closes(symbol, self.lookback + 1)
        if len(closes) <= self.lookback or closes[0] <= 0:
            return None
        return closes[-1] / closes[0] - 1.0

    def decide(self, context: Context) -> list[Order]:
        winners: list[str] = []
        for symbol in context.bars:
            r = self._trailing_return(context, symbol)
            if r is not None and r > 0:
                winners.append(symbol)

        target = set(winners)
        if target == self._held:
            return []  # nothing changed — hold

        orders: list[Order] = []
        # Exit anything no longer a winner.
        for symbol in self._held - target:
            orders += context.order_target_percent(symbol, 0.0)
        # Equal-weight the current winners.
        pct = self.allocation / len(winners) if winners else 0.0
        for symbol in winners:
            orders += context.order_target_percent(symbol, pct)

        self._held = target
        return orders
