import datetime as dt

import pytest

from sockmarket.dashboard import _buy_hold_series, render_dashboard
from sockmarket.market import Bar
from sockmarket.live.state import LiveState


def bar(day, sym, close):
    d = dt.date.fromisoformat(day)
    return Bar(d, sym, close, close, close, close, 1000)


def seeded_state():
    s = LiveState(starting_cash=10_000.0)
    for i, close in enumerate([100, 110, 120]):
        day = f"2025-01-0{i + 2}"
        s.record_bar(bar(day, "SOCK", close))
    # a couple of equity points and a trade
    s.portfolio.apply_fill(dt.date(2025, 1, 2), "SOCK", "buy", 10, 100.0)
    s.equity_log = [("2025-01-02T16:00:00", 10_000.0), ("2025-01-03T16:00:00", 10_100.0),
                    ("2025-01-04T16:00:00", 10_200.0)]
    return s


def test_buy_hold_series_tracks_price():
    s = seeded_state()
    curve = _buy_hold_series(s)
    # single symbol -> all cash in SOCK at 100 -> 100 shares; values track price*100
    assert curve[0] == ("2025-01-02", pytest.approx(10_000.0))
    assert curve[-1][1] == pytest.approx(12_000.0)  # 100 shares * 120


def test_render_contains_key_sections():
    html = render_dashboard(seeded_state())
    assert "<svg id=\"chart\"" in html
    assert "Equity curve" in html
    assert "Open positions" in html
    assert "Buy &amp; Hold" in html
    # embedded data payload is valid and present
    assert '<script type="application/json" id="data">' in html
    assert "SOCK" in html


def test_render_handles_empty_state():
    html = render_dashboard(LiveState(starting_cash=5_000.0))
    # no crash, and it tells the user the chart isn't ready yet
    assert "No equity history yet" in html
    assert "No open positions" in html


def test_buy_hold_empty_history_is_empty():
    assert _buy_hold_series(LiveState()) == []
