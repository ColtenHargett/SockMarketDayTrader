# SockMarketDayTrader

A zero-dependency **paper-trading bot and backtester** in pure Python. It runs a
trading "brain" over historical price bars with fake money, executes trades
honestly (fees, slippage, no peeking at the future), and scores the result
against buy-and-hold — the only benchmark that matters.

The bot can **trade whenever it wants**: the brain is asked on *every* bar and
returns zero or more orders. Returning nothing is holding. Nothing is on a fixed
schedule.

```
$ python -m sockmarket run --strategy momentum

============================================================
  Strategy: momentum
  Period:   2023-01-03 -> 2024-12-06  (504 bars)
============================================================
  Starting equity   $100,000.00
  Ending equity     $136,516....
  Total return      +36.52%
  ...
  Vs buy & hold     BEAT by +43.30%
============================================================
```

> ⚠️ This is a learning/simulation tool. It trades **fake money only** and does
> not connect to any brokerage. Backtest results are not predictions — beating a
> synthetic sample says nothing about beating the real market.

## Quick start

No installation, no dependencies (Python 3.10+). From the repo root:

```bash
python -m sockmarket list                       # show available brains
python -m sockmarket run --strategy sma_crossover
python -m sockmarket compare                     # rank every brain on the same data
```

Useful flags for `run`/`compare`:

| flag | meaning |
|---|---|
| `--strategy NAME` | which brain to run (`run` only) |
| `--data path.csv` | use your own bars instead of the bundled sample |
| `--symbols SOCK YARN` | restrict to certain tickers |
| `--cash 100000` | starting fake cash |
| `--commission 1.0` | flat fee per trade |
| `--slippage 5` | slippage in basis points (5 = 0.05%) |
| `--save-equity out.csv` | write the equity curve |
| `--save-trades out.csv` | write the full trade log |

## How it's built

The system deliberately separates three concerns so you can swap any one of them:

1. **Signal / brain** — `sockmarket/strategy.py` + `sockmarket/strategies/`.
   A `Strategy.decide(context)` returns orders. `context.history` only ever
   contains bars up to *now*, so a brain physically cannot cheat.
2. **Accounting** — `sockmarket/portfolio.py` (cash, positions, realized/
   unrealized P&L) and `sockmarket/broker.py` (fills, fees, slippage,
   affordability checks). This is the "fake money" engine.
3. **Engine** — `sockmarket/engine.py` walks the market bar by bar, and
   `sockmarket/metrics.py` scores the run (return, Sharpe, max drawdown, win
   rate) against a buy-and-hold benchmark.

### Built-in brains

| name | idea |
|---|---|
| `buy_and_hold` | the control — equal-weight basket, held to the end |
| `sma_crossover` | trend follower; trades on fast/slow moving-average crosses |
| `momentum` | holds symbols with positive trailing return |
| `mean_reversion` | buys dips (low z-score), sells the snap-back |
| `predictor` | turns an ML model's per-bar `Signal` into positions |

## Plugging in your own ML predictor

Keep the *prediction* separate from the *trading*. Your model only answers one
question per symbol per bar — a `Signal(direction, confidence)` — and the
framework handles sizing, exits, and accounting:

```python
from sockmarket.engine import Engine
from sockmarket.market import load_csv
from sockmarket.strategies.predictor import SignalPredictor, Signal, PredictorStrategy

class MyModel(SignalPredictor):
    def predict(self, symbol, history):        # history: list[Bar], oldest first, no future
        # ... run your trained model on the bars ...
        return Signal(direction=+1, confidence=0.7)   # +1 buy, 0 flat, -1 avoid

bars = load_csv("data/sample_prices.csv")
result = Engine(bars, PredictorStrategy(MyModel())).run()
print(result.metrics.total_return)
```

Because the predictor never sees cash or positions, it can't accidentally cheat,
and you can unit-test it on its own. This is where the model from
[your Stock Market Predictor](https://github.com/ColtenHargett/portfolio/tree/main/AI%20and%20Machine%20Learning/Stock%20Market%20Predictor)
drops in.

## Forward / live trading (the real experiment)

A backtest only shows a strategy *would have* worked on the past. The honest test
of "can it make money" is **forward paper trading**: run it live, going forward,
on real prices and real market hours, and watch it for months. That lives in
`sockmarket/live/`.

Two brokers behind one interface (`LiveBroker`):

- **`local`** — our own paper engine on free daily data, with state persisted to
  `data/live_state.json`. Zero signup. Best for a once-a-day bot.
- **`alpaca`** — a real [Alpaca](https://alpaca.markets) **paper** account: real
  fills, real-time data, real market clock, still no real money. The realistic
  path. Set `ALPACA_API_KEY_ID` and `ALPACA_API_SECRET_KEY` (free keys).

Two ways to run:

```bash
# One decision tick — what a scheduler/cron calls once per day after the close:
python -m sockmarket live --broker local --mode once \
    --strategy momentum --symbols AAPL MSFT NVDA --ignore-hours

# Continuous real-time loop — ticks while the US market is open, sleeps otherwise:
python -m sockmarket live --broker alpaca --mode loop \
    --strategy momentum --symbols AAPL MSFT NVDA --poll 60
```

`--ignore-hours` is for the end-of-day bot: it acts on the latest *completed*
daily bar, so the market being closed at run time is fine. Drop it for the
intraday loop, which trades only during the 9:30–16:00 ET session (holidays and
half-days included, via `sockmarket/live/clock.py`).

### Running it long-term, hands-off

This bot needs a persistent home — a laptop that's on, a cheap VM, or best of
all **GitHub Actions**. The repo ships `.github/workflows/live-trade.yml`, which
runs the bot once every weekday after the close and commits the updated
portfolio and decision log back to the repo — so your entire forward track
record accumulates in git history, for free, with no server. For the real Alpaca
account, add the two API keys as repository secrets and flip the commented block
in that workflow.

> Reality check: expect live results to be **worse** than the backtest — that gap
> is exactly what this experiment measures. Give it months before trusting any
> conclusion, and never move to real money on the strength of a paper run alone.

## Using real data

The repo ships with a synthetic sample so everything runs offline. When you have
network access, pull free daily bars from Stooq (no API key):

```bash
python -m sockmarket.data fetch AAPL MSFT --start 2022-01-01 --out data/real.csv
python -m sockmarket run --strategy momentum --data data/real.csv --symbols AAPL MSFT
```

## Development

```bash
pip install -r requirements-dev.txt   # just pytest
pytest                                # 21 tests, runs in <1s
```

## Roadmap ideas

- Sentiment/news signals via an LLM feeding into a `SignalPredictor`
- Portfolio-level risk controls (max position, per-trade stop-loss, volatility targeting)
- Walk-forward validation to catch overfitting
- Limit orders and partial-fill handling on the Alpaca path
- A small dashboard rendering `data/live_state.json` (equity curve + open positions)

## License

MIT — see `LICENSE`.
