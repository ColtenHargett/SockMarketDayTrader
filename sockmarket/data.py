"""Optional real-data fetcher.

The backtester runs fully offline on the bundled ``data/sample_prices.csv``.
When you have network access and want real history, this pulls free daily bars
from Stooq (no API key required) using only the standard library, and can cache
them to a CSV the rest of the tool already understands.

Usage:
    python -m sockmarket.data fetch AAPL MSFT --start 2022-01-01 --out data/real.csv
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import urllib.request
from pathlib import Path

from .market import Bar

STOOQ_URL = "https://stooq.com/q/d/l/?s={symbol}.us&i=d"


def fetch_symbol(symbol: str, timeout: float = 20.0) -> list[Bar]:
    """Fetch full daily history for one US symbol from Stooq.

    Raises urllib errors on network failure — callers should fall back to the
    bundled sample data. Honors HTTP(S)_PROXY via urllib's default handlers.
    """
    url = STOOQ_URL.format(symbol=symbol.lower())
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (trusted URL)
        text = resp.read().decode("utf-8", errors="replace")

    bars: list[Bar] = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        # Stooq columns: Date,Open,High,Low,Close,Volume
        if not row.get("Date") or row["Date"] == "Date":
            continue
        try:
            bars.append(
                Bar(
                    date=dt.date.fromisoformat(row["Date"]),
                    symbol=symbol.upper(),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=int(float(row.get("Volume") or 0)),
                )
            )
        except (ValueError, KeyError):
            continue
    return bars


def fetch(
    symbols: list[str],
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> list[Bar]:
    bars: list[Bar] = []
    for symbol in symbols:
        for bar in fetch_symbol(symbol):
            if start and bar.date < start:
                continue
            if end and bar.date > end:
                continue
            bars.append(bar)
    bars.sort(key=lambda b: (b.date, b.symbol))
    return bars


def save_csv(bars: list[Bar], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "symbol", "open", "high", "low", "close", "volume"])
        for b in bars:
            w.writerow([b.date.isoformat(), b.symbol, b.open, b.high, b.low, b.close, b.volume])


def _main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Fetch free daily bars from Stooq.")
    p.add_argument("command", choices=["fetch"])
    p.add_argument("symbols", nargs="+")
    p.add_argument("--start", type=dt.date.fromisoformat, default=None)
    p.add_argument("--end", type=dt.date.fromisoformat, default=None)
    p.add_argument("--out", default="data/real.csv")
    args = p.parse_args(argv)

    try:
        bars = fetch(args.symbols, args.start, args.end)
    except Exception as exc:  # noqa: BLE001 - surface any network/parse failure plainly
        print(f"fetch failed: {exc}")
        print("Tip: the backtester still works offline on data/sample_prices.csv")
        return 1

    if not bars:
        print("no bars returned (symbol unknown or no data in range)")
        return 1
    save_csv(bars, args.out)
    print(f"saved {len(bars)} bars for {', '.join(args.symbols)} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
