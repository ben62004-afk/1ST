#!/usr/bin/env python3
"""Run the QLD/SHY EWMA-200 regime-switch backtest end to end.

Produces:
    outputs/metrics.csv         core performance table (+ benchmarks)
    outputs/robustness.csv      span / EWMA-vs-SMA / buffer-band sweeps
    outputs/equity_curve.png    growth-of-$1 (log scale)
    outputs/drawdown.png        underwater plot
    report.md                   written analysis (conclusions + assumptions + risks)

Deterministic: data is cached and (when synthetic) seeded. Re-runs reproduce
identical results.

Usage:
    python run_backtest.py [--synthetic] [--seed 42]
"""

from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

from qld_ewma.backtest import run_backtest, buy_and_hold, FEE, SLIPPAGE
from qld_ewma.data import load_prices
from qld_ewma.metrics import performance_metrics
from qld_ewma.plots import plot_equity_curves, plot_drawdowns

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
ROOT = os.path.dirname(os.path.abspath(__file__))
SEED = 42


def _fmt_pct(x: float) -> str:
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x * 100:.2f}%"


def _fmt_num(x: float) -> str:
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.2f}"


def build_metrics_table(prices: pd.DataFrame, res) -> pd.DataFrame:
    rows = {}
    rows["Strategy (EWMA-200)"] = {
        **performance_metrics(res.equity, res.returns),
        "Exposure": res.exposure,
        "Switches": res.switches,
    }
    qld_bh = buy_and_hold(prices, "QLD")
    rows["QLD Buy&Hold"] = {**performance_metrics(qld_bh), "Exposure": 1.0, "Switches": 0}
    qqq_bh = buy_and_hold(prices, "QQQ")
    rows["QQQ Buy&Hold"] = {**performance_metrics(qqq_bh), "Exposure": 1.0, "Switches": 0}
    shy_bh = buy_and_hold(prices, "SHY")
    rows["SHY Buy&Hold"] = {**performance_metrics(shy_bh), "Exposure": 0.0, "Switches": 0}

    df = pd.DataFrame(rows).T
    cols = ["CAGR", "MDD", "Calmar", "Sharpe", "Sortino", "AnnVol",
            "TotalReturn", "Exposure", "Switches"]
    return df[cols]


def build_robustness(prices: pd.DataFrame) -> pd.DataFrame:
    rows = {}
    # (1) span sensitivity, EWMA.
    for span in (150, 200, 250):
        r = run_backtest(prices, span=span, method="ewma")
        rows[f"EWMA span={span}"] = {
            **performance_metrics(r.equity, r.returns),
            "Exposure": r.exposure, "Switches": r.switches,
        }
    # (2) EWMA vs SMA at span=200.
    r_sma = run_backtest(prices, span=200, method="sma")
    rows["SMA window=200"] = {
        **performance_metrics(r_sma.equity, r_sma.returns),
        "Exposure": r_sma.exposure, "Switches": r_sma.switches,
    }
    # (3) +/-1% buffer band on whipsaw (EWMA-200).
    for buf in (0.0, 0.01):
        r = run_backtest(prices, span=200, method="ewma", buffer=buf)
        rows[f"EWMA-200 buffer=+/-{int(buf*100)}%"] = {
            **performance_metrics(r.equity, r.returns),
            "Exposure": r.exposure, "Switches": r.switches,
        }
    df = pd.DataFrame(rows).T
    cols = ["CAGR", "MDD", "Calmar", "Sharpe", "Sortino", "AnnVol",
            "Exposure", "Switches"]
    return df[cols]


def md_table(df: pd.DataFrame) -> str:
    pct_cols = {"CAGR", "MDD", "AnnVol", "TotalReturn", "Exposure"}
    headers = ["Series"] + list(df.columns)
    lines = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join(["---"] * len(headers)) + " |"]
    for name, row in df.iterrows():
        cells = [name]
        for c in df.columns:
            v = row[c]
            if c == "Switches":
                cells.append(str(int(v)))
            elif c in pct_cols:
                cells.append(_fmt_pct(v))
            else:
                cells.append(_fmt_num(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true",
                    help="force the seeded synthetic dataset")
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()

    np.random.seed(args.seed)
    os.makedirs(OUT, exist_ok=True)

    data = load_prices(seed=args.seed, force_synthetic=args.synthetic)
    prices = data.prices
    print(f"Data source: {data.source} (synthetic={data.synthetic}), "
          f"{prices.index[0].date()} -> {prices.index[-1].date()}, "
          f"{len(prices)} rows")

    res = run_backtest(prices, span=200, method="ewma")

    table = build_metrics_table(prices, res)
    robust = build_robustness(prices)
    table.to_csv(os.path.join(OUT, "metrics.csv"))
    robust.to_csv(os.path.join(OUT, "robustness.csv"))

    curves = {
        "Strategy (EWMA-200)": res.equity,
        "QLD Buy&Hold": buy_and_hold(prices, "QLD"),
        "QQQ Buy&Hold": buy_and_hold(prices, "QQQ"),
    }
    tag = "SYNTHETIC DATA - ILLUSTRATIVE" if data.synthetic else "real data"
    plot_equity_curves(curves, os.path.join(OUT, "equity_curve.png"),
                       f"QLD/SHY EWMA-200 vs Buy&Hold ({tag})")
    plot_drawdowns(curves, os.path.join(OUT, "drawdown.png"),
                   f"Drawdowns ({tag})")

    write_report(data, prices, res, table, robust)
    print("Wrote outputs/ and report.md")
    print(table.to_string())


def write_report(data, prices, res, table, robust):
    syn = data.synthetic
    period = f"{prices.index[0].date()} to {prices.index[-1].date()}"
    strat = table.loc["Strategy (EWMA-200)"]
    qld = table.loc["QLD Buy&Hold"]

    data_note = ""
    if syn:
        data_note = (
            "> **⚠️ DATA CAVEAT — READ FIRST.** This execution environment had "
            "no network access to any market-data provider (Yahoo, Stooq, "
            "AlphaVantage, Nasdaq are all blocked by the sandbox network "
            "policy), and no current total-return series for QLD/SHY/QQQ was "
            "available from the reachable hosts. The numbers below were "
            "therefore generated from a **seeded synthetic dataset** that "
            "reproduces realistic Nasdaq-100 dynamics (volatility regimes, "
            "leverage decay via true 2x daily-rebalance mechanics, a low-vol "
            "bond leg). **They are ILLUSTRATIVE of the methodology, not "
            "investment conclusions.** To obtain real figures, run in an "
            "environment with network access (or drop a `data/cache/prices.csv` "
            "with columns NDX,QQQ,QLD,SHY) and re-run:\n>\n"
            "> ```bash\n> python run_backtest.py\n> ```\n>\n"
            "> The code path, costs, no-look-ahead execution and metrics are "
            "identical regardless of data source.\n\n"
        )

    md = f"""# QLD/SHY EWMA-200 Regime-Switch Backtest — Report

{data_note}## 1. Summary

A long-only trend-following overlay that holds the 2x Nasdaq-100 ETF **QLD**
when the Nasdaq-100 is in an uptrend and rotates to the short-Treasury ETF
**SHY** when it is not. The trend is the **EWMA-200** (span=200, α=2/201) of the
**signal instrument** — the Nasdaq-100 index (`^NDX`, or QQQ adjusted-close as a
proxy). The signal is deliberately *not* computed on QLD, so leverage decay
cannot distort the trend estimate.

- **Data source for this run:** `{data.source}` (synthetic={syn})
- **Period:** {period} ({len(prices)} trading days)
- **Signal:** EWMA-200 on NDX/QQQ total-return close
- **Rule:** close > EWMA → hold QLD; close ≤ EWMA → hold SHY (boundary = risk-off)
- **Execution:** signal at T close, position applied on **T+1** (no look-ahead)
- **Costs:** {FEE*100:.2f}% fee + {SLIPPAGE*100:.2f}% slippage per side, charged on
  both legs of a switch ({(FEE+SLIPPAGE)*2*100:.2f}% round-trip)

### Headline (strategy vs QLD buy-and-hold)

| Metric | Strategy EWMA-200 | QLD Buy&Hold |
| --- | --- | --- |
| CAGR | {_fmt_pct(strat['CAGR'])} | {_fmt_pct(qld['CAGR'])} |
| **Max Drawdown** | **{_fmt_pct(strat['MDD'])}** | **{_fmt_pct(qld['MDD'])}** |
| Calmar | {_fmt_num(strat['Calmar'])} | {_fmt_num(qld['Calmar'])} |
| Sharpe | {_fmt_num(strat['Sharpe'])} | {_fmt_num(qld['Sharpe'])} |
| Sortino | {_fmt_num(strat['Sortino'])} | {_fmt_num(qld['Sortino'])} |
| Ann. Vol | {_fmt_pct(strat['AnnVol'])} | {_fmt_pct(qld['AnnVol'])} |
| Time in market | {_fmt_pct(strat['Exposure'])} | 100% |
| Switches | {int(strat['Switches'])} | 0 |

The central thesis of trend-timing a leveraged ETF is **drawdown control**: a 2x
ETF can lose the vast majority of its value in a deep bear market (path-dependent
decay compounds the loss), so sitting in cash-like SHY during downtrends is meant
to convert an un-investable max-drawdown into a tolerable one — ideally without
sacrificing all of the upside.

## 2. Full performance table

{md_table(table)}

*MDD is the core metric. Calmar = CAGR / |MDD|. Sharpe/Sortino use rf=0,
annualised by √252. AnnVol is annualised daily-return volatility. "Switches" is
the number of executed regime changes (each charged round-trip).*

## 3. Charts

![Equity curve](outputs/equity_curve.png)

![Drawdowns](outputs/drawdown.png)

## 4. Robustness

{md_table(robust)}

- **Span sensitivity ({{150,200,250}})** — shorter spans react faster (fewer deep
  drawdowns but more whipsaw/switches and cost drag); longer spans lag. A result
  that only works at one exact span is overfit; we report all three.
- **EWMA vs SMA** — EWMA weights recent prices more and turns slightly faster
  than the equal-weight SMA at the same length; compare switch counts and Calmar.
- **±1% buffer band** — a symmetric hysteresis band around the trend suppresses
  whipsaw: it should reduce the switch count (and cost drag) at the price of
  slightly later entries/exits. Compare the `buffer=0%` vs `buffer=±1%` rows.

## 5. Assumptions

1. **Total-return data.** All legs use dividend-reinvested adjusted close, so SHY
   coupons and ETF distributions are captured (see tax caveat below).
2. **T+1 execution via close-to-close TR.** Adjusted-close series have no
   adjusted *open*, so the spec's "T+1 open" rebalance is implemented as applying
   the new position to T+1's total return. This is the standard close-based
   convention and is verified look-ahead-free by tests.
3. **Costs.** {FEE*100:.2f}% commission + {SLIPPAGE*100:.2f}% slippage per side,
   both legs per switch. No bid/ask modelling beyond slippage, no market impact.
4. **No financing/borrow line items** beyond what is embedded in QLD's own NAV
   (its 0.95% expense ratio and swap financing are already in its price series).
5. **rf = 0** for Sharpe/Sortino. Using a positive T-bill rate would lower both
   modestly and is a documented choice.
6. **Determinism.** Data is cached; the synthetic fallback is seeded
   (`seed=42`). Re-runs are bit-identical.

## 6. Risks & caveats

- **Leverage path risk.** QLD resets 2x daily. In choppy, high-volatility
  sideways markets it bleeds even when the index ends flat; the strategy mitigates
  this only when the *trend* filter is out of the market, not during in-trend
  chop.
- **Whipsaw / regime cost.** Near the EWMA, frequent crossings generate switches;
  each round-trip costs {(FEE+SLIPPAGE)*2*100:.2f}% and taxes are extra. The
  buffer-band analysis quantifies this.
- **SHY foreign withholding tax (risk-off leg).** For a non-US (e.g. Taiwan)
  investor, SHY distributions are US-source and subject to **30% US withholding
  tax** (absent treaty relief). SHY is a *bond* ETF whose total return is almost
  entirely coupon income, so a 30% haircut on distributions is a direct, material
  drag on the risk-off leg — unlike an equity ETF where most return is price
  appreciation. The more time the strategy spends in SHY (high "time-out-of-market"
  in prolonged bears), the larger this tax leakage. Mitigations to consider:
  a local money-market/short-bond fund, treaty-rate reclaim, or holding cash.
- **Single-regime / overfitting risk.** Most of the sample is one secular tech
  bull market. Parameter robustness is reported, but out-of-sample / different
  regimes (e.g. a prolonged rising-rate bear) could behave differently.
- **Survivorship & product risk.** QLD/SHY are specific products; expense ratios,
  swap counterparties, and index methodology can change.

## 7. Reproduce

```bash
pip install -r requirements.txt
pytest -q                 # all tests must pass
python run_backtest.py    # real data if network/cache available; else synthetic
python run_backtest.py --synthetic   # force the seeded illustrative dataset
```
"""
    with open(os.path.join(ROOT, "report.md"), "w") as f:
        f.write(md)


if __name__ == "__main__":
    main()
