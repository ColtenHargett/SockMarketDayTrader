"""Command-line interface: run a backtest, compare strategies, or list brains.

Examples:
    python -m sockmarket run --strategy sma_crossover
    python -m sockmarket run --strategy predictor --data data/real.csv --symbols AAPL
    python -m sockmarket compare
    python -m sockmarket list
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .broker import PaperBroker
from .engine import Engine
from .market import load_csv
from .report import render, save_equity_csv, save_trades_csv
from .strategies import REGISTRY

DEFAULT_DATA = Path(__file__).resolve().parent.parent / "data" / "sample_prices.csv"


def _build_strategy(name: str):
    if name not in REGISTRY:
        raise SystemExit(
            f"unknown strategy {name!r}. Available: {', '.join(sorted(REGISTRY))}"
        )
    return REGISTRY[name]()


def _load_bars(data: str | None, symbols: list[str] | None):
    path = Path(data) if data else DEFAULT_DATA
    if not path.exists():
        raise SystemExit(f"data file not found: {path}")
    return load_csv(path, symbols)


def cmd_run(args: argparse.Namespace) -> int:
    bars = _load_bars(args.data, args.symbols)
    strategy = _build_strategy(args.strategy)
    broker = PaperBroker(
        commission_per_trade=args.commission,
        slippage_bps=args.slippage,
        allow_fractional=not args.whole_shares,
    )
    engine = Engine(bars, strategy, broker=broker, starting_cash=args.cash)
    result = engine.run()
    print(render(result))

    if args.save_equity:
        save_equity_csv(result, args.save_equity)
        print(f"equity curve -> {args.save_equity}")
    if args.save_trades:
        save_trades_csv(result, args.save_trades)
        print(f"trade log    -> {args.save_trades}")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    bars = _load_bars(args.data, args.symbols)
    names = args.strategies or sorted(REGISTRY)
    rows = []
    for name in names:
        engine = Engine(
            bars,
            _build_strategy(name),
            broker=PaperBroker(commission_per_trade=args.commission, slippage_bps=args.slippage),
            starting_cash=args.cash,
        )
        r = engine.run()
        rows.append((name, r.metrics))

    bench = rows[0][1] if rows else None
    header = f"{'strategy':<16}{'return':>12}{'annual':>10}{'sharpe':>9}{'maxDD':>9}{'trades':>8}"
    print(header)
    print("-" * len(header))
    for name, m in sorted(rows, key=lambda x: x[1].total_return, reverse=True):
        print(
            f"{name:<16}{m.total_return * 100:>11.2f}%{m.annualized_return * 100:>9.2f}%"
            f"{m.sharpe:>9.2f}{m.max_drawdown * 100:>8.2f}%{m.num_trades:>8}"
        )
    return 0


def cmd_live(args: argparse.Namespace) -> int:
    from .live import LiveConfig, LocalPaperBroker, StooqFeed, run_loop, run_once
    from .live.state import LiveState

    strategy = _build_strategy(args.strategy)

    if args.broker == "alpaca":
        from .live.brokers import AlpacaBroker, AlpacaError

        try:
            broker = AlpacaBroker.from_env()
        except AlpacaError as exc:
            raise SystemExit(str(exc))
    else:
        state = LiveState.load(args.state, starting_cash=args.cash)
        broker = LocalPaperBroker(feed=StooqFeed(), state=state)

    config = LiveConfig(
        symbols=[s.upper() for s in args.symbols] if args.symbols else ["AAPL"],
        strategy=strategy,
        broker=broker,
        state_path=args.state,
        require_market_open=not args.ignore_hours,
    )

    if args.mode == "once":
        result = run_once(config, starting_cash=args.cash)
        return 0 if result is not None else 1
    run_loop(config, poll_seconds=args.poll, starting_cash=args.cash)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    print("Available strategies:")
    for name in sorted(REGISTRY):
        doc = (REGISTRY[name].__doc__ or "").strip().splitlines()
        summary = doc[0] if doc else ""
        print(f"  {name:<16} {summary}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sockmarket", description="Paper-trading bot & backtester.")
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp):
        sp.add_argument("--data", default=None, help="CSV of bars (default: bundled sample)")
        sp.add_argument("--symbols", nargs="*", default=None, help="restrict to these symbols")
        sp.add_argument("--cash", type=float, default=100_000.0, help="starting cash")
        sp.add_argument("--commission", type=float, default=0.0, help="flat fee per trade")
        sp.add_argument("--slippage", type=float, default=0.0, help="slippage in basis points")

    run = sub.add_parser("run", help="run one strategy")
    add_common(run)
    run.add_argument("--strategy", default="sma_crossover")
    run.add_argument("--whole-shares", action="store_true", help="disallow fractional shares")
    run.add_argument("--save-equity", default=None, help="write equity curve CSV here")
    run.add_argument("--save-trades", default=None, help="write trade log CSV here")
    run.set_defaults(func=cmd_run)

    comp = sub.add_parser("compare", help="compare several strategies on the same data")
    add_common(comp)
    comp.add_argument("--strategies", nargs="*", default=None, help="subset to compare")
    comp.set_defaults(func=cmd_compare)

    live = sub.add_parser("live", help="forward-trade in real time (paper money)")
    live.add_argument("--strategy", default="momentum")
    live.add_argument("--symbols", nargs="*", default=None, help="tickers to trade (default AAPL)")
    live.add_argument("--broker", choices=["local", "alpaca"], default="local",
                      help="'local' = free data + our paper engine; 'alpaca' = real paper account")
    live.add_argument("--mode", choices=["once", "loop"], default="once",
                      help="'once' = single tick (for cron); 'loop' = continuous real-time")
    live.add_argument("--cash", type=float, default=100_000.0, help="starting cash (local broker)")
    live.add_argument("--state", default="data/live_state.json", help="state file path (local broker)")
    live.add_argument("--poll", type=float, default=60.0, help="seconds between ticks in loop mode")
    live.add_argument("--ignore-hours", action="store_true",
                      help="act on the latest bar even when the market is closed (for testing)")
    live.set_defaults(func=cmd_live)

    lst = sub.add_parser("list", help="list available strategies")
    lst.set_defaults(func=cmd_list)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
