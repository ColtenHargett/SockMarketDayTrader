import datetime as dt

import pytest

from sockmarket.metrics import compute


def make_dates(n, start=dt.date(2024, 1, 1)):
    return [start + dt.timedelta(days=i) for i in range(n)]


def test_total_return_and_drawdown():
    equity = [100.0, 120.0, 90.0, 150.0]
    m = compute(make_dates(4), equity, [], num_trades=0)
    assert m.total_return == pytest.approx(0.5)
    # peak 120 -> trough 90 == 25% drawdown
    assert m.max_drawdown == pytest.approx(0.25)


def test_win_rate_only_counts_closing_trades():
    equity = [100.0, 110.0]
    m = compute(make_dates(2), equity, [50.0, -20.0, 0.0], num_trades=3)
    # two closing trades (50 win, -20 loss); the 0.0 is not a close
    assert m.win_rate == pytest.approx(0.5)


def test_flat_curve_has_zero_metrics():
    equity = [100.0, 100.0, 100.0]
    m = compute(make_dates(3), equity, [], num_trades=0)
    assert m.total_return == pytest.approx(0.0)
    assert m.sharpe == pytest.approx(0.0)
    assert m.max_drawdown == pytest.approx(0.0)


def test_single_point_is_safe():
    m = compute([dt.date(2024, 1, 1)], [100.0], [], num_trades=0)
    assert m.total_return == 0
    assert m.ending_equity == 100.0
