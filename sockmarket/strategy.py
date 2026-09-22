"""The strategy interface — the bot's "brain".

A strategy sees the market on every bar and decides what to do. Doing nothing is
a first-class choice: return an empty list to hold. That is what lets the bot
"trade whenever it wants" instead of on a fixed schedule.

To build your own brain, subclass ``Strategy`` and implement ``decide``.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from .broker import Order
from .market import Bar
from .portfolio import Portfolio


@dataclass
class Context:
    """Everything a strategy is allowed to see when it decides.

    Crucially, ``history`` contains bars up to *and including* the current bar
    and nothing after it, so a strategy physically cannot peek into the future.
    """

    date: dt.date
    bars: dict[str, Bar]  # current bar per symbol on this date
    history: dict[str, list[Bar]]  # full history per symbol, oldest first
    portfolio: Portfolio

    def price(self, symbol: str) -> float | None:
        bar = self.bars.get(symbol)
        return bar.close if bar else None

    def closes(self, symbol: str, lookback: int | None = None) -> list[float]:
        """Recent closing prices for ``symbol``, oldest first."""
        hist = self.history.get(symbol, [])
        closes = [b.close for b in hist]
        return closes[-lookback:] if lookback else closes

    def position(self, symbol: str) -> float:
        return self.portfolio.quantity(symbol)

    def order_target_percent(self, symbol: str, pct: float) -> list[Order]:
        """Build order(s) to move ``symbol`` toward ``pct`` of total equity.

        ``pct`` is 0..1. This is a convenience so a brain can say "put 50% of the
        book in SOCK" without doing the share math itself.
        """
        price = self.price(symbol)
        if not price or price <= 0:
            return []
        equity = self.portfolio.equity({s: b.close for s, b in self.bars.items()})
        target_value = max(0.0, pct) * equity
        target_qty = target_value / price
        delta = target_qty - self.position(symbol)
        if abs(delta * price) < 1e-6:
            return []
        if delta > 0:
            return [Order(symbol, "buy", delta, reason=f"target {pct:.0%}")]
        return [Order(symbol, "sell", -delta, reason=f"target {pct:.0%}")]


class Strategy:
    """Base class for all trading brains."""

    name: str = "strategy"

    def on_start(self, context: Context) -> None:
        """Optional hook called once before the first bar."""

    def decide(self, context: Context) -> list[Order]:
        """Return the orders to submit on this bar. Empty list = hold.

        Subclasses must override this.
        """
        raise NotImplementedError

    def on_finish(self, context: Context) -> None:
        """Optional hook called once after the last bar."""
