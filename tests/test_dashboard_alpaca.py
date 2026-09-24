import datetime as dt

from sockmarket.dashboard import render_alpaca_dashboard
from sockmarket.market import Bar


class FakeAlpaca:
    """Stands in for AlpacaBroker with canned account data."""

    def account(self):
        return {"equity": "110000", "cash": "20000"}

    def portfolio_history(self, period="1M", timeframe="1D"):
        base = 100_000.0
        days = [dt.date(2026, 1, d) for d in range(2, 8)]  # 6 trading days
        equity = [100_000, 101_000, 103_000, 102_000, 108_000, 110_000]
        return [d.isoformat() for d in days], [float(e) for e in equity], base

    def positions_detailed(self):
        return [{"symbol": "AAPL", "qty": 100.0, "avg_cost": 300.0,
                 "last": 333.0, "value": 33_300.0, "unrealized": 3_300.0}]

    def fills(self, limit=50):
        return [{"date": "2026-01-06", "symbol": "AAPL", "side": "buy",
                 "qty": 100.0, "price": 300.0, "realized": 0.0}]

    def _daily_bars(self, symbol, limit):
        out, price = [], 300.0
        for i in range(6):
            d = dt.date(2026, 1, 2 + i)
            out.append(Bar(d, symbol, price, price, price, price, 1000))
            price *= 1.01
        return out


def test_alpaca_dashboard_renders_account_data():
    html = render_alpaca_dashboard(FakeAlpaca(), ["AAPL"], title="Test Account")
    assert "Test Account" in html
    assert "$110,000" in html            # current equity tile
    assert "+10.00%" in html             # total return from 100k -> 110k
    assert "AAPL" in html                # position + fill
    assert '<svg id="chart"' in html     # equity curve present (>=2 points)
    # embedded payload carries the account equity series and a benchmark
    assert '"strategy"' in html and '"benchmark"' in html


def test_alpaca_dashboard_handles_empty_account():
    class Empty(FakeAlpaca):
        def portfolio_history(self, period="1M", timeframe="1D"):
            return [], [], 0.0

        def positions_detailed(self):
            return []

        def fills(self, limit=50):
            return []

        def account(self):
            return {"equity": "100000", "cash": "100000"}

    html = render_alpaca_dashboard(Empty(), ["AAPL"])
    assert "No equity history yet" in html
    assert "No open positions" in html
