"""Live forward-trading: run a brain against real markets in real time.

This is where the bot stops replaying history and starts trading forward, on
real prices and real market hours, to answer the only question that matters:
does it actually make money going forward?

Two execution surfaces share one interface (``LiveBroker``):

- ``LocalPaperBroker`` — our own fake-money engine, prices from a free feed,
  state persisted to disk. Zero signup. Great for a once-a-day cron bot.
- ``AlpacaBroker`` — a real Alpaca *paper* brokerage account (real fills, real
  data, real market clock, still no real money). The realistic path.

And two ways to run (``runner.py``):

- ``run_once`` — a single decision tick, for a scheduler / GitHub Actions cron.
- ``run_loop`` — a continuous real-time loop that ticks while the market is open.
"""

from __future__ import annotations

from .clock import MarketClock
from .state import LiveState
from .feeds import Feed, StooqFeed, ReplayFeed
from .brokers import LiveBroker, LocalPaperBroker, AlpacaBroker
from .runner import run_once, run_loop, LiveConfig

__all__ = [
    "MarketClock",
    "LiveState",
    "Feed",
    "StooqFeed",
    "ReplayFeed",
    "LiveBroker",
    "LocalPaperBroker",
    "AlpacaBroker",
    "run_once",
    "run_loop",
    "LiveConfig",
]
