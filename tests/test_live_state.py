import datetime as dt

import pytest

from sockmarket.market import Bar
from sockmarket.live.state import LiveState


def bar(day, sym="SOCK", close=100.0):
    return Bar(dt.date.fromisoformat(day), sym, close, close, close, close, 1000)


def test_record_bar_rejects_duplicates_and_old():
    s = LiveState()
    assert s.record_bar(bar("2025-01-02")) is True
    assert s.record_bar(bar("2025-01-02")) is False  # same date
    assert s.record_bar(bar("2025-01-01")) is False  # older
    assert s.record_bar(bar("2025-01-03")) is True   # newer


def test_history_is_bounded():
    s = LiveState()
    from sockmarket.live.state import HISTORY_LIMIT

    start = dt.date(2020, 1, 1)
    for i in range(HISTORY_LIMIT + 50):
        d = (start + dt.timedelta(days=i)).isoformat()
        s.record_bar(bar(d))
    assert len(s.history["SOCK"]) == HISTORY_LIMIT


def test_roundtrip_persistence(tmp_path):
    s = LiveState(starting_cash=50_000.0)
    s.record_bar(bar("2025-01-02", close=100.0))
    s.portfolio.apply_fill(dt.date(2025, 1, 2), "SOCK", "buy", 10, 100.0)
    s.log_equity(dt.datetime(2025, 1, 2, 16, 0))

    path = tmp_path / "state.json"
    s.save(path)
    loaded = LiveState.load(path)

    assert loaded.portfolio.cash == pytest.approx(s.portfolio.cash)
    assert loaded.portfolio.quantity("SOCK") == pytest.approx(10)
    assert loaded.history["SOCK"][-1].close == pytest.approx(100.0)
    assert loaded.equity_log[-1][1] == pytest.approx(s.equity_log[-1][1])


def test_load_missing_file_returns_fresh(tmp_path):
    loaded = LiveState.load(tmp_path / "nope.json", starting_cash=25_000.0)
    assert loaded.portfolio.cash == pytest.approx(25_000.0)
    assert loaded.history == {}
