"""The live runner: fetch the latest bars, ask the brain, place orders.

Two entry points share one tick:

- ``run_once``  — one decision, then exit. This is what a scheduler (GitHub
  Actions cron, system cron) calls once per day after the close.
- ``run_loop``  — tick forever while the market is open, sleeping between ticks
  and until the next open. This is the real-time intraday mode.
"""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass, field

from ..portfolio import Position
from ..strategy import Context, Strategy
from .brokers import LiveBroker, LocalPaperBroker
from .clock import MarketClock
from .state import LiveState


@dataclass
class LiveConfig:
    symbols: list[str]
    strategy: Strategy
    broker: LiveBroker
    clock: MarketClock = field(default_factory=MarketClock)
    state_path: str = "data/live_state.json"
    log_path: str = "data/live_decisions.log"
    require_market_open: bool = True  # set False to act on the latest bar anytime


def _log(config: LiveConfig, message: str) -> None:
    line = f"{dt.datetime.now(config.clock.tz).isoformat()}  {message}"
    print(line)
    try:
        with open(config.log_path, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass  # logging must never crash a trading run


def _sync_from_broker(state: LiveState, broker: LiveBroker) -> None:
    """For brokers that own the truth (Alpaca), mirror their cash/positions into
    the local portfolio so ``order_target_percent`` sizes against real money."""
    snap = broker.snapshot()
    if snap is None:
        return
    cash, positions = snap
    state.portfolio.cash = cash
    state.portfolio.positions = {
        sym: Position(quantity=qty, avg_cost=avg) for sym, (qty, avg) in positions.items()
    }


def tick(config: LiveConfig, state: LiveState) -> dict:
    """Run exactly one decision cycle. Returns a small summary dict."""
    clock = config.clock
    now = clock.now()

    if config.require_market_open and not clock.is_open(now):
        _log(config, f"market closed; skipping (next open {clock.next_open(now)})")
        return {"acted": False, "reason": "market_closed", "orders": 0}

    # 1) Pull the latest bar per symbol and fold new ones into history.
    new_data = False
    for symbol in config.symbols:
        bar = config.broker.latest_bar(symbol)
        if bar is None:
            _log(config, f"no bar returned for {symbol}")
            continue
        if state.record_bar(bar):
            new_data = True

    if not new_data:
        _log(config, "no new bars since last tick; holding")
        return {"acted": False, "reason": "no_new_data", "orders": 0}

    # 2) Sync real account state (Alpaca) so sizing is correct.
    _sync_from_broker(state, config.broker)

    # 3) Build the same Context the backtester uses and ask the brain.
    bars_now = {s: h[-1] for s, h in state.history.items() if h and s in config.symbols}
    context = Context(
        date=now.date(),
        bars=bars_now,
        history={s: list(h) for s, h in state.history.items()},
        portfolio=state.portfolio,
    )
    orders = config.strategy.decide(context) or []

    # 4) Route orders to the broker at the latest close.
    placed = 0
    for order in orders:
        bar = bars_now.get(order.symbol)
        if bar is None:
            continue
        config.broker.submit(order, bar.close, now)
        placed += 1
        _log(config, f"ORDER {order.side} {order.quantity:.4f} {order.symbol} @~{bar.close:.2f}"
                     f"  ({order.reason})")

    # 5) Record equity + benchmark (keyed by the market date so the equity curve
    #    plots on the real trading calendar) and persist.
    as_of = max((h[-1].date for s, h in state.history.items() if h and s in config.symbols),
                default=now.date())
    state.ensure_benchmark(config.symbols)
    state.last_run = now.isoformat()
    state.log_equity(as_of)
    state.log_benchmark(as_of)
    state.save(config.state_path)

    equity = config.broker.equity() if not isinstance(config.broker, LocalPaperBroker) else state.equity()
    _log(config, f"tick done: {placed} order(s), equity ~${equity:,.2f}")
    return {"acted": True, "orders": placed, "equity": equity}


def _state_for(config: LiveConfig, starting_cash: float) -> LiveState:
    """The runner and a LocalPaperBroker must share one LiveState object, or
    fills would land in a different portfolio than the one that gets saved."""
    if isinstance(config.broker, LocalPaperBroker):
        return config.broker.state
    return LiveState.load(config.state_path, starting_cash=starting_cash)


def run_once(config: LiveConfig, starting_cash: float = 100_000.0) -> dict:
    """One decision tick, for a scheduler. Loads and saves state around it."""
    state = _state_for(config, starting_cash)
    config.strategy.on_start(
        Context(date=config.clock.now().date(), bars={}, history=state.history, portfolio=state.portfolio)
    )
    return tick(config, state)


def run_loop(
    config: LiveConfig,
    poll_seconds: float = 60.0,
    starting_cash: float = 100_000.0,
    max_ticks: int | None = None,
) -> None:
    """Continuous real-time loop. Ticks every ``poll_seconds`` while the market
    is open, and sleeps until the next open when it's closed.

    ``max_ticks`` bounds the run (used by tests); None runs indefinitely.
    """
    state = _state_for(config, starting_cash)
    clock = config.clock
    ticks = 0
    _log(config, f"live loop starting: {config.strategy.name} via {config.broker.describe()} "
                 f"on {', '.join(config.symbols)}")

    while max_ticks is None or ticks < max_ticks:
        if config.require_market_open and not clock.is_open():
            wait = min(clock.seconds_until_open(), 3600.0)  # cap so holiday tables refresh
            _log(config, f"market closed; sleeping {int(wait)}s until ~{clock.next_open()}")
            if max_ticks is not None:
                break  # tests don't actually sleep for hours
            time.sleep(max(1.0, wait))
            continue

        tick(config, state)
        ticks += 1
        if max_ticks is None or ticks < max_ticks:
            time.sleep(poll_seconds)

    _log(config, "live loop stopped")
