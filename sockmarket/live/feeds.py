"""Live price feeds: fetch the latest bar for a symbol, right now.

- ``StooqFeed``: free daily bars, no API key (good for a once-a-day bot).
- ``ReplayFeed``: replays a fixed list of bars, for tests and dry runs.

Intraday/real-time bars come from Alpaca instead — see ``AlpacaBroker`` in
``brokers.py``, which doubles as a real-time feed when you trade through Alpaca.
"""

from __future__ import annotations

from ..data import fetch_symbol
from ..market import Bar


class Feed:
    """Interface: return the most recent bar for ``symbol``, or None."""

    def latest_bar(self, symbol: str) -> Bar | None:
        raise NotImplementedError


class StooqFeed(Feed):
    """Latest completed daily bar from Stooq (free, no key)."""

    def latest_bar(self, symbol: str) -> Bar | None:
        bars = fetch_symbol(symbol)
        return bars[-1] if bars else None


class ReplayFeed(Feed):
    """Hands out pre-supplied bars one call at a time — deterministic for tests.

    ``bars`` maps symbol -> list of Bar (oldest first). Each ``latest_bar`` call
    advances that symbol's cursor by one.
    """

    def __init__(self, bars: dict[str, list[Bar]]) -> None:
        self._bars = {s: list(b) for s, b in bars.items()}
        self._idx = {s: 0 for s in bars}

    def latest_bar(self, symbol: str) -> Bar | None:
        seq = self._bars.get(symbol, [])
        i = self._idx.get(symbol, 0)
        if i >= len(seq):
            return None
        self._idx[symbol] = i + 1
        return seq[i]

    def exhausted(self) -> bool:
        return all(self._idx.get(s, 0) >= len(b) for s, b in self._bars.items())
