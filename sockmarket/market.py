"""Market data: a single price Bar and sources that produce a stream of bars.

Everything here is standard-library only. A ``Bar`` is one OHLCV row for one
symbol on one date. A data source yields bars in chronological order, which is
all the backtest engine needs.
"""

from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Bar:
    """One OHLCV price bar for a single symbol."""

    date: dt.date
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: int

    @classmethod
    def from_row(cls, row: dict) -> "Bar":
        return cls(
            date=dt.date.fromisoformat(row["date"]),
            symbol=row["symbol"].strip().upper(),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=int(float(row["volume"])),
        )


def load_csv(path: str | Path, symbols: list[str] | None = None) -> list[Bar]:
    """Load bars from a CSV with columns: date,symbol,open,high,low,close,volume.

    Bars are returned sorted by (date, symbol). Optionally filter to ``symbols``.
    """
    path = Path(path)
    wanted = {s.upper() for s in symbols} if symbols else None
    bars: list[Bar] = []
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            bar = Bar.from_row(row)
            if wanted is None or bar.symbol in wanted:
                bars.append(bar)
    bars.sort(key=lambda b: (b.date, b.symbol))
    return bars


def group_by_date(bars: list[Bar]) -> list[tuple[dt.date, dict[str, Bar]]]:
    """Collapse a flat bar list into ``[(date, {symbol: Bar}), ...]`` in order.

    The engine walks the market one date at a time; each step it may see one or
    more symbols. Missing symbols on a given date simply aren't in the dict.
    """
    by_date: dict[dt.date, dict[str, Bar]] = {}
    for bar in bars:
        by_date.setdefault(bar.date, {})[bar.symbol] = bar
    return [(d, by_date[d]) for d in sorted(by_date)]
