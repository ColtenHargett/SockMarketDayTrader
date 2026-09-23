import datetime as dt

import pytest

from sockmarket.broker import Order
from sockmarket.engine import Engine
from sockmarket.market import Bar
from sockmarket.strategy import Context, Strategy
from sockmarket.strategies import REGISTRY
from sockmarket.strategies.predictor import PredictorStrategy, SignalPredictor, Signal


def make_bars(symbol, closes, start=dt.date(2024, 1, 1)):
    bars = []
    d = start
    for c in closes:
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        bars.append(Bar(d, symbol, c, c, c, c, 1_000))
        d += dt.timedelta(days=1)
    return bars


class BuyOnceHold(Strategy):
    name = "buy_once"

    def __init__(self):
        self.done = False

    def decide(self, context: Context):
        if not self.done:
            self.done = True
            return [Order("SOCK", "buy", 10)]
        return []


def test_engine_runs_and_tracks_equity():
    bars = make_bars("SOCK", [100, 110, 120, 130])
    result = Engine(bars, BuyOnceHold(), starting_cash=10_000.0).run()
    assert len(result.equity_curve) == 4
    # bought 10 @100 -> cash 9000 + 10*130 = 10300 at the end
    assert result.equity_curve[-1] == pytest.approx(10_300.0)
    assert result.metrics.total_return == pytest.approx(0.03)


def test_strategy_cannot_see_the_future():
    """History handed to the strategy must never contain a later bar."""
    seen_lengths = []

    class Recorder(Strategy):
        def decide(self, context: Context):
            hist = context.history.get("SOCK", [])
            seen_lengths.append(len(hist))
            # the last bar in history must be today's bar
            assert hist[-1].close == context.bars["SOCK"].close
            return []

    bars = make_bars("SOCK", [1, 2, 3, 4, 5])
    Engine(bars, Recorder()).run()
    assert seen_lengths == [1, 2, 3, 4, 5]


def test_buy_and_hold_matches_benchmark():
    bars = make_bars("SOCK", [100, 105, 95, 120])
    result = Engine(bars, REGISTRY["buy_and_hold"](), starting_cash=10_000.0).run()
    # buy&hold strategy should closely track the internal benchmark curve
    assert result.metrics.total_return == pytest.approx(
        result.buy_hold_metrics.total_return, abs=1e-6
    )


def test_predictor_plugin_contract():
    class AlwaysBuy(SignalPredictor):
        def predict(self, symbol, history):
            return Signal(direction=1, confidence=1.0)

    bars = make_bars("SOCK", [100, 110, 120])
    strat = PredictorStrategy(AlwaysBuy(), allocation=1.0, min_confidence=0.0)
    result = Engine(bars, strat, starting_cash=10_000.0).run()
    # It should have taken a long position and profited on the uptrend.
    assert result.metrics.total_return > 0
    assert result.portfolio.trades  # at least one trade happened


def test_empty_bars_raises():
    with pytest.raises(ValueError):
        Engine([], BuyOnceHold()).run()
