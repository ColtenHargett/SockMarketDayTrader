"""Optional real-data fetcher (free, no API key, standard library only).

The backtester runs fully offline on the bundled ``data/sample_prices.csv``.
For real history, this pulls free daily bars from two sources and prefers
whichever answers:

- **Yahoo Finance** (JSON chart API) — reliable from cloud/CI IPs.
- **Stooq** (CSV) — a fallback; note Stooq often blocks datacenter IPs.

Both requests send a browser-like User-Agent, without which some hosts return
403/404 to the default urllib agent.

Usage:
    python -m sockmarket.data fetch AAPL MSFT --start 2022-01-01 --out data/real.csv
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import urllib.request
from pathlib import Path

from .market import Bar

STOOQ_URL = "https://stooq.com/q/d/l/?s={symbol}.us&i=d"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range}&interval=1d"
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def _http_get(url: str, timeout: float) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted URL)
        return resp.read().decode("utf-8", errors="replace")


def fetch_symbol_stooq(symbol: str, timeout: float = 20.0) -> list[Bar]:
    """Full daily history for one US symbol from Stooq (CSV)."""
    text = _http_get(STOOQ_URL.format(symbol=symbol.lower()), timeout)
    bars: list[Bar] = []
    for row in csv.DictReader(io.StringIO(text)):
        # Stooq columns: Date,Open,High,Low,Close,Volume
        if not row.get("Date") or row["Date"] == "Date":
            continue
        try:
            bars.append(
                Bar(
                    date=dt.date.fromisoformat(row["Date"]),
                    symbol=symbol.upper(),
                    open=float(row["Open"]), high=float(row["High"]), low=float(row["Low"]),
                    close=float(row["Close"]), volume=int(float(row.get("Volume") or 0)),
                )
            )
        except (ValueError, KeyError):
            continue
    return bars


def fetch_symbol_yahoo(symbol: str, timeout: float = 20.0, rng: str = "1y") -> list[Bar]:
    """Daily history for one symbol from Yahoo Finance's chart API (JSON)."""
    text = _http_get(YAHOO_URL.format(symbol=symbol.upper(), range=rng), timeout)
    return _parse_yahoo(text, symbol)


def _parse_yahoo(text: str, symbol: str) -> list[Bar]:
    payload = json.loads(text)
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        return []
    stamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    opens, highs = quote.get("open") or [], quote.get("high") or []
    lows, closes = quote.get("low") or [], quote.get("close") or []
    vols = quote.get("volume") or []
    bars: list[Bar] = []
    for i, ts in enumerate(stamps):
        try:
            c = closes[i]
            if c is None:
                continue  # Yahoo pads incomplete rows with nulls
            d = dt.datetime.fromtimestamp(ts, dt.timezone.utc).date()
            bars.append(Bar(
                date=d, symbol=symbol.upper(),
                open=float(opens[i] if opens[i] is not None else c),
                high=float(highs[i] if highs[i] is not None else c),
                low=float(lows[i] if lows[i] is not None else c),
                close=float(c),
                volume=int(vols[i] or 0) if i < len(vols) else 0,
            ))
        except (IndexError, ValueError, TypeError):
            continue
    return bars


def fetch_symbol(symbol: str, timeout: float = 20.0) -> list[Bar]:
    """Full daily history for one symbol, trying Yahoo first, then Stooq.

    Raises the last error only if *both* sources fail, so a single flaky host
    doesn't sink the request.
    """
    errors = []
    for source in (fetch_symbol_yahoo, fetch_symbol_stooq):
        try:
            bars = source(symbol, timeout=timeout)
            if bars:
                return bars
        except Exception as exc:  # noqa: BLE001 - try the next source
            errors.append(f"{source.__name__}: {exc}")
    if errors:
        raise RuntimeError(f"all data sources failed for {symbol}: {'; '.join(errors)}")
    return []


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
