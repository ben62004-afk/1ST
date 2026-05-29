"""Backtest engine: regime switch between QLD (risk-on) and SHY (risk-off).

Execution model (no look-ahead)
-------------------------------
* The target position is decided from data **up to and including close of day
  t** (see :func:`qld_ewma.signals.generate_signal`).
* It is executed on the **next bar (T+1)**.  We implement this by shifting the
  target position forward one day before applying it to that day's total return.
  Because the data are adjusted-close (total-return) series, the realised return
  for holding the chosen asset on day ``t+1`` is its close-to-close TR; this is
  the standard close-based approximation of a next-open execution.
* On the day a switch takes effect we charge round-trip transaction costs
  (sell the old leg + buy the new leg = "雙邊").

Costs
-----
``cost_per_side = fee + slippage`` (default 0.03% + 0.05% = 0.08%).  A switch
incurs ``2 * cost_per_side`` (both legs), deducted from that day's return.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd

from .signals import generate_signal

FEE = 0.0003       # 0.03% commission per side
SLIPPAGE = 0.0005  # 0.05% slippage per side


@dataclasses.dataclass
class BacktestResult:
    equity: pd.Series          # strategy equity curve (starts at 1.0)
    returns: pd.Series         # strategy daily net returns
    position: pd.Series        # executed position per day (1=QLD, 0=SHY)
    target: pd.Series          # target position decided at prior close
    switches: int              # number of regime changes actually executed
    exposure: float            # fraction of days held in QLD
    cost_per_side: float


def run_backtest(
    prices: pd.DataFrame,
    span: int = 200,
    method: str = "ewma",
    buffer: float = 0.0,
    fee: float = FEE,
    slippage: float = SLIPPAGE,
    risk_on: str = "QLD",
    risk_off: str = "SHY",
    signal_col: str | None = None,
) -> BacktestResult:
    """Run the regime-switch backtest.

    Parameters
    ----------
    prices : DataFrame with at least the signal column and ``risk_on``/``risk_off``.
    signal_col : column to compute the trend on; defaults to 'NDX' if present
        and populated, else 'QQQ'.
    """
    prices = prices.sort_index()
    if signal_col is None:
        if "NDX" in prices and prices["NDX"].notna().any():
            signal_col = "NDX"
        else:
            signal_col = "QQQ"

    close = prices[signal_col].dropna()
    target = generate_signal(close, span=span, method=method, buffer=buffer)

    # Execute on T+1: shift the target forward one day.
    executed = target.shift(1).fillna(0.0)

    # Daily total returns of each leg, aligned to the executed-position index.
    on_ret = prices[risk_on].pct_change()
    off_ret = prices[risk_off].pct_change()
    idx = executed.index
    on_ret = on_ret.reindex(idx)
    off_ret = off_ret.reindex(idx)

    gross = executed * on_ret + (1.0 - executed) * off_ret

    # Transaction costs on days where the executed position changes.
    cost_per_side = fee + slippage
    pos_change = executed.diff().abs().fillna(0.0)
    # A full switch (0<->1) moves |delta|=1 and touches both legs => 2 sides.
    costs = pos_change * 2.0 * cost_per_side

    net = (gross - costs).fillna(0.0)
    equity = (1.0 + net).cumprod()

    switches = int((executed.diff().abs() > 0).sum())
    exposure = float(executed.mean())

    return BacktestResult(
        equity=equity,
        returns=net,
        position=executed,
        target=target,
        switches=switches,
        exposure=exposure,
        cost_per_side=cost_per_side,
    )


def buy_and_hold(prices: pd.DataFrame, symbol: str) -> pd.Series:
    """Equity curve (starts at 1.0) for buying and holding ``symbol``."""
    ret = prices[symbol].pct_change().fillna(0.0)
    return (1.0 + ret).cumprod()
