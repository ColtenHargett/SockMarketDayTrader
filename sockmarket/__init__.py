"""SockMarketDayTrader — a zero-dependency paper-trading bot and backtester.

Public surface:

    from sockmarket import Engine, PaperBroker, Portfolio, Strategy, Context
    from sockmarket.market import load_csv
    from sockmarket.strategies import REGISTRY
"""

from __future__ import annotations

from .broker import Order, PaperBroker
from .engine import BacktestResult, Engine
from .market import Bar, load_csv
from .metrics import Metrics
from .portfolio import Portfolio, Position, Trade
from .strategy import Context, Strategy

__version__ = "0.1.0"

__all__ = [
    "Order",
    "PaperBroker",
    "BacktestResult",
    "Engine",
    "Bar",
    "load_csv",
    "Metrics",
    "Portfolio",
    "Position",
    "Trade",
    "Context",
    "Strategy",
    "__version__",
]
