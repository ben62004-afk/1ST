# QLD/SHY EWMA-200 Regime-Switch Backtest

A trend-timing overlay on the 2x Nasdaq-100 ETF **QLD**: hold QLD when the
Nasdaq-100 trades above its **EWMA-200** (span=200, α=2/201), rotate to the
short-Treasury ETF **SHY** otherwise. The trend signal is computed on the
Nasdaq-100 index (`^NDX`, or QQQ adjusted close as a proxy) — never on QLD — so
leverage decay cannot distort it. Execution is **T+1** (no look-ahead), with
0.03% fee + 0.05% slippage per side charged on both legs of a switch.

## Quick start

```bash
pip install -r requirements.txt
pytest -q                 # 30 tests, all green
python run_backtest.py    # uses real data if reachable, else cache, else synthetic
```

Outputs land in `outputs/` (`metrics.csv`, `robustness.csv`, `equity_curve.png`,
`drawdown.png`) and a written `report.md`.

## Data resolution (deterministic, cached)

1. `data/cache/prices.csv` if present (columns: `NDX,QQQ,QLD,SHY`, adjusted close).
2. Live download via `yfinance` (auto-adjusted total return), then cached.
3. **Seeded synthetic fallback** — used only when neither cache nor network is
   available. Its numbers are *illustrative of the methodology, not investment
   advice*, and the report flags this loudly. Force it with
   `python run_backtest.py --synthetic`.

> This repository was produced in a sandbox whose network policy blocked all
> market-data hosts, so the committed `report.md`/PNGs use the synthetic
> fallback. Re-running anywhere with network access (or a real
> `data/cache/prices.csv`) regenerates the same artifacts with real numbers and
> **zero code changes**.

## Layout

```
qld_ewma/
  data.py      # load_prices: cache -> yfinance -> seeded synthetic
  signals.py   # ewma / sma / generate_signal (+ buffer band)
  backtest.py  # run_backtest: T+1 execution, costs, return chaining
  metrics.py   # CAGR, MDD, Calmar, Sharpe, Sortino, AnnVol, ...
  plots.py     # equity curve + drawdown PNGs
run_backtest.py
tests/         # EWMA calc, signal boundary, no-look-ahead, return chaining, ...
```
