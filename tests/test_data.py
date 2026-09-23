import datetime as dt
import json
import urllib.error

import pytest

from sockmarket import data
from sockmarket.data import _http_get, _parse_yahoo, fetch_symbol


def _yahoo_payload():
    # Two days; the second close is null (Yahoo pads incomplete rows) and must be skipped.
    return json.dumps({
        "chart": {"result": [{
            "timestamp": [
                int(dt.datetime(2025, 1, 2, tzinfo=dt.timezone.utc).timestamp()),
                int(dt.datetime(2025, 1, 3, tzinfo=dt.timezone.utc).timestamp()),
            ],
            "indicators": {"quote": [{
                "open": [100.0, 101.0], "high": [102.0, 103.0],
                "low": [99.0, 100.0], "close": [101.5, None], "volume": [1_000_000, 0],
            }]},
        }]}
    })


def test_parse_yahoo_extracts_bars_and_skips_nulls():
    bars = _parse_yahoo(_yahoo_payload(), "AAPL")
    assert len(bars) == 1  # the null-close row is dropped
    b = bars[0]
    assert b.symbol == "AAPL"
    assert b.date == dt.date(2025, 1, 2)
    assert b.close == pytest.approx(101.5)
    assert b.volume == 1_000_000


def test_parse_yahoo_empty_result_is_empty():
    assert _parse_yahoo(json.dumps({"chart": {"result": None}}), "AAPL") == []


def test_fetch_symbol_prefers_yahoo(monkeypatch):
    calls = []
    monkeypatch.setattr(data, "fetch_symbol_yahoo",
                        lambda s, timeout=20.0: (calls.append("y"), _parse_yahoo(_yahoo_payload(), s))[1])
    monkeypatch.setattr(data, "fetch_symbol_stooq",
                        lambda s, timeout=20.0: (calls.append("s"), [])[1])
    bars = fetch_symbol("AAPL")
    assert bars and calls == ["y"]  # Stooq not consulted when Yahoo answers


def test_fetch_symbol_falls_back_to_stooq(monkeypatch):
    def boom(s, timeout=20.0):
        raise RuntimeError("yahoo down")

    monkeypatch.setattr(data, "fetch_symbol_yahoo", boom)
    monkeypatch.setattr(data, "fetch_symbol_stooq", lambda s, timeout=20.0: _parse_yahoo(_yahoo_payload(), s))
    bars = fetch_symbol("AAPL")
    assert len(bars) == 1


def test_fetch_symbol_raises_when_all_sources_fail(monkeypatch):
    def boom(s, timeout=20.0):
        raise RuntimeError("down")

    monkeypatch.setattr(data, "fetch_symbol_yahoo", boom)
    monkeypatch.setattr(data, "fetch_symbol_stooq", boom)
    with pytest.raises(RuntimeError):
        fetch_symbol("AAPL")


class _FakeResp:
    def __init__(self, body):
        self._body = body.encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_http_get_retries_on_429_then_succeeds(monkeypatch):
    monkeypatch.setattr(data.time, "sleep", lambda *_: None)  # no real delay
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, None)
        return _FakeResp("ok")

    monkeypatch.setattr(data.urllib.request, "urlopen", fake_urlopen)
    assert _http_get("https://example.test", timeout=1.0) == "ok"
    assert calls["n"] == 2  # retried once after the 429


def test_http_get_gives_up_after_retries(monkeypatch):
    monkeypatch.setattr(data.time, "sleep", lambda *_: None)

    def always_429(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(data.urllib.request, "urlopen", always_429)
    with pytest.raises(urllib.error.HTTPError):
        _http_get("https://example.test", timeout=1.0, retries=2)
