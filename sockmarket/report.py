"""Human-readable rendering of a backtest result."""

from __future__ import annotations

import csv
from pathlib import Path

from .engine import BacktestResult


def _pct(x: float) -> str:
    return f"{x * 100:+.2f}%"


def _money(x: float) -> str:
    return f"${x:,.2f}"


def render(result: BacktestResult) -> str:
    m = result.metrics
    bh = result.buy_hold_metrics
    p = result.portfolio

    lines: list[str] = []
    lines.append("=" * 60)
    lines.append(f"  Strategy: {result.strategy_name}")
    lines.append(f"  Period:   {result.dates[0]} -> {result.dates[-1]}  ({m.days} bars)")
    lines.append("=" * 60)
    lines.append(f"  Starting equity   {_money(m.starting_equity)}")
    lines.append(f"  Ending equity     {_money(m.ending_equity)}")
    lines.append(f"  Total return      {_pct(m.total_return)}")
    lines.append(f"  Annualized        {_pct(m.annualized_return)}")
    lines.append(f"  Volatility (ann)  {_pct(m.annualized_volatility)}")
    lines.append(f"  Sharpe            {m.sharpe:.2f}")
    lines.append(f"  Max drawdown      -{m.max_drawdown * 100:.2f}%")
    lines.append(f"  Trades            {m.num_trades}")
    lines.append(f"  Win rate          {m.win_rate * 100:.1f}%")
    lines.append(f"  Realized P&L      {_money(p.realized_pnl)}")
    lines.append(f"  Cash              {_money(p.cash)}")
    open_positions = {s: pos.quantity for s, pos in p.positions.items() if pos.quantity}
    if open_positions:
        held = ", ".join(f"{s}:{q:.2f}" for s, q in sorted(open_positions.items()))
        lines.append(f"  Open positions    {held}")

    if bh is not None:
        lines.append("-" * 60)
        lines.append(f"  Buy & hold return {_pct(bh.total_return)}  (Sharpe {bh.sharpe:.2f})")
        edge = m.total_return - bh.total_return
        verdict = "BEAT" if edge > 0 else "TRAILED"
        lines.append(f"  Vs buy & hold     {verdict} by {_pct(edge)}")
    lines.append("=" * 60)
    return "\n".join(lines)


def save_equity_csv(result: BacktestResult, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "strategy_equity", "buy_hold_equity"])
        for i, date in enumerate(result.dates):
            bh = result.buy_hold_curve[i] if i < len(result.buy_hold_curve) else ""
            w.writerow([date.isoformat(), f"{result.equity_curve[i]:.2f}", f"{bh:.2f}" if bh != "" else ""])


def save_trades_csv(result: BacktestResult, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "symbol", "side", "quantity", "price", "commission", "realized_pnl"])
        for t in result.portfolio.trades:
            w.writerow(
                [t.date.isoformat(), t.symbol, t.side, f"{t.quantity:.4f}",
                 f"{t.price:.4f}", f"{t.commission:.2f}", f"{t.realized_pnl:.2f}"]
            )
