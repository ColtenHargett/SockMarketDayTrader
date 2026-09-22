"""Performance metrics computed from an equity curve.

Pure standard library. Everything an honest backtest report needs to answer the
only question that matters: did the brain actually beat just holding?
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

TRADING_DAYS_PER_YEAR = 252


@dataclass
class Metrics:
    starting_equity: float
    ending_equity: float
    total_return: float  # fraction, e.g. 0.15 == +15%
    annualized_return: float
    annualized_volatility: float
    sharpe: float
    max_drawdown: float  # fraction, e.g. 0.20 == -20% peak-to-trough
    num_trades: int
    win_rate: float  # fraction of closing (sell) trades that booked a profit
    days: int

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _daily_returns(equity: list[float]) -> list[float]:
    out = []
    for prev, cur in zip(equity, equity[1:]):
        out.append((cur / prev) - 1.0 if prev else 0.0)
    return out


def _max_drawdown(equity: list[float]) -> float:
    peak = -math.inf
    worst = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1.0)
    return -worst  # report as a positive fraction


def compute(
    dates: list[dt.date],
    equity: list[float],
    realized_pnls: list[float],
    num_trades: int,
    risk_free_rate: float = 0.0,
) -> Metrics:
    if len(equity) < 2:
        start = equity[0] if equity else 0.0
        return Metrics(start, start, 0, 0, 0, 0, 0, num_trades, 0, len(equity))

    start, end = equity[0], equity[-1]
    total_return = (end / start) - 1.0 if start else 0.0

    span_days = max(1, (dates[-1] - dates[0]).days)
    years = span_days / 365.25
    annualized_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0.0

    rets = _daily_returns(equity)
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets) if len(rets) > 1 else 0.0
    std = math.sqrt(var)
    ann_vol = std * math.sqrt(TRADING_DAYS_PER_YEAR)

    daily_rf = risk_free_rate / TRADING_DAYS_PER_YEAR
    sharpe = 0.0
    if std > 0:
        sharpe = ((mean - daily_rf) / std) * math.sqrt(TRADING_DAYS_PER_YEAR)

    sells = [p for p in realized_pnls if p != 0.0]
    wins = sum(1 for p in sells if p > 0)
    win_rate = wins / len(sells) if sells else 0.0

    return Metrics(
        starting_equity=start,
        ending_equity=end,
        total_return=total_return,
        annualized_return=annualized_return,
        annualized_volatility=ann_vol,
        sharpe=sharpe,
        max_drawdown=_max_drawdown(equity),
        num_trades=num_trades,
        win_rate=win_rate,
        days=len(equity),
    )
