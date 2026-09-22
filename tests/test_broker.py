import datetime as dt

import pytest

from sockmarket.broker import Order, PaperBroker
from sockmarket.portfolio import Portfolio


D = dt.date(2024, 1, 2)


def test_slippage_moves_buy_price_up():
    b = PaperBroker(slippage_bps=100)  # 1%
    p = Portfolio(starting_cash=10_000.0)
    b.execute(p, Order("SOCK", "buy", 10), ref_price=100.0, date=D)
    # filled at 101 -> cash 10000 - 1010
    assert p.cash == pytest.approx(10_000.0 - 1010.0)


def test_buy_is_trimmed_to_affordable_cash():
    b = PaperBroker()
    p = Portfolio(starting_cash=100.0)
    trade = b.execute(p, Order("SOCK", "buy", 10), ref_price=50.0, date=D)
    assert trade is not None
    assert trade.quantity == pytest.approx(2.0)  # only 2 shares affordable
    assert p.cash == pytest.approx(0.0)


def test_sell_capped_at_holdings():
    b = PaperBroker()
    p = Portfolio(starting_cash=10_000.0)
    b.execute(p, Order("SOCK", "buy", 3), ref_price=100.0, date=D)
    trade = b.execute(p, Order("SOCK", "sell", 10), ref_price=110.0, date=D)
    assert trade is not None
    assert trade.quantity == pytest.approx(3.0)
    assert p.quantity("SOCK") == 0


def test_sell_with_no_position_is_rejected():
    b = PaperBroker()
    p = Portfolio(starting_cash=10_000.0)
    assert b.execute(p, Order("SOCK", "sell", 1), ref_price=100.0, date=D) is None


def test_whole_shares_floor():
    b = PaperBroker(allow_fractional=False)
    p = Portfolio(starting_cash=1000.0)
    trade = b.execute(p, Order("SOCK", "buy", 7.9), ref_price=100.0, date=D)
    assert trade.quantity == pytest.approx(7.0)


def test_invalid_order_rejected_at_construction():
    with pytest.raises(ValueError):
        Order("SOCK", "hold", 1)
    with pytest.raises(ValueError):
        Order("SOCK", "buy", 0)
