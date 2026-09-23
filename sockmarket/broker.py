"""The paper broker: turns Orders into fills against the portfolio.

This is where "fake money" stays honest. Orders fill at the bar price plus
configurable slippage and commission, and the broker refuses trades the account
can't afford — the same guardrails a real broker would impose.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from .portfolio import Portfolio, Trade


@dataclass
class Order:
    """A request to trade. Quantity is in shares; use ``target_weight`` helpers
    on the strategy context if you'd rather size by portfolio fraction."""

    symbol: str
    side: str  # "buy" or "sell"
    quantity: float
    reason: str = ""  # optional note, shown in logs — handy for debugging a brain

    def __post_init__(self) -> None:
        if self.side not in ("buy", "sell"):
            raise ValueError(f"order side must be 'buy' or 'sell', got {self.side!r}")
        if self.quantity <= 0:
            raise ValueError("order quantity must be positive")


@dataclass
class PaperBroker:
    """Executes market orders against a reference price with costs applied.

    - ``commission_per_trade``: flat fee added on every fill.
    - ``slippage_bps``: adverse price move, in basis points (1 bp = 0.01%).
      Buys fill a touch higher, sells a touch lower — a simple model of the
      spread/impact you'd really pay.
    - ``allow_fractional``: if False, buy quantities are floored to whole shares.
    """

    commission_per_trade: float = 0.0
    slippage_bps: float = 0.0
    allow_fractional: bool = True

    def _fill_price(self, side: str, ref_price: float) -> float:
        slip = ref_price * (self.slippage_bps / 10_000.0)
        return ref_price + slip if side == "buy" else ref_price - slip

    def execute(
        self,
        portfolio: Portfolio,
        order: Order,
        ref_price: float,
        date: dt.date,
    ) -> Trade | None:
        """Fill ``order`` at ``ref_price`` (usually the bar close).

        Returns the resulting Trade, or None if the order was rejected (e.g.
        not enough cash to buy, or no shares to sell). Rejections are silent so
        a strategy can fire optimistic orders without crashing the run.
        """
        price = self._fill_price(order.side, ref_price)
        qty = order.quantity

        if order.side == "buy":
            if not self.allow_fractional:
                qty = float(int(qty))
            affordable = portfolio.cash - self.commission_per_trade
            if qty * price > affordable:
                # Trim to what cash allows rather than rejecting outright.
                qty = max(0.0, affordable / price)
                if not self.allow_fractional:
                    qty = float(int(qty))
            if qty <= 0:
                return None
        else:  # sell
            held = portfolio.quantity(order.symbol)
            qty = min(qty, held)
            if qty <= 0:
                return None

        return portfolio.apply_fill(
            date=date,
            symbol=order.symbol,
            side=order.side,
            quantity=qty,
            price=price,
            commission=self.commission_per_trade,
        )
