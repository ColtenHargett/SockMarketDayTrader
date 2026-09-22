"""The backtest engine — walks the market bar by bar and runs the brain.

Each step: build the context from history up to now, ask the strategy what to do,
execute any orders through the paper broker, then mark the account to market and
record the equity. No future data is ever visible to the strategy.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from .broker import PaperBroker
from .market import Bar, group_by_date
from .metrics import Metrics, compute
from .portfolio import Portfolio
from .strategy import Context, Strategy


@dataclass
class BacktestResult:
    strategy_name: str
    dates: list[dt.date]
    equity_curve: list[float]
    portfolio: Portfolio
    metrics: Metrics
    buy_hold_curve: list[float] = field(default_factory=list)
    buy_hold_metrics: Metrics | None = None


class Engine:
    """Runs one strategy over one set of bars."""

    def __init__(
        self,
        bars: list[Bar],
        strategy: Strategy,
        broker: PaperBroker | None = None,
        starting_cash: float = 100_000.0,
    ) -> None:
        self.timeline = group_by_date(bars)
        self.strategy = strategy
        self.broker = broker or PaperBroker()
        self.portfolio = Portfolio(starting_cash=starting_cash)
        self._history: dict[str, list[Bar]] = {}

    def run(self) -> BacktestResult:
        if not self.timeline:
            raise ValueError("no bars to backtest")

        dates: list[dt.date] = []
        equity_curve: list[float] = []
        last_prices: dict[str, float] = {}

        first_context = self._context(*self.timeline[0])
        self.strategy.on_start(first_context)

        for date, bars in self.timeline:
            # Extend history with this bar before the strategy looks — it may act
            # on the current close.
            for symbol, bar in bars.items():
                self._history.setdefault(symbol, []).append(bar)
                last_prices[symbol] = bar.close

            context = self._context(date, bars)
            orders = self.strategy.decide(context) or []
            for order in orders:
                bar = bars.get(order.symbol)
                if bar is None:
                    continue  # can't trade a symbol that isn't trading today
                self.broker.execute(self.portfolio, order, bar.close, date)

            dates.append(date)
            equity_curve.append(self.portfolio.equity(last_prices))

        self.strategy.on_finish(self._context(*self.timeline[-1]))

        realized = [t.realized_pnl for t in self.portfolio.trades]
        metrics = compute(dates, equity_curve, realized, len(self.portfolio.trades))

        bh_dates, bh_curve = self._buy_hold(equity_curve[0])
        bh_metrics = compute(bh_dates, bh_curve, [], 0)

        return BacktestResult(
            strategy_name=getattr(self.strategy, "name", type(self.strategy).__name__),
            dates=dates,
            equity_curve=equity_curve,
            portfolio=self.portfolio,
            metrics=metrics,
            buy_hold_curve=bh_curve,
            buy_hold_metrics=bh_metrics,
        )

    def _context(self, date: dt.date, bars: dict[str, Bar]) -> Context:
        return Context(
            date=date,
            bars=bars,
            history={s: list(h) for s, h in self._history.items()},
            portfolio=self.portfolio,
        )

    def _buy_hold(self, starting_equity: float) -> tuple[list[dt.date], list[float]]:
        """Benchmark: split the starting cash equally across all symbols on day
        one, hold to the end. This is the bar every brain must clear."""
        symbols = sorted({s for _, bars in self.timeline for s in bars})
        if not symbols:
            return [], []
        alloc = starting_equity / len(symbols)

        # Buy on each symbol's first available bar.
        shares: dict[str, float] = {}
        for symbol in symbols:
            for _, bars in self.timeline:
                if symbol in bars:
                    shares[symbol] = alloc / bars[symbol].close
                    break

        dates: list[dt.date] = []
        curve: list[float] = []
        last_prices: dict[str, float] = {}
        for date, bars in self.timeline:
            for symbol, bar in bars.items():
                last_prices[symbol] = bar.close
            value = sum(shares.get(s, 0.0) * last_prices.get(s, 0.0) for s in symbols)
            dates.append(date)
            curve.append(value)
        return dates, curve
