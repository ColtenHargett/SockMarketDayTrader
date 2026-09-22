"""Persistent live-trading state (JSON on disk).

A live bot must not forget what it owns between runs — especially the daily
cron bot, where every run is a brand-new process. This stores the portfolio,
a bounded rolling history of bars per symbol (so strategies still get their
lookback), and the equity curve, in a single human-readable JSON file.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path

from ..market import Bar
from ..portfolio import Portfolio, Position, Trade

HISTORY_LIMIT = 400  # bars kept per symbol; plenty for any built-in strategy


@dataclass
class LiveState:
    starting_cash: float = 100_000.0
    portfolio: Portfolio = field(default_factory=lambda: Portfolio(100_000.0))
    history: dict[str, list[Bar]] = field(default_factory=dict)
    equity_log: list[tuple[str, float]] = field(default_factory=list)  # (iso datetime, equity)
    last_run: str | None = None

    # --- history helpers -------------------------------------------------
    def record_bar(self, bar: Bar) -> bool:
        """Append ``bar`` if it's newer than the latest for that symbol.

        Returns True if it was a new bar (so the caller knows to act), False if
        it's a duplicate of one already seen (same or older date).
        """
        hist = self.history.setdefault(bar.symbol, [])
        if hist and bar.date <= hist[-1].date:
            return False
        hist.append(bar)
        if len(hist) > HISTORY_LIMIT:
            del hist[: len(hist) - HISTORY_LIMIT]
        return True

    def latest_prices(self) -> dict[str, float]:
        return {s: h[-1].close for s, h in self.history.items() if h}

    def equity(self) -> float:
        return self.portfolio.equity(self.latest_prices())

    def log_equity(self, when: dt.datetime) -> None:
        self.equity_log.append((when.isoformat(), self.equity()))

    # --- persistence -----------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "starting_cash": self.starting_cash,
            "portfolio": {
                "starting_cash": self.portfolio.starting_cash,
                "cash": self.portfolio.cash,
                "positions": {
                    s: {"quantity": p.quantity, "avg_cost": p.avg_cost}
                    for s, p in self.portfolio.positions.items()
                },
                "trades": [
                    {
                        "date": t.date.isoformat(),
                        "symbol": t.symbol,
                        "side": t.side,
                        "quantity": t.quantity,
                        "price": t.price,
                        "commission": t.commission,
                        "realized_pnl": t.realized_pnl,
                    }
                    for t in self.portfolio.trades
                ],
            },
            "history": {
                s: [[b.date.isoformat(), b.open, b.high, b.low, b.close, b.volume] for b in bars]
                for s, bars in self.history.items()
            },
            "equity_log": [[ts, eq] for ts, eq in self.equity_log],
            "last_run": self.last_run,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LiveState":
        pdata = data.get("portfolio", {})
        portfolio = Portfolio(starting_cash=pdata.get("starting_cash", data.get("starting_cash", 100_000.0)))
        portfolio.cash = pdata.get("cash", portfolio.starting_cash)
        portfolio.positions = {
            s: Position(quantity=pv["quantity"], avg_cost=pv["avg_cost"])
            for s, pv in pdata.get("positions", {}).items()
        }
        portfolio.trades = [
            Trade(
                date=dt.date.fromisoformat(t["date"]),
                symbol=t["symbol"],
                side=t["side"],
                quantity=t["quantity"],
                price=t["price"],
                commission=t.get("commission", 0.0),
                realized_pnl=t.get("realized_pnl", 0.0),
            )
            for t in pdata.get("trades", [])
        ]
        history = {
            s: [
                Bar(
                    date=dt.date.fromisoformat(row[0]),
                    symbol=s,
                    open=row[1], high=row[2], low=row[3], close=row[4], volume=int(row[5]),
                )
                for row in rows
            ]
            for s, rows in data.get("history", {}).items()
        }
        equity_log = [(ts, eq) for ts, eq in data.get("equity_log", [])]
        return cls(
            starting_cash=data.get("starting_cash", 100_000.0),
            portfolio=portfolio,
            history=history,
            equity_log=equity_log,
            last_run=data.get("last_run"),
        )

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2))
        tmp.replace(path)  # atomic swap so a crash mid-write can't corrupt state

    @classmethod
    def load(cls, path: str | Path, starting_cash: float = 100_000.0) -> "LiveState":
        path = Path(path)
        if not path.exists():
            return cls(starting_cash=starting_cash, portfolio=Portfolio(starting_cash))
        return cls.from_dict(json.loads(path.read_text()))
