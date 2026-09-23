import datetime as dt

from sockmarket.live.clock import NY, MarketClock


def at(y, m, d, hh, mm):
    return dt.datetime(y, m, d, hh, mm, tzinfo=NY)


def test_open_during_regular_hours():
    c = MarketClock()
    # Wednesday 2025-06-11, 10:00 ET -> open
    assert c.is_open(at(2025, 6, 11, 10, 0)) is True


def test_closed_before_open_and_after_close():
    c = MarketClock()
    assert c.is_open(at(2025, 6, 11, 9, 0)) is False
    assert c.is_open(at(2025, 6, 11, 16, 1)) is False


def test_closed_on_weekend():
    c = MarketClock()
    # Saturday 2025-06-14
    assert c.is_open(at(2025, 6, 14, 12, 0)) is False
    assert c.is_trading_day(dt.date(2025, 6, 14)) is False


def test_closed_on_holiday():
    c = MarketClock()
    # Independence Day 2025-07-04 (a Friday)
    assert c.is_trading_day(dt.date(2025, 7, 4)) is False
    assert c.is_open(at(2025, 7, 4, 11, 0)) is False


def test_early_close_day():
    c = MarketClock()
    # 2025-11-28 is a half day: open at 13:30, closed at 13:30
    assert c.is_open(at(2025, 11, 28, 12, 0)) is True
    assert c.is_open(at(2025, 11, 28, 13, 30)) is False


def test_next_open_skips_weekend():
    c = MarketClock()
    # Friday 2025-06-13 after close -> next open is Monday 2025-06-16 09:30
    nxt = c.next_open(at(2025, 6, 13, 17, 0))
    assert nxt.date() == dt.date(2025, 6, 16)
    assert nxt.time() == dt.time(9, 30)
