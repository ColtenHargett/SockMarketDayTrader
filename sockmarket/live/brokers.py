"""Live brokers: the seam between a decision and a real order.

``LiveBroker`` is the interface the runner talks to. Two implementations:

- ``LocalPaperBroker``  — our own fake-money engine + a free price feed +
  on-disk state. Zero signup; we approximate fills at the latest close.
- ``AlpacaBroker``      — a real Alpaca *paper* account: real fills, real-time
  data, and Alpaca holds the positions/cash. Standard-library HTTP only.

Both expose the same handful of methods so the runner never knows which it's
using.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from ..broker import Order, PaperBroker
from ..market import Bar
from .feeds import Feed
from .state import LiveState


class LiveBroker:
    """Interface the runner drives. Prices come from the broker so the paper and
    Alpaca paths stay symmetric."""

    def latest_bar(self, symbol: str) -> Bar | None:
        raise NotImplementedError

    def position_qty(self, symbol: str) -> float:
        raise NotImplementedError

    def equity(self) -> float:
        raise NotImplementedError

    def submit(self, order: Order, ref_price: float, when: dt.datetime) -> None:
        raise NotImplementedError

    def snapshot(self) -> tuple[float, dict[str, tuple[float, float]]] | None:
        """Real account state as ``(cash, {symbol: (qty, avg_cost)})``.

        Returns None for brokers whose state already lives in ``LiveState``
        (the local paper broker). Alpaca returns the true account so the runner
        can size orders against real cash and positions.
        """
        return None

    def backfill(self, symbol: str) -> list[Bar]:
        """Recent daily history for a symbol, used once to warm up a strategy's
        lookback so it can trade from the first run instead of waiting weeks for
        history to accumulate one bar at a time. Empty by default."""
        return []

    def describe(self) -> str:
        return type(self).__name__


@dataclass
class LocalPaperBroker(LiveBroker):
    """Fake money, real (free) prices, state persisted to ``state``.

    Fills are modeled by the same ``PaperBroker`` the backtester uses, so a
    live run and a backtest treat costs identically.
    """

    feed: Feed
    state: LiveState
    broker: PaperBroker = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.broker is None:
            self.broker = PaperBroker()

    def latest_bar(self, symbol: str) -> Bar | None:
        return self.feed.latest_bar(symbol)

    def backfill(self, symbol: str) -> list[Bar]:
        from ..data import fetch_symbol

        try:
            return fetch_symbol(symbol)
        except Exception:  # noqa: BLE001 - warm-up is best-effort
            return []

    def position_qty(self, symbol: str) -> float:
        return self.state.portfolio.quantity(symbol)

    def equity(self) -> float:
        return self.state.equity()

    def submit(self, order: Order, ref_price: float, when: dt.datetime) -> None:
        self.broker.execute(self.state.portfolio, order, ref_price, when.date())


class AlpacaError(RuntimeError):
    pass


@dataclass
class AlpacaBroker(LiveBroker):
    """Trade a real Alpaca paper account over its REST API (no real money).

    Credentials come from the environment so keys never live in the repo:
        ALPACA_API_KEY_ID, ALPACA_API_SECRET_KEY
    Base URLs default to the paper endpoints. Uses only urllib, so it honors
    HTTP(S)_PROXY and needs no third-party SDK.
    """

    key_id: str = ""
    secret_key: str = ""
    base_url: str = "https://paper-api.alpaca.markets"
    data_url: str = "https://data.alpaca.markets"
    # Free Alpaca accounts must use the IEX feed; the default (SIP) needs a paid
    # data subscription and would 403. Override with ALPACA_DATA_FEED=sip if paid.
    data_feed: str = "iex"
    timeout: float = 20.0

    @classmethod
    def from_env(cls) -> "AlpacaBroker":
        key = os.environ.get("ALPACA_API_KEY_ID", "")
        secret = os.environ.get("ALPACA_API_SECRET_KEY", "")
        if not key or not secret:
            raise AlpacaError(
                "Set ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY to trade via Alpaca. "
                "Get free paper-trading keys at https://alpaca.markets."
            )
        base = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
        feed = os.environ.get("ALPACA_DATA_FEED", "iex")
        return cls(key_id=key, secret_key=secret, base_url=base, data_feed=feed)

    # --- low-level HTTP --------------------------------------------------
    def _request(self, method: str, url: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("APCA-API-KEY-ID", self.key_id)
        req.add_header("APCA-API-SECRET-KEY", self.secret_key)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
                text = resp.read().decode()
                return json.loads(text) if text else {}
        except urllib.error.HTTPError as exc:  # surface Alpaca's error message
            detail = exc.read().decode(errors="replace")
            raise AlpacaError(f"Alpaca {method} {url} -> {exc.code}: {detail}") from exc

    # --- LiveBroker interface -------------------------------------------
    def _daily_bars(self, symbol: str, limit: int) -> list[Bar]:
        """Recent completed daily bars from Alpaca (IEX feed by default).

        An explicit ``start`` is required — without it Alpaca returns only the
        most recent bar, which starves lookback-based strategies.
        """
        span_days = int(limit * 1.6) + 10  # calendar days to cover weekends/holidays
        start = (dt.date.today() - dt.timedelta(days=span_days)).isoformat()
        url = (f"{self.data_url}/v2/stocks/{symbol}/bars"
               f"?timeframe=1Day&start={start}&limit={limit}&adjustment=raw&feed={self.data_feed}")
        payload = self._request("GET", url)
        bars = []
        for b in payload.get("bars") or []:
            try:
                bars.append(Bar(
                    date=dt.date.fromisoformat(b["t"][:10]), symbol=symbol.upper(),
                    open=float(b["o"]), high=float(b["h"]), low=float(b["l"]),
                    close=float(b["c"]), volume=int(b.get("v", 0)),
                ))
            except (KeyError, ValueError):
                continue
        return bars

    def latest_bar(self, symbol: str) -> Bar | None:
        # An end-of-day bot wants the latest completed *daily* bar, not the last
        # minute bar, so read daily bars and take the most recent.
        bars = self._daily_bars(symbol, limit=2)
        return bars[-1] if bars else None

    def backfill(self, symbol: str) -> list[Bar]:
        try:
            return self._daily_bars(symbol, limit=120)
        except AlpacaError:
            return []

    def position_qty(self, symbol: str) -> float:
        try:
            pos = self._request("GET", f"{self.base_url}/v2/positions/{symbol}")
        except AlpacaError as exc:
            if "404" in str(exc):  # no open position for this symbol
                return 0.0
            raise
        return float(pos.get("qty", 0.0))

    def equity(self) -> float:
        acct = self._request("GET", f"{self.base_url}/v2/account")
        return float(acct.get("equity", 0.0))

    def snapshot(self) -> tuple[float, dict[str, tuple[float, float]]]:
        acct = self._request("GET", f"{self.base_url}/v2/account")
        cash = float(acct.get("cash", 0.0))
        positions_raw = self._request("GET", f"{self.base_url}/v2/positions")
        positions: dict[str, tuple[float, float]] = {}
        for pos in positions_raw if isinstance(positions_raw, list) else []:
            sym = pos["symbol"].upper()
            positions[sym] = (float(pos.get("qty", 0.0)), float(pos.get("avg_entry_price", 0.0)))
        return cash, positions

    def submit(self, order: Order, ref_price: float, when: dt.datetime) -> None:
        # Alpaca sizes buys/sells in shares; round to whole shares for market orders.
        qty = int(order.quantity)
        if qty <= 0:
            return
        body = {
            "symbol": order.symbol,
            "qty": str(qty),
            "side": order.side,
            "type": "market",
            "time_in_force": "day",
        }
        self._request("POST", f"{self.base_url}/v2/orders", body)

    def describe(self) -> str:
        return f"AlpacaBroker(paper, {self.base_url})"
