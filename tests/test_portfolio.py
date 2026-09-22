import datetime as dt

import pytest

from sockmarket.portfolio import Portfolio


D = dt.date(2024, 1, 2)


def test_buy_updates_cash_and_position():
    p = Portfolio(starting_cash=1000.0)
    p.apply_fill(D, "SOCK", "buy", 10, 50.0)
    assert p.cash == pytest.approx(500.0)
    assert p.quantity("SOCK") == 10
    assert p.positions["SOCK"].avg_cost == pytest.approx(50.0)


def test_avg_cost_is_weighted():
    p = Portfolio(starting_cash=10_000.0)
    p.apply_fill(D, "SOCK", "buy", 10, 100.0)
    p.apply_fill(D, "SOCK", "buy", 10, 200.0)
    assert p.positions["SOCK"].avg_cost == pytest.approx(150.0)


def test_sell_books_realized_pnl():
    p = Portfolio(starting_cash=10_000.0)
    p.apply_fill(D, "SOCK", "buy", 10, 100.0)
    trade = p.apply_fill(D, "SOCK", "sell", 10, 130.0)
    assert trade.realized_pnl == pytest.approx(300.0)
    assert p.quantity("SOCK") == 0
    assert p.realized_pnl == pytest.approx(300.0)


def test_cannot_oversell():
    p = Portfolio(starting_cash=10_000.0)
    p.apply_fill(D, "SOCK", "buy", 5, 100.0)
    with pytest.raises(ValueError):
        p.apply_fill(D, "SOCK", "sell", 10, 100.0)


def test_equity_marks_to_market():
    p = Portfolio(starting_cash=1000.0)
    p.apply_fill(D, "SOCK", "buy", 10, 50.0)  # cash now 500, 10 shares
    assert p.equity({"SOCK": 60.0}) == pytest.approx(500.0 + 600.0)


def test_commission_reduces_cash_and_pnl():
    p = Portfolio(starting_cash=1000.0)
    p.apply_fill(D, "SOCK", "buy", 1, 100.0, commission=1.0)
    assert p.cash == pytest.approx(899.0)
    trade = p.apply_fill(D, "SOCK", "sell", 1, 110.0, commission=1.0)
    assert trade.realized_pnl == pytest.approx(10.0 - 1.0)
