"""Render the live trading state as a standalone HTML dashboard.

Reads a ``LiveState`` (the JSON the live bot writes) and produces a single,
self-contained ``dashboard.html`` — no external scripts, no build step — with:

- stat tiles (equity, total return, edge vs buy & hold, max drawdown, trades),
- an inline-SVG equity curve of the strategy vs a buy-and-hold benchmark,
  with a hover crosshair + tooltip,
- tables of open positions and recent trades.

Colors come from the validated data-viz palette: the strategy is series-1 (blue),
the benchmark series-2 (orange); light and dark themes are both defined.
"""

from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path

from .live.state import LiveState
from .metrics import compute


# --- data shaping --------------------------------------------------------
def _buy_hold_series(state: LiveState) -> list[tuple[str, float]]:
    """Equal-weight buy-and-hold value per date, from the recorded bar history.

    Mirrors the backtester's benchmark so the live comparison is apples-to-apples.
    """
    history = state.history
    symbols = sorted(history)
    if not symbols:
        return []
    starting = state.starting_cash
    alloc = starting / len(symbols)

    shares: dict[str, float] = {}
    for s in symbols:
        if history[s]:
            shares[s] = alloc / history[s][0].close

    # Union of all dates across symbols, in order.
    dates = sorted({b.date for s in symbols for b in history[s]})
    last_close: dict[str, float] = {}
    idx: dict[str, int] = {s: 0 for s in symbols}
    curve: list[tuple[str, float]] = []
    for d in dates:
        for s in symbols:
            bars = history[s]
            while idx[s] < len(bars) and bars[idx[s]].date <= d:
                last_close[s] = bars[idx[s]].close
                idx[s] += 1
        value = sum(shares.get(s, 0.0) * last_close.get(s, 0.0) for s in symbols)
        curve.append((d.isoformat(), value))
    return curve


def _positions_table(state: LiveState) -> list[dict]:
    prices = state.latest_prices()
    rows = []
    for sym, pos in sorted(state.portfolio.positions.items()):
        if pos.quantity <= 0:
            continue
        last = prices.get(sym, pos.avg_cost)
        value = pos.quantity * last
        unreal = (last - pos.avg_cost) * pos.quantity
        rows.append({
            "symbol": sym,
            "qty": pos.quantity,
            "avg_cost": pos.avg_cost,
            "last": last,
            "value": value,
            "unrealized": unreal,
        })
    return rows


def _build_payload(state: LiveState, title: str) -> dict:
    # Strategy curve = the full equity log (dates are market dates).
    strat = [(ts[:10], eq) for ts, eq in state.equity_log]
    raw_eq = [eq for _, eq in strat]
    full_dates = [dt.date.fromisoformat(ts) for ts, _ in strat]
    realized = [t.realized_pnl for t in state.portfolio.trades]
    m = compute(full_dates, raw_eq, realized, len(state.portfolio.trades)) if len(raw_eq) >= 2 else None

    # Benchmark: prefer the one tracked in state (lifetime-aligned with the
    # strategy, tick for tick); fall back to reconstructing from bar history for
    # states written before benchmark tracking existed.
    if state.benchmark_log:
        bench = [(ts[:10], v) for ts, v in state.benchmark_log]
    else:
        bench = [(d, v) for d, v in _buy_hold_series(state)]
        if bench and raw_eq:  # align the shorter reconstructed window to the tail
            k = min(len(bench), len(raw_eq))
            bench = bench[len(bench) - k:]
            strat = strat[len(strat) - k:]

    bench_return = (bench[-1][1] / bench[0][1] - 1.0) if len(bench) >= 2 and bench[0][1] else 0.0
    strat_window_return = (strat[-1][1] / strat[0][1] - 1.0) if len(strat) >= 2 and strat[0][1] else 0.0
    current_equity = raw_eq[-1] if raw_eq else state.equity()

    stats = {
        "starting_cash": state.starting_cash,
        "current_equity": current_equity,
        "total_return": (m.total_return if m else 0.0),
        "bench_return": bench_return,
        "edge": strat_window_return - bench_return,
        "max_drawdown": (m.max_drawdown if m else 0.0),
        "sharpe": (m.sharpe if m else 0.0),
        "num_trades": len(state.portfolio.trades),
        "realized_pnl": state.portfolio.realized_pnl,
        "cash": state.portfolio.cash,
        "last_run": state.last_run,
    }

    trades = [
        {
            "date": t.date.isoformat(), "symbol": t.symbol, "side": t.side,
            "qty": round(t.quantity, 4), "price": round(t.price, 2),
            "realized": round(t.realized_pnl, 2),
        }
        for t in state.portfolio.trades[-25:][::-1]  # most recent first
    ]

    return {
        "title": title,
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "strategy": strat,
        "benchmark": bench,
        "stats": stats,
        "positions": _positions_table(state),
        "trades": trades,
    }


# --- HTML rendering ------------------------------------------------------
def _money(x: float) -> str:
    return f"${x:,.2f}"


def _money0(x: float) -> str:
    return f"${x:,.0f}"


def _pct(x: float) -> str:
    return f"{x * 100:+.2f}%"


def _stat_tiles(stats: dict) -> str:
    def delta_class(x: float) -> str:
        return "up" if x > 0 else ("down" if x < 0 else "flat")

    tiles = [
        ("Equity", _money0(stats["current_equity"]), "", ""),
        ("Total return", _pct(stats["total_return"]), delta_class(stats["total_return"]),
         f"from {_money0(stats['starting_cash'])}"),
        ("vs Buy &amp; Hold", _pct(stats["edge"]), delta_class(stats["edge"]),
         f"B&amp;H {_pct(stats['bench_return'])}"),
        ("Max drawdown", f"-{stats['max_drawdown'] * 100:.2f}%",
         "down" if stats["max_drawdown"] > 0 else "flat", ""),
        ("Trades", str(stats["num_trades"]), "",
         f"realized {_money0(stats['realized_pnl'])}"),
        ("Cash", _money0(stats["cash"]), "", ""),
    ]
    cells = []
    for label, value, cls, sub in tiles:
        sub_html = f'<div class="tile-sub">{sub}</div>' if sub else ""
        cells.append(
            f'<div class="tile"><div class="tile-label">{label}</div>'
            f'<div class="tile-value {cls}">{value}</div>{sub_html}</div>'
        )
    return '<div class="tiles">' + "".join(cells) + "</div>"


def _positions_html(rows: list[dict]) -> str:
    if not rows:
        return '<p class="empty">No open positions.</p>'
    body = []
    for r in rows:
        u = r["unrealized"]
        ucls = "up" if u > 0 else ("down" if u < 0 else "flat")
        body.append(
            f"<tr><td>{html.escape(r['symbol'])}</td>"
            f"<td class='num'>{r['qty']:.2f}</td>"
            f"<td class='num'>{_money(r['avg_cost'])}</td>"
            f"<td class='num'>{_money(r['last'])}</td>"
            f"<td class='num'>{_money(r['value'])}</td>"
            f"<td class='num {ucls}'>{_money(u)}</td></tr>"
        )
    return (
        "<table><thead><tr><th>Symbol</th><th class='num'>Qty</th>"
        "<th class='num'>Avg cost</th><th class='num'>Last</th>"
        "<th class='num'>Value</th><th class='num'>Unrealized</th></tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
    )


def _trades_html(rows: list[dict]) -> str:
    if not rows:
        return '<p class="empty">No trades yet.</p>'
    body = []
    for r in rows:
        rl = r["realized"]
        rcls = "up" if rl > 0 else ("down" if rl < 0 else "flat")
        side_cls = "buy" if r["side"] == "buy" else "sell"
        body.append(
            f"<tr><td>{html.escape(r['date'])}</td>"
            f"<td>{html.escape(r['symbol'])}</td>"
            f"<td><span class='side {side_cls}'>{html.escape(r['side'])}</span></td>"
            f"<td class='num'>{r['qty']:.2f}</td>"
            f"<td class='num'>{_money(r['price'])}</td>"
            f"<td class='num {rcls}'>{_money(rl) if rl else '—'}</td></tr>"
        )
    return (
        "<table><thead><tr><th>Date</th><th>Symbol</th><th>Side</th>"
        "<th class='num'>Qty</th><th class='num'>Price</th>"
        "<th class='num'>Realized</th></tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
    )


def render_dashboard(state: LiveState, title: str = "SockMarket — Live Track Record") -> str:
    payload = _build_payload(state, title)
    data_json = json.dumps(payload)
    tiles = _stat_tiles(payload["stats"])
    positions = _positions_html(payload["positions"])
    trades = _trades_html(payload["trades"])
    gen = html.escape(payload["generated"])
    last_run = html.escape(str(payload["stats"]["last_run"] or "never"))
    has_curve = len(payload["strategy"]) >= 2

    chart_section = (
        '<div class="chart-wrap"><svg id="chart" role="img" '
        'aria-label="Equity curve of the strategy versus buy and hold"></svg>'
        '<div id="tooltip" class="tooltip" hidden></div></div>'
        if has_curve else
        '<p class="empty">No equity history yet — the chart appears after the '
        'bot has run for a couple of days.</p>'
    )

    return _TEMPLATE.replace("__TITLE__", html.escape(title)) \
        .replace("__TILES__", tiles) \
        .replace("__CHART__", chart_section) \
        .replace("__POSITIONS__", positions) \
        .replace("__TRADES__", trades) \
        .replace("__GENERATED__", gen) \
        .replace("__LASTRUN__", last_run) \
        .replace("__DATA__", data_json)


def save(state: LiveState, path: str | Path,
         title: str = "SockMarket — Live Track Record") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_dashboard(state, title))
    return path


def build_from_file(state_path: str | Path, out_path: str | Path) -> Path:
    state = LiveState.load(state_path)
    return save(state, out_path)


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root {
    color-scheme: light;
    --plane: #f9f9f7; --surface: #fcfcfb;
    --text-primary: #0b0b0b; --text-secondary: #52514e; --muted: #898781;
    --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10);
    --series-1: #2a78d6; --series-2: #eb6834;
    --up: #006300; --down: #d03b3b;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      color-scheme: dark;
      --plane: #0d0d0d; --surface: #1a1a19;
      --text-primary: #ffffff; --text-secondary: #c3c2b7; --muted: #898781;
      --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
      --series-1: #3987e5; --series-2: #d95926;
      --up: #0ca30c; --down: #d03b3b;
    }
  }
  :root[data-theme="dark"] {
    color-scheme: dark;
    --plane: #0d0d0d; --surface: #1a1a19;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
    --series-1: #3987e5; --series-2: #d95926;
    --up: #0ca30c; --down: #d03b3b;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--plane); color: var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    line-height: 1.45;
  }
  .container { max-width: 1000px; margin: 0 auto; padding: 24px 16px 64px; }
  header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px 16px; margin-bottom: 4px; }
  h1 { font-size: 1.4rem; margin: 0; }
  .meta { color: var(--muted); font-size: 0.82rem; }
  .disclaimer { color: var(--muted); font-size: 0.78rem; margin: 6px 0 20px; }
  .tiles {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px; margin-bottom: 24px;
  }
  .tile {
    background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    padding: 14px 16px;
  }
  .tile-label { color: var(--text-secondary); font-size: 0.8rem; }
  .tile-value { font-size: 1.35rem; font-weight: 650; margin-top: 4px; white-space: nowrap; font-variant-numeric: tabular-nums; }
  .tile-sub { color: var(--muted); font-size: 0.76rem; margin-top: 2px; }
  .up { color: var(--up); } .down { color: var(--down); }
  .card {
    background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    padding: 18px; margin-bottom: 22px;
  }
  .card h2 { font-size: 1rem; margin: 0 0 14px; }
  .legend { display: flex; gap: 18px; margin: 0 0 10px; font-size: 0.85rem; color: var(--text-secondary); }
  .legend .key { display: inline-flex; align-items: center; gap: 6px; }
  .swatch { width: 14px; height: 3px; border-radius: 2px; display: inline-block; }
  .chart-wrap { position: relative; width: 100%; }
  svg#chart { width: 100%; height: 340px; display: block; }
  .tooltip {
    position: absolute; pointer-events: none; background: var(--surface);
    border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px;
    font-size: 0.78rem; box-shadow: 0 4px 14px rgba(0,0,0,0.14);
    transform: translate(-50%, calc(-100% - 12px)); white-space: nowrap; z-index: 5;
  }
  .tooltip .t-date { color: var(--muted); margin-bottom: 4px; }
  .tooltip .t-row { display: flex; justify-content: space-between; gap: 14px; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--grid); }
  th { color: var(--text-secondary); font-weight: 600; }
  td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
  .side { padding: 1px 7px; border-radius: 999px; font-size: 0.74rem; }
  .side.buy { background: color-mix(in srgb, var(--series-1) 18%, transparent); color: var(--series-1); }
  .side.sell { background: color-mix(in srgb, var(--series-2) 18%, transparent); color: var(--series-2); }
  .empty { color: var(--muted); font-size: 0.9rem; }
  .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 22px; }
  @media (max-width: 760px) { .grid-2 { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>__TITLE__</h1>
    <span class="meta">last tick __LASTRUN__ · generated __GENERATED__</span>
  </header>
  <p class="disclaimer">Paper money only — no real brokerage, no real funds. Forward results are the honest test and usually trail the backtest.</p>

  __TILES__

  <div class="card">
    <h2>Equity curve</h2>
    <div class="legend">
      <span class="key"><span class="swatch" style="background:var(--series-1)"></span>Strategy</span>
      <span class="key"><span class="swatch" style="background:var(--series-2)"></span>Buy &amp; Hold</span>
    </div>
    __CHART__
  </div>

  <div class="grid-2">
    <div class="card"><h2>Open positions</h2>__POSITIONS__</div>
    <div class="card"><h2>Recent trades</h2>__TRADES__</div>
  </div>
</div>

<script type="application/json" id="data">__DATA__</script>
<script>
(function () {
  var data = JSON.parse(document.getElementById("data").textContent);
  var svg = document.getElementById("chart");
  if (!svg || data.strategy.length < 2) return;

  var NS = "http://www.w3.org/2000/svg";
  var W = 920, H = 340, M = { t: 16, r: 16, b: 30, l: 62 };
  svg.setAttribute("viewBox", "0 0 " + W + " " + H);
  var plotW = W - M.l - M.r, plotH = H - M.t - M.b;

  function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  function toTime(s) { return new Date(s.length <= 10 ? s + "T00:00:00" : s).getTime(); }

  var strat = data.strategy.map(function (p) { return { t: toTime(p[0]), v: p[1], label: p[0] }; });
  var bench = data.benchmark.map(function (p) { return { t: toTime(p[0]), v: p[1], label: p[0] }; });
  var all = strat.concat(bench);
  var tMin = Math.min.apply(null, all.map(function (d) { return d.t; }));
  var tMax = Math.max.apply(null, all.map(function (d) { return d.t; }));
  var vMin = Math.min.apply(null, all.map(function (d) { return d.v; }));
  var vMax = Math.max.apply(null, all.map(function (d) { return d.v; }));
  var pad = (vMax - vMin) * 0.08 || vMax * 0.05 || 1;
  vMin -= pad; vMax += pad;

  function x(t) { return M.l + (tMax === tMin ? 0 : (t - tMin) / (tMax - tMin)) * plotW; }
  function y(v) { return M.t + (1 - (v - vMin) / (vMax - vMin)) * plotH; }

  function el(name, attrs) {
    var e = document.createElementNS(NS, name);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }
  function money(v) {
    return "$" + v.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 });
  }

  // gridlines + y labels
  var ticks = 5;
  for (var i = 0; i <= ticks; i++) {
    var v = vMin + (vMax - vMin) * (i / ticks);
    var yy = y(v);
    svg.appendChild(el("line", { x1: M.l, y1: yy, x2: W - M.r, y2: yy, stroke: css("--grid"), "stroke-width": 1 }));
    var lbl = el("text", { x: M.l - 8, y: yy + 4, "text-anchor": "end", fill: css("--muted"), "font-size": 11 });
    lbl.textContent = money(v);
    svg.appendChild(lbl);
  }
  // baseline at starting cash for reference
  var base = data.stats.starting_cash;
  if (base >= vMin && base <= vMax) {
    svg.appendChild(el("line", { x1: M.l, y1: y(base), x2: W - M.r, y2: y(base),
      stroke: css("--axis"), "stroke-width": 1, "stroke-dasharray": "3 3" }));
  }
  // x labels (first, middle, last) — anchor the ends inward so they don't clip
  var xLabels = [
    { idx: 0, anchor: "start" },
    { idx: Math.floor(strat.length / 2), anchor: "middle" },
    { idx: strat.length - 1, anchor: "end" },
  ];
  xLabels.forEach(function (spec) {
    var p = strat[spec.idx]; if (!p) return;
    var t = el("text", { x: x(p.t), y: H - 10, "text-anchor": spec.anchor, fill: css("--muted"), "font-size": 11 });
    t.textContent = p.label.slice(0, 10);
    svg.appendChild(t);
  });

  function path(points, color, width) {
    var d = points.map(function (p, i) { return (i ? "L" : "M") + x(p.t).toFixed(1) + " " + y(p.v).toFixed(1); }).join(" ");
    svg.appendChild(el("path", { d: d, fill: "none", stroke: color, "stroke-width": width,
      "stroke-linejoin": "round", "stroke-linecap": "round" }));
  }
  path(bench, css("--series-2"), 2);
  path(strat, css("--series-1"), 2);

  // direct end labels
  function endLabel(points, color, text) {
    var p = points[points.length - 1];
    var t = el("text", { x: x(p.t) - 4, y: y(p.v) - 6, "text-anchor": "end", fill: color, "font-size": 11, "font-weight": 600 });
    t.textContent = text;
    svg.appendChild(t);
  }
  endLabel(strat, css("--series-1"), "Strategy");
  endLabel(bench, css("--series-2"), "B&H");

  // hover crosshair + tooltip
  var tip = document.getElementById("tooltip");
  var vline = el("line", { y1: M.t, y2: M.t + plotH, stroke: css("--axis"), "stroke-width": 1, opacity: 0 });
  var dot1 = el("circle", { r: 4, fill: css("--series-1"), opacity: 0 });
  var dot2 = el("circle", { r: 4, fill: css("--series-2"), opacity: 0 });
  svg.appendChild(vline); svg.appendChild(dot1); svg.appendChild(dot2);

  function nearest(points, t) {
    var best = points[0], bd = Infinity;
    for (var i = 0; i < points.length; i++) {
      var d = Math.abs(points[i].t - t);
      if (d < bd) { bd = d; best = points[i]; }
    }
    return best;
  }
  svg.addEventListener("mousemove", function (ev) {
    var rect = svg.getBoundingClientRect();
    var px = (ev.clientX - rect.left) / rect.width * W;
    if (px < M.l || px > W - M.r) return;
    var t = tMin + (px - M.l) / plotW * (tMax - tMin);
    var s = nearest(strat, t), b = nearest(bench, t);
    vline.setAttribute("x1", x(s.t)); vline.setAttribute("x2", x(s.t)); vline.setAttribute("opacity", 1);
    dot1.setAttribute("cx", x(s.t)); dot1.setAttribute("cy", y(s.v)); dot1.setAttribute("opacity", 1);
    dot2.setAttribute("cx", x(b.t)); dot2.setAttribute("cy", y(b.v)); dot2.setAttribute("opacity", 1);
    tip.hidden = false;
    tip.style.left = (x(s.t) / W * rect.width) + "px";
    tip.style.top = (y(Math.max(s.v, b.v)) / H * rect.height) + "px";
    tip.innerHTML = '<div class="t-date">' + s.label.slice(0, 10) + '</div>' +
      '<div class="t-row"><span>Strategy</span><b>' + money(s.v) + '</b></div>' +
      '<div class="t-row"><span>Buy &amp; Hold</span><b>' + money(b.v) + '</b></div>';
  });
  svg.addEventListener("mouseleave", function () {
    tip.hidden = true; vline.setAttribute("opacity", 0);
    dot1.setAttribute("opacity", 0); dot2.setAttribute("opacity", 0);
  });
})();
</script>
</body>
</html>
"""
