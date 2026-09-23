"""The plug-in point for a machine-learning predictor (e.g. Colten's repo).

The idea: keep the *signal* (what will the price do?) separate from the
*strategy* (what do I do about it?). Your ML model only has to answer one
question per symbol per bar — a ``Signal`` — and ``PredictorStrategy`` turns
that into orders, position sizing, and exits.

To wire in your own model:

    from sockmarket.strategies.predictor import SignalPredictor, PredictorStrategy

    class MyModel(SignalPredictor):
        def predict(self, symbol, history):
            # history is a list of Bar, oldest first, no future data.
            # return a Signal: direction in {-1, 0, +1} and a 0..1 confidence.
            ...

    strategy = PredictorStrategy(MyModel())

That's the whole contract. The predictor never sees cash or positions, so it
can't accidentally cheat, and you can unit-test it in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..broker import Order
from ..market import Bar
from ..strategy import Context, Strategy


@dataclass
class Signal:
    """A prediction for one symbol on one bar.

    direction: -1 sell/avoid, 0 neutral, +1 buy.
    confidence: 0..1, scales how much of the allocation is deployed.
    """

    direction: int = 0
    confidence: float = 0.0

    def clamped(self) -> "Signal":
        d = max(-1, min(1, int(self.direction)))
        c = max(0.0, min(1.0, float(self.confidence)))
        return Signal(d, c)


class SignalPredictor:
    """Interface your ML model implements. One method, no market-state access."""

    def predict(self, symbol: str, history: list[Bar]) -> Signal:
        raise NotImplementedError


class ExamplePredictor(SignalPredictor):
    """A tiny, honest stand-in so the 'predictor' strategy runs out of the box.

    It is deliberately simple (short-vs-long trend with a confidence from the
    gap). Replace it with your trained model — the rest of the system is unchanged.
    """

    def __init__(self, short: int = 10, long: int = 40) -> None:
        self.short = short
        self.long = long

    def predict(self, symbol: str, history: list[Bar]) -> Signal:
        closes = [b.close for b in history]
        if len(closes) < self.long:
            return Signal(0, 0.0)
        short_ma = sum(closes[-self.short :]) / self.short
        long_ma = sum(closes[-self.long :]) / self.long
        if long_ma == 0:
            return Signal(0, 0.0)
        gap = (short_ma - long_ma) / long_ma
        direction = 1 if gap > 0 else (-1 if gap < 0 else 0)
        confidence = min(1.0, abs(gap) * 20)  # scale the gap into a 0..1 feel
        return Signal(direction, confidence)


class PredictorStrategy(Strategy):
    """Turns per-symbol Signals into a target-weight portfolio.

    Confidence scales the position: a +1 signal at 0.5 confidence targets half of
    the per-symbol allocation. Non-positive signals flatten the position.
    """

    name = "predictor"

    def __init__(
        self,
        predictor: SignalPredictor | None = None,
        allocation: float = 0.95,
        min_confidence: float = 0.05,
    ) -> None:
        self.predictor = predictor or ExamplePredictor()
        self.allocation = allocation
        self.min_confidence = min_confidence

    def decide(self, context: Context) -> list[Order]:
        orders: list[Order] = []
        symbols = list(context.bars)
        per_symbol = self.allocation / len(symbols) if symbols else 0.0

        for symbol in symbols:
            history = context.history.get(symbol, [])
            signal = self.predictor.predict(symbol, history).clamped()

            if signal.direction > 0 and signal.confidence >= self.min_confidence:
                target = per_symbol * signal.confidence
            else:
                target = 0.0  # neutral or bearish -> flat (no shorting)

            orders += context.order_target_percent(symbol, target)
        return orders
