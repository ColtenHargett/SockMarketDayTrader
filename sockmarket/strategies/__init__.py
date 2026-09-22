"""Built-in trading brains and a registry so the CLI can list them by name."""

from __future__ import annotations

from ..strategy import Strategy
from .buy_and_hold import BuyAndHold
from .sma_crossover import SmaCrossover
from .momentum import Momentum
from .mean_reversion import MeanReversion
from .predictor import PredictorStrategy, SignalPredictor, ExamplePredictor

REGISTRY: dict[str, type[Strategy]] = {
    "buy_and_hold": BuyAndHold,
    "sma_crossover": SmaCrossover,
    "momentum": Momentum,
    "mean_reversion": MeanReversion,
    "predictor": PredictorStrategy,
}

__all__ = [
    "REGISTRY",
    "BuyAndHold",
    "SmaCrossover",
    "Momentum",
    "MeanReversion",
    "PredictorStrategy",
    "SignalPredictor",
    "ExamplePredictor",
]
