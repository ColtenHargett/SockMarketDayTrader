import datetime as dt

import pytest

from sockmarket.live.brokers import AlpacaBroker, AlpacaError


def _broker():
    return AlpacaBroker(key_id="k", secret_key="s")


def test_from_env_requires_keys(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
    with pytest.raises(AlpacaError):
        AlpacaBroker.from_env()


def test_from_env_reads_feed(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY_ID", "k")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "s")
    monkeypatch.setenv("ALPACA_DATA_FEED", "iex")
    b = AlpacaBroker.from_env()
    assert b.data_feed == "iex"


def test_daily_bars_use_iex_feed_and_parse(monkeypatch):
    b = _broker()
    captured = {}

    def fake_request(method, url, body=None):
        captured["url"] = url
        return {"bars": [
            {"t": "2026-01-02T05:00:00Z", "o": 100, "h": 102, "l": 99, "c": 101, "v": 1000},
            {"t": "2026-01-03T05:00:00Z", "o": 101, "h": 103, "l": 100, "c": 102, "v": 1200},
        ]}

    monkeypatch.setattr(b, "_request", fake_request)
    latest = b.latest_bar("AAPL")
    assert "feed=iex" in captured["url"]
    assert latest.date == dt.date(2026, 1, 3)
    assert latest.close == pytest.approx(102)

    hist = b.backfill("AAPL")
    assert len(hist) == 2


def test_position_qty_absent_is_zero(monkeypatch):
    b = _broker()

    def fake_request(method, url, body=None):
        raise AlpacaError("Alpaca GET ... -> 404: position does not exist")

    monkeypatch.setattr(b, "_request", fake_request)
    assert b.position_qty("AAPL") == 0.0
