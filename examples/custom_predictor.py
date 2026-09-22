"""Example: plug a custom 'ML' predictor into the backtester.

Run from the repo root:

    python examples/custom_predictor.py

Swap the body of ``predict`` for a call into your trained model (for example the
one in your Stock Market Predictor repo). Everything else — sizing, exits,
accounting, scoring — is handled for you.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running this script directly (`python examples/custom_predictor.py`)
# by putting the repo root on the import path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sockmarket.engine import Engine
from sockmarket.market import Bar, load_csv
from sockmarket.report import render
from sockmarket.strategies.predictor import PredictorStrategy, Signal, SignalPredictor

DATA = "data/sample_prices.csv"


class BreakoutPredictor(SignalPredictor):
    """A toy model: bullish when today's close is a new N-day high.

    Replace this with your real model. Contract: given a symbol and its bar
    history (oldest first, no future data), return a Signal.
    """

    def __init__(self, lookback: int = 20) -> None:
        self.lookback = lookback

    def predict(self, symbol: str, history: list[Bar]) -> Signal:
        closes = [b.close for b in history]
        if len(closes) <= self.lookback:
            return Signal(0, 0.0)
        window = closes[-self.lookback - 1 : -1]  # prior N closes, excluding today
        today = closes[-1]
        recent_high = max(window)
        if today >= recent_high:
            strength = (today / recent_high) - 1.0
            return Signal(direction=1, confidence=min(1.0, 0.5 + strength * 10))
        return Signal(direction=0, confidence=0.0)


def main() -> None:
    bars = load_csv(DATA)
    strategy = PredictorStrategy(BreakoutPredictor(lookback=20))
    result = Engine(bars, strategy, starting_cash=100_000.0).run()
    print(render(result))


if __name__ == "__main__":
    main()
