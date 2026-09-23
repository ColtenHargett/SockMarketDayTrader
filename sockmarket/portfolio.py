"""The fake-money accounting engine: cash, positions, and profit/loss.

The ``Portfolio`` never touches the market itself. It just records what happens
when trades fill, tracks average cost so realized P&L is meaningful, and can
mark itself to market given the latest prices.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass
class Position:
    quantity: float = 0.0
    avg_cost: float = 0.0  # average cost per share of the shares currently held


@dataclass
class Trade:
    date: dt.date
    symbol: str
    side: str  # "buy" or "sell"
    quantity: float
    price: float
    commission: float
    realized_pnl: float  # profit/loss booked by this fill (nonzero only on sells)


@dataclass
class Portfolio:
    """Cash + open positions, updated as trades fill."""

    starting_cash: float = 100_000.0
    cash: float = field(init=False)
    positions: dict[str, Position] = field(default_factory=dict)
    trades: list[Trade] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.cash = self.starting_cash

    def quantity(self, symbol: str) -> float:
        pos = self.positions.get(symbol)
        return pos.quantity if pos else 0.0

    def apply_fill(
        self,
        date: dt.date,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        commission: float = 0.0,
    ) -> Trade:
        """Record a filled buy or sell, updating cash, position, and P&L."""
        if quantity <= 0:
            raise ValueError("fill quantity must be positive")
        pos = self.positions.setdefault(symbol, Position())
        realized = 0.0

        if side == "buy":
            self.cash -= quantity * price + commission
            new_qty = pos.quantity + quantity
            # Weighted-average cost of the shares now held.
            pos.avg_cost = (pos.avg_cost * pos.quantity + price * quantity) / new_qty
            pos.quantity = new_qty
        elif side == "sell":
            if quantity > pos.quantity + 1e-9:
                raise ValueError(
                    f"cannot sell {quantity} of {symbol}; only {pos.quantity} held "
                    "(short selling is not supported)"
                )
            realized = (price - pos.avg_cost) * quantity - commission
            self.cash += quantity * price - commission
            pos.quantity -= quantity
            if pos.quantity <= 1e-9:
                pos.quantity = 0.0
                pos.avg_cost = 0.0
        else:
            raise ValueError(f"unknown side: {side!r}")

        trade = Trade(date, symbol, side, quantity, price, commission, realized)
        self.trades.append(trade)
        return trade

    def market_value(self, prices: dict[str, float]) -> float:
        """Value of open positions at the given prices."""
        total = 0.0
        for symbol, pos in self.positions.items():
            if pos.quantity and symbol in prices:
                total += pos.quantity * prices[symbol]
        return total

    def equity(self, prices: dict[str, float]) -> float:
        """Total account value = cash + marked-to-market positions."""
        return self.cash + self.market_value(prices)

    @property
    def realized_pnl(self) -> float:
        return sum(t.realized_pnl for t in self.trades)
