import datetime as dt

import pytest

from sockmarket.market import Bar
from sockmarket.live.brokers import LocalPaperBroker
from sockmarket.live.feeds import ReplayFeed
from sockmarket.live.runner import LiveConfig, run_loop, tick
from sockmarket.live.state import LiveState
from sockmarket.strategies import REGISTRY


def make_series(sym, closes, start=dt.date(2025, 1, 2)):
    bars, d = [], start
    for c in closes:
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        bars.append(Bar(d, sym, c, c, c, c, 1000))
        d += dt.timedelta(days=1)
    return bars


def _config(tmp_path, feed, state, strategy_name="buy_and_hold"):
    return LiveConfig(
        symbols=["SOCK"],
        strategy=REGISTRY[strategy_name](),
        broker=LocalPaperBroker(feed=feed, state=state),
        state_path=str(tmp_path / "state.json"),
        log_path=str(tmp_path / "decisions.log"),
        require_market_open=False,  # act regardless of wall-clock time
    )


def test_tick_places_order_and_persists(tmp_path):
    feed = ReplayFeed({"SOCK": make_series("SOCK", [100, 101, 102])})
    state = LiveState(starting_cash=10_000.0)
    config = _config(tmp_path, feed, state)

    result = tick(config, state)
    assert result["acted"] is True
    assert result["orders"] == 1  # buy_and_hold buys on first sight
    assert state.portfolio.quantity("SOCK") > 0

    # state file was written and reloads cleanly
    reloaded = LiveState.load(config.state_path)
    assert reloaded.portfolio.quantity("SOCK") == pytest.approx(state.portfolio.quantity("SOCK"))


def test_benchmark_is_tracked_and_lifetime_aligned(tmp_path):
    feed = ReplayFeed({"SOCK": make_series("SOCK", [100, 110, 120, 130])})
    state = LiveState(starting_cash=10_000.0)
    config = _config(tmp_path, feed, state)
    for _ in range(4):
        tick(config, state)
    # benchmark bought at 100 with all 10k -> 100 shares; by the last bar (130)
    # the buy-and-hold value is 13,000, and it has one point per tick.
    assert len(state.benchmark_log) == 4
    assert state.benchmark_log[0][1] == pytest.approx(10_000.0)
    assert state.benchmark_log[-1][1] == pytest.approx(13_000.0)
    # equity and benchmark logs stay tick-for-tick aligned
    assert len(state.equity_log) == len(state.benchmark_log)


def test_no_new_bar_means_hold(tmp_path):
    feed = ReplayFeed({"SOCK": make_series("SOCK", [100])})
    state = LiveState(starting_cash=10_000.0)
    config = _config(tmp_path, feed, state)

    first = tick(config, state)
    assert first["acted"] is True
    # feed exhausted -> no new bar -> hold, no crash
    second = tick(config, state)
    assert second["acted"] is False
    assert second["reason"] == "no_new_data"


def test_market_closed_skips(tmp_path):
    feed = ReplayFeed({"SOCK": make_series("SOCK", [100, 101])})
    state = LiveState(starting_cash=10_000.0)
    config = _config(tmp_path, feed, state)
    config.require_market_open = True
    config.clock = _AlwaysClosedClock()

    result = tick(config, state)
    assert result["acted"] is False
    assert result["reason"] == "market_closed"


def test_run_loop_bounded(tmp_path):
    feed = ReplayFeed({"SOCK": make_series("SOCK", [100, 101, 102, 103, 104])})
    state = LiveState(starting_cash=10_000.0)
    config = _config(tmp_path, feed, state, strategy_name="sma_crossover")
    # Should run exactly 3 ticks without sleeping and without error.
    run_loop(config, poll_seconds=0.0, max_ticks=3)
    assert len(state.equity_log) == 3


class _AlwaysClosedClock:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("America/New_York")

    def now(self):
        return dt.datetime(2025, 6, 14, 12, 0, tzinfo=self.tz)  # a Saturday

    def is_open(self, at=None):
        return False

    def next_open(self, at=None):
        return dt.datetime(2025, 6, 16, 9, 30, tzinfo=self.tz)

    def seconds_until_open(self, at=None):
        return 3600.0
