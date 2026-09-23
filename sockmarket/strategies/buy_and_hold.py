"""The control. If a clever brain can't beat this, the cleverness isn't paying."""

from __future__ import annotations

from ..strategy import Context, Strategy
from ..broker import Order


class BuyAndHold(Strategy):
    """Buy an equal-weight basket on the first bar each symbol appears, then hold."""

    name = "buy_and_hold"

    def __init__(self) -> None:
        self._bought: set[str] = set()

    def decide(self, context: Context) -> list[Order]:
        symbols = list(context.bars)
        pct = 1.0 / len(symbols) if symbols else 0.0
        orders: list[Order] = []
        for symbol in symbols:
            if symbol not in self._bought:
                orders += context.order_target_percent(symbol, pct)
                self._bought.add(symbol)
        return orders
