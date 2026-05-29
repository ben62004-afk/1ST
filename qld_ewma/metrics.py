"""Performance metrics for equity curves / return series."""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def _years(equity: pd.Series) -> float:
    days = (equity.index[-1] - equity.index[0]).days
    return max(days / 365.25, 1e-9)


def cagr(equity: pd.Series) -> float:
    total = equity.iloc[-1] / equity.iloc[0]
    return total ** (1.0 / _years(equity)) - 1.0


def max_drawdown(equity: pd.Series) -> float:
    """Maximum drawdown as a negative fraction (e.g. -0.55)."""
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return float(dd.min())


def drawdown_series(equity: pd.Series) -> pd.Series:
    peak = equity.cummax()
    return equity / peak - 1.0


def calmar(equity: pd.Series) -> float:
    mdd = abs(max_drawdown(equity))
    if mdd == 0:
        return float("nan")
    return cagr(equity) / mdd


def annual_volatility(returns: pd.Series) -> float:
    return float(returns.std(ddof=1) * np.sqrt(TRADING_DAYS))


def sharpe(returns: pd.Series, rf_annual: float = 0.0) -> float:
    rf_daily = rf_annual / TRADING_DAYS
    excess = returns - rf_daily
    sd = excess.std(ddof=1)
    if not np.isfinite(sd) or sd < 1e-15:
        return float("nan")
    return float(excess.mean() / sd * np.sqrt(TRADING_DAYS))


def sortino(returns: pd.Series, rf_annual: float = 0.0) -> float:
    rf_daily = rf_annual / TRADING_DAYS
    excess = returns - rf_daily
    downside = excess[excess < 0]
    dd = np.sqrt((downside ** 2).mean()) if len(downside) else 0.0
    if not np.isfinite(dd) or dd < 1e-15:
        return float("nan")
    return float(excess.mean() / dd * np.sqrt(TRADING_DAYS))


def performance_metrics(
    equity: pd.Series,
    returns: pd.Series | None = None,
    rf_annual: float = 0.0,
) -> Dict[str, float]:
    """Return the core metric dictionary for an equity curve.

    If ``returns`` is omitted it is derived from the equity curve.
    """
    if returns is None:
        returns = equity.pct_change().dropna()
    return {
        "CAGR": cagr(equity),
        "MDD": max_drawdown(equity),
        "Calmar": calmar(equity),
        "Sharpe": sharpe(returns, rf_annual),
        "Sortino": sortino(returns, rf_annual),
        "AnnVol": annual_volatility(returns),
        "TotalReturn": float(equity.iloc[-1] / equity.iloc[0] - 1.0),
    }
